"""In-process background worker.

Priority loop:
  1. Generate queued topics (plan -> cards) — the core pipeline.
  2. Enrichment, in small chunks so a newly queued topic preempts quickly:
     per-unit learning material, then per-card deep explanations — both grounded
     in keyless web search results so the user gets real, clickable sources.
  3. Nightly weakness-report emails (active-recall coaching for wrong answers).

Jobs are persisted in SQLite, so a container restart resumes pending work.
"""
import asyncio
import json
import logging
import os
from datetime import datetime

from . import db, emailer, extract, llm, websearch

log = logging.getLogger("flashdeck.worker")

POLL_INTERVAL = 3
ENRICH_CARDS_PER_STEP = 2
REPORT_HOUR = int(os.environ.get("REPORT_HOUR", "5"))  # local container time
REPORT_MIN_WRONG = 3
REPORT_WINDOW = 7 * 86400

# Consecutive-failure counters so a dead Ollama (e.g. the host laptop is asleep)
# retries instead of burning through work, but a permanently broken item is
# eventually marked failed and skipped.
_fail_counts: dict[str, int] = {}
MAX_FAILS = 3

# Users already checked for a weakness report today (avoids re-querying all day).
_report_checked: dict[int, str] = {}


async def run_forever():
    with db.connect() as con:
        con.execute("UPDATE topics SET status='queued', progress_pct=0 WHERE status='processing'")
    log.info("Worker started (report hour: %02d:00)", REPORT_HOUR)
    while True:
        try:
            topic = _next_queued()
            if topic:
                await _process(topic)
                continue
            if await _enrich_step():
                continue
            await _maybe_send_reports()
            if await _maybe_refresh_topics():
                continue
            await asyncio.sleep(POLL_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Worker loop error")
            await asyncio.sleep(POLL_INTERVAL)


def _next_queued():
    with db.connect() as con:
        return db.one(con, "SELECT * FROM topics WHERE status='queued' ORDER BY id LIMIT 1")


def _update(topic_id: int, **fields):
    cols = ", ".join(f"{k}=?" for k in fields)
    with db.connect() as con:
        con.execute(f"UPDATE topics SET {cols} WHERE id=?", (*fields.values(), topic_id))


# ------------------------------------------------------------- core generation

async def _process(topic: dict):
    topic_id = topic["id"]
    with db.connect() as con:
        user = db.one(con, "SELECT * FROM users WHERE id=?", (topic["user_id"],))
        sources = db.all_rows(con, "SELECT * FROM sources WHERE topic_id=?", (topic_id,))
    if not user:
        _update(topic_id, status="failed", error="user deleted")
        return

    log.info("Processing topic %s for user %s", topic_id, user["email"])
    _update(topic_id, status="processing", progress_msg="extracting_sources", progress_pct=5)
    try:
        for src in sources:
            if src["content_text"]:
                continue
            try:
                if src["kind"] == "url":
                    text = await extract.fetch_url(src["name"])
                else:
                    with open(src["file_path"], "rb") as fh:
                        text = extract.extract_file(src["name"], fh.read())
            except Exception as e:
                log.warning("Source %s failed: %s", src["name"], e)
                text = ""
            src["content_text"] = text
            with db.connect() as con:
                con.execute("UPDATE sources SET content_text=? WHERE id=?", (text, src["id"]))
        sources_text = extract.combine_sources(sources)

        _update(topic_id, progress_msg="planning", progress_pct=15)
        plan = await llm.generate_plan(user, topic, sources_text)
        _update(topic_id, title=str(plan.get("title", ""))[:120],
                plan_json=json.dumps(plan, ensure_ascii=False))

        units = plan["units"]
        per_unit = llm.cards_per_unit(topic["card_count"], len(units))
        total_cards = 0
        for i in range(len(units)):
            _update(topic_id, progress_msg=f"generating_unit:{i + 1}/{len(units)}",
                    progress_pct=15 + int(80 * i / len(units)))
            try:
                cards = await llm.generate_unit_cards(user, topic, plan, i, per_unit, sources_text)
            except llm.OllamaError as e:
                if i == 0:
                    raise
                log.warning("Unit %s of topic %s failed, keeping partial deck: %s", i, topic_id, e)
                continue
            with db.connect() as con:
                for card in cards:
                    con.execute(
                        """INSERT INTO cards (topic_id, unit_index, type, question, answer,
                           choices_json, explanation, difficulty, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (topic_id, i, card["type"], card["question"], card["answer"],
                         json.dumps(card["choices"], ensure_ascii=False),
                         card["explanation"], card["difficulty"], db.now()),
                    )
            total_cards += len(cards)

        if total_cards == 0:
            raise llm.OllamaError("The model produced no usable flashcards.")

        _update(topic_id, status="ready", progress_msg="", progress_pct=100, ready_at=db.now())
        log.info("Topic %s ready: %s cards in %s units", topic_id, total_cards, len(units))
        topic["title"] = plan.get("title", topic["prompt"][:60])
        await emailer.send_topic_ready(user, topic, total_cards, len(units))

    except Exception as e:
        message = str(e) if isinstance(e, llm.OllamaError) else f"Unexpected error: {e}"
        log.exception("Topic %s failed", topic_id)
        _update(topic_id, status="failed", error=message[:500], progress_pct=0)
        await emailer.send_topic_failed(user, topic, message[:500])


# ------------------------------------------------------------- enrichment

def _record_failure(key: str) -> bool:
    """Count a failure; True once the item should be marked failed and skipped."""
    _fail_counts[key] = _fail_counts.get(key, 0) + 1
    if _fail_counts[key] >= MAX_FAILS:
        del _fail_counts[key]
        return True
    return False


async def _enrich_step() -> bool:
    """Do one small chunk of enrichment work. Returns True if something was attempted."""
    with db.connect() as con:
        topic = db.one(
            con,
            """SELECT t.*, u.id AS uid FROM topics t JOIN users u ON u.id=t.user_id
               WHERE t.status='ready' AND t.plan_json != '' AND (
                 t.material_json = ''
                 OR EXISTS (SELECT 1 FROM cards c WHERE c.topic_id=t.id AND c.sources_json='')
               ) ORDER BY t.id LIMIT 1""",
        )
        if not topic:
            return False
        user = db.one(con, "SELECT * FROM users WHERE id=?", (topic["user_id"],))

    plan = json.loads(topic["plan_json"])
    material = json.loads(topic["material_json"]) if topic["material_json"] else None

    # Phase 1: learning material, one unit per step.
    if material is None or len(material) < len(plan["units"]):
        material = material or []
        idx = len(material)
        unit_title = plan["units"][idx].get("title", "")
        key = f"mat:{topic['id']}:{idx}"
        _update(topic["id"], progress_msg=f"enriching_material:{idx + 1}/{len(plan['units'])}")
        try:
            with db.connect() as con:
                srcs = db.all_rows(con, "SELECT * FROM sources WHERE topic_id=?", (topic["id"],))
            results = await websearch.search(f"{plan.get('title', '')} {unit_title}")
            entry = await llm.generate_unit_material(
                user, topic, plan, idx, results, extract.combine_sources(srcs))
            material.append(entry)
            _fail_counts.pop(key, None)
            log.info("Material for topic %s unit %s done (%s sources)",
                     topic["id"], idx, len(entry["sources"]))
        except Exception as e:
            log.warning("Material for topic %s unit %s failed: %s", topic["id"], idx, e)
            if _record_failure(key):
                material.append({"unit_index": idx, "title": unit_title,
                                 "text": "", "sources": [], "failed": True})
            else:
                await asyncio.sleep(POLL_INTERVAL)
                return True
        done = len(material) >= len(plan["units"])
        _update(topic["id"], material_json=json.dumps(material, ensure_ascii=False),
                progress_msg="" if done else f"enriching_material:{len(material)}/{len(plan['units'])}")
        return True

    # Phase 2: deep card explanations, a couple per step.
    with db.connect() as con:
        cards = db.all_rows(
            con, "SELECT * FROM cards WHERE topic_id=? AND sources_json='' ORDER BY id LIMIT ?",
            (topic["id"], ENRICH_CARDS_PER_STEP),
        )
        remaining = db.one(con, "SELECT COUNT(*) AS c FROM cards WHERE topic_id=? AND sources_json=''",
                           (topic["id"],))["c"]
    _update(topic["id"], progress_msg=f"enriching_cards:{remaining}")
    for card in cards:
        key = f"card:{card['id']}"
        try:
            results = await websearch.search(f"{topic['title']} {card['question'][:120]}")
            data = await llm.enrich_card(user, topic, card, results)
            with db.connect() as con:
                con.execute(
                    "UPDATE cards SET long_explanation=?, sources_json=? WHERE id=?",
                    (data["explanation"], json.dumps(data["sources"], ensure_ascii=False),
                     card["id"]),
                )
            _fail_counts.pop(key, None)
        except Exception as e:
            log.warning("Enriching card %s failed: %s", card["id"], e)
            if _record_failure(key):
                with db.connect() as con:
                    con.execute("UPDATE cards SET sources_json='[]' WHERE id=?", (card["id"],))
            else:
                await asyncio.sleep(POLL_INTERVAL)
                return True
    if remaining <= len(cards):
        _update(topic["id"], progress_msg="")
        log.info("Enrichment for topic %s complete", topic["id"])
    return True


# ------------------------------------------------------------- nightly refresh

REFRESH_BATCH = 8


async def _maybe_refresh_topics() -> bool:
    """Generate a fresh batch of questions for one opted-in topic per night.

    Targets the unit the learner currently gets wrong most often (active-recall
    coaching: practice where it hurts); falls back to round-robin when there is
    no answer history. New cards enter the normal enrichment pipeline.
    """
    now = datetime.now()
    if now.hour < REPORT_HOUR:
        return False
    today_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    with db.connect() as con:
        topic = db.one(
            con,
            """SELECT * FROM topics WHERE nightly_refresh=1 AND status='ready'
               AND plan_json != '' AND last_refresh_at < ? ORDER BY last_refresh_at LIMIT 1""",
            (today_start,),
        )
        if not topic:
            return False
        user = db.one(con, "SELECT * FROM users WHERE id=?", (topic["user_id"],))
    key = f"refresh:{topic['id']}"
    plan = json.loads(topic["plan_json"])
    try:
        with db.connect() as con:
            weak = db.one(
                con,
                """SELECT c.unit_index, SUM(CASE WHEN a.result='wrong' THEN 1 ELSE 0 END) AS w
                   FROM answer_log a JOIN cards c ON c.id=a.card_id
                   WHERE a.topic_id=? AND a.answered_at >= ?
                   GROUP BY c.unit_index ORDER BY w DESC LIMIT 1""",
                (topic["id"], db.now() - 14 * 86400),
            )
            existing = [r["question"] for r in db.all_rows(
                con, "SELECT question FROM cards WHERE topic_id=? ORDER BY id DESC LIMIT 60",
                (topic["id"],))]
            srcs = db.all_rows(con, "SELECT * FROM sources WHERE topic_id=?", (topic["id"],))
        unit_index = weak["unit_index"] if weak and weak["w"] else \
            int(now.timestamp() // 86400) % len(plan["units"])
        cards = await llm.generate_unit_cards(
            user, topic, plan, unit_index, REFRESH_BATCH,
            extract.combine_sources(srcs), avoid_questions=existing,
        )
        with db.connect() as con:
            for card in cards:
                con.execute(
                    """INSERT INTO cards (topic_id, unit_index, type, question, answer,
                       choices_json, explanation, difficulty, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (topic["id"], unit_index, card["type"], card["question"], card["answer"],
                     json.dumps(card["choices"], ensure_ascii=False),
                     card["explanation"], card["difficulty"], db.now()),
                )
            con.execute("UPDATE topics SET last_refresh_at=? WHERE id=?",
                        (db.now(), topic["id"]))
        _fail_counts.pop(key, None)
        log.info("Nightly refresh: %s new cards for topic %s (unit %s)",
                 len(cards), topic["id"], unit_index)
    except Exception as e:
        log.warning("Nightly refresh for topic %s failed: %s", topic["id"], e)
        if _record_failure(key):
            # Give up for today; try again tomorrow night.
            with db.connect() as con:
                con.execute("UPDATE topics SET last_refresh_at=? WHERE id=?",
                            (db.now(), topic["id"]))
    return True


# ------------------------------------------------------------- nightly reports

async def _maybe_send_reports():
    if not emailer.smtp_configured():
        return
    now = datetime.now()
    if now.hour < REPORT_HOUR:
        return
    today = now.strftime("%Y-%m-%d")
    today_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    with db.connect() as con:
        users = db.all_rows(
            con,
            "SELECT * FROM users WHERE email_notifications=1 AND last_report_at < ?",
            (today_start,),
        )
    for user in users:
        if _report_checked.get(user["id"]) == today:
            continue
        _report_checked[user["id"]] = today
        try:
            await _send_report_for(user)
        except Exception:
            log.exception("Weakness report for user %s failed", user["id"])


async def _send_report_for(user: dict):
    since = max(user["last_report_at"], db.now() - REPORT_WINDOW)
    with db.connect() as con:
        rows = db.all_rows(
            con,
            """SELECT c.id, c.question, c.answer, c.explanation, c.long_explanation,
                      c.sources_json, t.title AS topic_title,
                      SUM(CASE WHEN a.result='wrong' THEN 1 ELSE 0 END) AS wrong_count,
                      MAX(a.answered_at) AS last_at
               FROM answer_log a
               JOIN cards c ON c.id = a.card_id
               JOIN topics t ON t.id = a.topic_id
               WHERE a.user_id=? AND a.answered_at>=? AND a.result='wrong'
               GROUP BY c.id ORDER BY t.id, wrong_count DESC""",
            (user["id"], since),
        )
    # Only count cards that are STILL weak: wrong more recently than last correct.
    weak = []
    with db.connect() as con:
        for row in rows:
            newer_correct = db.one(
                con,
                """SELECT 1 AS x FROM answer_log WHERE user_id=? AND card_id=? AND
                   result='correct' AND answered_at > ?""",
                (user["id"], row["id"], row["last_at"]),
            )
            if not newer_correct:
                weak.append(row)
    if len(weak) < REPORT_MIN_WRONG:
        return

    weak = weak[:12]  # keep the email and the LLM context bounded
    blocks, source_lines, seen_urls = [], [], set()
    for row in weak:
        explanation = row["long_explanation"] or row["explanation"]
        blocks.append(
            f"TOPIC: {row['topic_title']}\nQ: {row['question']}\nCORRECT ANSWER: {row['answer']}\n"
            f"EXPLANATION NOTES: {explanation[:400]}\n(missed {row['wrong_count']}x)"
        )
        for src in json.loads(row["sources_json"] or "[]"):
            if src["url"] not in seen_urls:
                seen_urls.add(src["url"])
                source_lines.append(f"- {src['title']}: {src['url']}")
    cards_block = "\n\n".join(blocks)

    try:
        body = await llm.generate_weakness_report(user, cards_block)
    except Exception as e:
        log.warning("LLM report for user %s failed (%s), using template fallback", user["id"], e)
        body = emailer.fallback_report_body(user, weak)

    if source_lines:
        body += "\n\n" + emailer.sources_heading(user) + "\n" + "\n".join(source_lines[:12])
    await emailer.send_weakness_report(user, body, len(weak))
    with db.connect() as con:
        con.execute("UPDATE users SET last_report_at=? WHERE id=?", (db.now(), user["id"]))
    log.info("Sent weakness report to %s (%s weak cards)", user["email"], len(weak))