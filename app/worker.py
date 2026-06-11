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

log = logging.getLogger("slopstudy.worker")

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
    """Two parallel lanes, so the heavy (generation) model and a lighter
    (enrich/translate/report) model can run on Ollama at the same time.

    Each lane awaits at most one LLM call, so the app never has more than two
    models in flight. (To also cap how many models Ollama keeps *resident*,
    set OLLAMA_MAX_LOADED_MODELS=2 on the Ollama host.)
    """
    with db.connect() as con:
        con.execute("UPDATE topics SET status='queued', progress_pct=0 WHERE status='processing'")
        con.execute("UPDATE topic_revisions SET status='queued' WHERE status='processing'")
        con.execute("UPDATE card_reevals SET status='queued' WHERE status='processing'")
    log.info("Worker started: heavy + light lanes (report hour: %02d:00)", REPORT_HOUR)
    await asyncio.gather(_heavy_loop(), _light_loop())


async def _heavy_loop():
    """Topic generation, natural-language revisions, nightly fresh questions."""
    while True:
        try:
            topic = _next_queued()
            if topic:
                await _process(topic)
                continue
            if await _process_revision():
                continue
            if await _maybe_refresh_topics():
                continue
            await asyncio.sleep(POLL_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Heavy lane error")
            await asyncio.sleep(POLL_INTERVAL)


async def _light_loop():
    """Enrichment, translations, card disputes and weakness reports."""
    while True:
        try:
            if await _process_reeval():  # user-triggered disputes take priority
                continue
            if await _categorize_step():
                continue
            if await _enrich_step():
                continue
            await _maybe_send_reports()
            await asyncio.sleep(POLL_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Light lane error")
            await asyncio.sleep(POLL_INTERVAL)


def _next_queued():
    # Admin-controllable queue: lower queue_priority first, then FIFO; paused topics wait.
    with db.connect() as con:
        return db.one(
            con,
            """SELECT * FROM topics WHERE status='queued' AND paused=0
               ORDER BY queue_priority, id LIMIT 1""",
        )


def _is_cancelled(topic_id: int) -> bool:
    with db.connect() as con:
        row = db.one(con, "SELECT cancel_requested FROM topics WHERE id=?", (topic_id,))
    return bool(row and row["cancel_requested"])


def _ollama_actor(con, user, task: str | None = None):
    """Overlay the admin-managed global Ollama connection (with the task-specific
    model, if configured) onto a user dict, so the LLM client always uses the
    shared endpoint regardless of who owns the topic."""
    return {**user, **db.ollama_config(con, task)} if user else user


def _insert_card(con, topic_id: int, unit_index: int, lang: str, card: dict):
    con.execute(
        """INSERT INTO cards (topic_id, unit_index, type, question, answer,
           choices_json, explanation, difficulty, lang, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (topic_id, unit_index, card["type"], card["question"], card["answer"],
         json.dumps(card["choices"], ensure_ascii=False),
         card["explanation"], card["difficulty"], lang, db.now()),
    )


def _update(topic_id: int, **fields):
    cols = ", ".join(f"{k}=?" for k in fields)
    with db.connect() as con:
        con.execute(f"UPDATE topics SET {cols} WHERE id=?", (*fields.values(), topic_id))


# ------------------------------------------------------------- core generation

async def _process(topic: dict):
    topic_id = topic["id"]
    with db.connect() as con:
        user = _ollama_actor(con, db.one(con, "SELECT * FROM users WHERE id=?", (topic["user_id"],)), task="generate")
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
        plan = await _await_or_stop(llm.generate_plan(user, topic, sources_text), topic_id)
        _update(topic_id, title=str(plan.get("title", ""))[:120],
                plan_json=json.dumps(plan, ensure_ascii=False))

        units = plan["units"]
        per_unit = llm.cards_per_unit(topic["card_count"], len(units))
        total_cards = 0
        for i in range(len(units)):
            if _is_cancelled(topic_id):
                _update(topic_id, status="stopped", progress_msg="", progress_pct=0,
                        cancel_requested=0, error="Stopped by admin")
                log.info("Topic %s cancelled mid-generation", topic_id)
                return
            _update(topic_id, progress_msg=f"generating_unit:{i + 1}/{len(units)}",
                    progress_pct=15 + int(80 * i / len(units)))
            try:
                cards = await _await_or_stop(
                    llm.generate_unit_cards(user, topic, plan, i, per_unit, sources_text),
                    topic_id)
            except llm.OllamaError as e:
                if i == 0:
                    raise
                log.warning("Unit %s of topic %s failed, keeping partial deck: %s", i, topic_id, e)
                continue
            with db.connect() as con:
                for card in cards:
                    _insert_card(con, topic_id, i, topic["language"], card)
            total_cards += len(cards)

        if total_cards == 0:
            raise llm.OllamaError("The model produced no usable flashcards.")

        _update(topic_id, status="ready", progress_msg="", progress_pct=100, ready_at=db.now())
        log.info("Topic %s ready: %s cards in %s units", topic_id, total_cards, len(units))
        topic["title"] = plan.get("title", topic["prompt"][:60])
        await emailer.send_topic_ready(user, topic, total_cards, len(units))

    except _Stopped:
        # Admin stop aborted the in-flight LLM call (GPU freed immediately).
        _update(topic_id, status="stopped", progress_msg="", progress_pct=0,
                cancel_requested=0, error="Stopped by admin")
        log.info("Topic %s stopped mid-call by admin", topic_id)
    except Exception as e:
        message = str(e) if isinstance(e, llm.OllamaError) else f"Unexpected error: {e}"
        log.exception("Topic %s failed", topic_id)
        _update(topic_id, status="failed", error=message[:500], progress_pct=0)
        await emailer.send_topic_failed(user, topic, message[:500])


# ------------------------------------------------------------- card disputes

async def _process_reeval() -> bool:
    """Re-evaluate one disputed card: critically re-check it against fresh web
    evidence and rewrite it in place, then let it re-enrich/re-translate."""
    with db.connect() as con:
        rev = db.one(con, "SELECT * FROM card_reevals WHERE status='queued' ORDER BY id LIMIT 1")
        if not rev:
            return False
        card = db.one(con, "SELECT * FROM cards WHERE id=?", (rev["card_id"],))
        topic = db.one(con, "SELECT * FROM topics WHERE id=?", (rev["topic_id"],))
        disputer = db.one(con, "SELECT * FROM users WHERE id=?", (rev["user_id"],))
        owner = _ollama_actor(con, db.one(con, "SELECT * FROM users WHERE id=?",
                                          (topic["user_id"],)) if topic else None, task="generate")
        con.execute("UPDATE card_reevals SET status='processing' WHERE id=?", (rev["id"],))
    if not card or not topic:
        with db.connect() as con:
            con.execute("UPDATE card_reevals SET status='failed', result_msg='card gone' WHERE id=?",
                        (rev["id"],))
        return True

    card_view = {
        "type": card["type"], "question": card["question"], "answer": card["answer"],
        "choices": json.loads(card["choices_json"]) if card["choices_json"] else [],
        "explanation": card["explanation"],
    }
    try:
        results = await websearch.search(f"{topic['title']} {card['question'][:120]}")
        data = await llm.reevaluate_card(owner, topic, card_view, rev["context"], results)
        new = data["card"]
        with db.connect() as con:
            # Rewrite the card and clear derived content so the pipeline regenerates
            # the deep explanation and translations for the corrected version.
            con.execute(
                """UPDATE cards SET question=?, answer=?, choices_json=?, explanation=?,
                   difficulty=?, long_explanation='', sources_json='', translations_json=''
                   WHERE id=?""",
                (new["question"], new["answer"], json.dumps(new["choices"], ensure_ascii=False),
                 new["explanation"], new["difficulty"], card["id"]),
            )
            # The disputer's old progress on this card is stale now — reset it so the
            # corrected card comes back for review.
            con.execute("DELETE FROM card_progress WHERE card_id=?", (card["id"],))
            con.execute("UPDATE card_reevals SET status='done', result_msg=? WHERE id=?",
                        (data["note"][:400], rev["id"]))
        log.info("Re-evaluated card %s (topic %s)", card["id"], topic["id"])
        if disputer and disputer["email_notifications"] and not disputer["disabled"]:
            emailer.send_notice_sync(
                disputer["email"], disputer["language"], "card_reevaluated",
                link_path=f"/#/topic/{topic['id']}", name=disputer["name"],
                title=topic["title"] or topic["prompt"][:60],
                note=data["note"][:400] or "—")
    except Exception as e:
        msg = str(e) if isinstance(e, llm.OllamaError) else f"Unexpected error: {e}"
        log.exception("Re-eval %s failed", rev["id"])
        with db.connect() as con:
            con.execute("UPDATE card_reevals SET status='failed', result_msg=? WHERE id=?",
                        (msg[:300], rev["id"]))
    return True


# ------------------------------------------------------------- revisions

async def _process_revision() -> bool:
    """Apply one queued natural-language deck edit (add/remove cards)."""
    with db.connect() as con:
        rev = db.one(con, "SELECT * FROM topic_revisions WHERE status='queued' ORDER BY id LIMIT 1")
        if not rev:
            return False
        topic = db.one(con, "SELECT * FROM topics WHERE id=?", (rev["topic_id"],))
        user = _ollama_actor(con, db.one(con, "SELECT * FROM users WHERE id=?", (rev["user_id"],)), task="generate")
        con.execute("UPDATE topic_revisions SET status='processing' WHERE id=?", (rev["id"],))
    if not topic or not user or not topic["plan_json"]:
        with db.connect() as con:
            con.execute("UPDATE topic_revisions SET status='failed', result_msg=? WHERE id=?",
                        ("Topic unavailable", rev["id"]))
        return True

    plan = json.loads(topic["plan_json"])
    try:
        with db.connect() as con:
            cards = db.all_rows(
                con, "SELECT id, unit_index, question FROM cards WHERE topic_id=? ORDER BY id",
                (topic["id"],))
            srcs = db.all_rows(con, "SELECT * FROM sources WHERE topic_id=?", (topic["id"],))
        decision = await llm.plan_revision(user, topic, plan, cards, rev["instruction"])

        removed = 0
        if decision["remove_ids"]:
            with db.connect() as con:
                con.execute(
                    "DELETE FROM cards WHERE topic_id=? AND id IN (%s)"
                    % ",".join("?" * len(decision["remove_ids"])),
                    (topic["id"], *decision["remove_ids"]),
                )
                removed = con.execute("SELECT changes()").fetchone()[0]

        added = 0
        if decision["add_count"] > 0:
            unit_idx = decision["add_unit_index"]
            # Inject the requested focus into the unit so generation targets it.
            unit = dict(plan["units"][unit_idx])
            if decision["add_focus"]:
                unit = {**unit, "title": decision["add_focus"] or unit.get("title", ""),
                        "objectives": [decision["add_focus"]] + unit.get("objectives", [])}
            synth_plan = {**plan, "units": [unit]}
            existing_q = [c["question"] for c in cards]
            new_cards = await llm.generate_unit_cards(
                user, topic, synth_plan, 0, decision["add_count"],
                extract.combine_sources(srcs), avoid_questions=existing_q)
            with db.connect() as con:
                for card in new_cards:
                    _insert_card(con, topic["id"], unit_idx, topic["language"], card)
            added = len(new_cards)

        summary = decision["summary"] or f"+{added} / -{removed} cards"
        result = f"{summary} (added {added}, removed {removed})"
        with db.connect() as con:
            con.execute("UPDATE topic_revisions SET status='done', result_msg=? WHERE id=?",
                        (result, rev["id"]))
        log.info("Revision %s on topic %s: %s", rev["id"], topic["id"], result)
    except Exception as e:
        msg = str(e) if isinstance(e, llm.OllamaError) else f"Unexpected error: {e}"
        log.exception("Revision %s failed", rev["id"])
        with db.connect() as con:
            con.execute("UPDATE topic_revisions SET status='failed', result_msg=? WHERE id=?",
                        (msg[:300], rev["id"]))
    return True


# ------------------------------------------------------------- enrichment

def _record_failure(key: str) -> bool:
    """Count a failure; True once the item should be marked failed and skipped."""
    _fail_counts[key] = _fail_counts.get(key, 0) + 1
    if _fail_counts[key] >= MAX_FAILS:
        del _fail_counts[key]
        return True
    return False


def background_paused() -> bool:
    with db.connect() as con:
        return db.get_setting(con, "background_paused", "0") == "1"


class _Paused(Exception):
    """Raised when a pause is requested mid-item, to abort it without saving."""


def _enrich_halted(topic_id: int) -> bool:
    with db.connect() as con:
        if db.get_setting(con, "background_paused", "0") == "1":
            return True
        row = db.one(con, "SELECT enrich_paused FROM topics WHERE id=?", (topic_id,))
        return bool(row and row["enrich_paused"])


class _Stopped(Exception):
    """Raised when an admin stop request aborts an in-flight generation call."""


async def _await_abortable(coro, stop_check, exc_type):
    """Await an LLM call, but cancel it the moment stop_check() turns true.

    Cancelling drops the httpx connection so Ollama stops generating (freeing the
    GPU). The partial result is discarded; because we only persist AFTER this
    returns, an interrupted item simply stays pending and is redone later.
    """
    task = asyncio.ensure_future(coro)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=1.0)
            if task in done:
                return task.result()
            if stop_check():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise exc_type()
    except asyncio.CancelledError:
        task.cancel()
        raise


async def _await_or_pause(coro, topic_id: int):
    return await _await_abortable(coro, lambda: _enrich_halted(topic_id), _Paused)


async def _await_or_stop(coro, topic_id: int):
    return await _await_abortable(coro, lambda: _is_cancelled(topic_id), _Stopped)


async def _categorize_step() -> bool:
    """Assign a catalogue category to one ready topic that lacks one (cheap call)."""
    if background_paused():
        return False
    with db.connect() as con:
        topic = db.one(
            con,
            """SELECT * FROM topics WHERE status='ready' AND category='' AND plan_json!=''
               ORDER BY id DESC LIMIT 1""",
        )
        if not topic:
            return False
        actor = _ollama_actor(con, db.one(con, "SELECT * FROM users WHERE id=?",
                                          (topic["user_id"],)), task="enrich")
    plan = json.loads(topic["plan_json"])
    key = f"cat:{topic['id']}"
    try:
        category = await llm.categorize_topic(
            actor, plan.get("title", topic["title"]), plan.get("overview", ""))
        with db.connect() as con:
            con.execute("UPDATE topics SET category=? WHERE id=?", (category, topic["id"]))
        _fail_counts.pop(key, None)
        log.info("Categorized topic %s as %s", topic["id"], category)
    except Exception as e:
        log.warning("Categorizing topic %s failed: %s", topic["id"], e)
        if _record_failure(key):
            with db.connect() as con:
                con.execute("UPDATE topics SET category='Other' WHERE id=?", (topic["id"],))
        else:
            await asyncio.sleep(POLL_INTERVAL)
    return True


async def _enrich_step() -> bool:
    """Do one small chunk of enrichment work. Returns True if something was attempted."""
    if background_paused():
        return False
    with db.connect() as con:
        topic = db.one(
            con,
            """SELECT t.*, u.id AS uid FROM topics t JOIN users u ON u.id=t.user_id
               WHERE t.status='ready' AND t.plan_json != '' AND t.enrich_paused=0 AND (
                 t.material_json = ''
                 OR EXISTS (SELECT 1 FROM cards c WHERE c.topic_id=t.id AND c.sources_json='')
                 OR EXISTS (SELECT 1 FROM cards c WHERE c.topic_id=t.id
                            AND c.sources_json != '' AND c.translations_json='')
                 OR t.content_translated = 0
               ) ORDER BY COALESCE(t.ready_at, 0) DESC, t.id DESC LIMIT 1""",
        )
        if not topic:
            return False
        base_user = db.one(con, "SELECT * FROM users WHERE id=?", (topic["user_id"],))
        # Phases 1+2 (material, explanations) and phase 3 (translation) may run
        # on different models — e.g. a small fast model for translation.
        user = _ollama_actor(con, base_user, task="enrich")
        translate_user = _ollama_actor(con, base_user, task="translate")

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
            entry = await _await_or_pause(llm.generate_unit_material(
                user, topic, plan, idx, results, extract.combine_sources(srcs)), topic["id"])
            material.append(entry)
            _fail_counts.pop(key, None)
            log.info("Material for topic %s unit %s done (%s sources)",
                     topic["id"], idx, len(entry["sources"]))
        except _Paused:
            return True  # discard the partial unit; redo it on resume
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
    if cards:
        with db.connect() as con:
            remaining = db.one(
                con, "SELECT COUNT(*) AS c FROM cards WHERE topic_id=? AND sources_json=''",
                (topic["id"],))["c"]
        _update(topic["id"], progress_msg=f"enriching_cards:{remaining}")
        for card in cards:
            key = f"card:{card['id']}"
            try:
                results = await websearch.search(f"{topic['title']} {card['question'][:120]}")
                data = await _await_or_pause(llm.enrich_card(user, topic, card, results),
                                             topic["id"])
                with db.connect() as con:
                    con.execute(
                        "UPDATE cards SET long_explanation=?, sources_json=? WHERE id=?",
                        (data["explanation"], json.dumps(data["sources"], ensure_ascii=False),
                         card["id"]),
                    )
                _fail_counts.pop(key, None)
            except _Paused:
                return True  # this card stays pending; resume picks it up again
            except Exception as e:
                log.warning("Enriching card %s failed: %s", card["id"], e)
                if _record_failure(key):
                    with db.connect() as con:
                        con.execute("UPDATE cards SET sources_json='[]' WHERE id=?", (card["id"],))
                else:
                    await asyncio.sleep(POLL_INTERVAL)
                    return True
        if remaining <= len(cards):
            log.info("Enrichment for topic %s complete", topic["id"])
        return True

    # Phase 3: translate each card into the other language (so the UI can show the
    # whole deck — questions, answers, explanations — in German or English).
    with db.connect() as con:
        cards = db.all_rows(
            con,
            """SELECT * FROM cards WHERE topic_id=? AND sources_json != ''
               AND translations_json='' ORDER BY id LIMIT ?""",
            (topic["id"], ENRICH_CARDS_PER_STEP),
        )
        remaining = db.one(
            con,
            """SELECT COUNT(*) AS c FROM cards WHERE topic_id=? AND sources_json != ''
               AND translations_json=''""",
            (topic["id"],))["c"]
    if cards:
        _update(topic["id"], progress_msg=f"translating_cards:{remaining}")
        for card in cards:
            key = f"trans:{card['id']}"
            base_lang = card["lang"] or topic["language"]
            target = llm.other_lang(base_lang)
            try:
                translated = await _await_or_pause(
                    llm.translate_card(translate_user, card, target), topic["id"])
                with db.connect() as con:
                    con.execute(
                        "UPDATE cards SET translations_json=? WHERE id=?",
                        (json.dumps({target: translated}, ensure_ascii=False), card["id"]),
                    )
                _fail_counts.pop(key, None)
            except _Paused:
                return True  # leave this card untranslated; resume re-does it
            except Exception as e:
                log.warning("Translating card %s failed: %s", card["id"], e)
                if _record_failure(key):
                    # Mark as attempted so we stop retrying; UI falls back to base language.
                    with db.connect() as con:
                        con.execute("UPDATE cards SET translations_json='{}' WHERE id=?",
                                    (card["id"],))
                else:
                    await asyncio.sleep(POLL_INTERVAL)
                    return True
        if remaining <= len(cards):
            log.info("Card translation for topic %s complete", topic["id"])
        return True

    # Phase 4: translate topic-level content — title, study plan, learning
    # material — so the whole topic page follows the user's language toggle.
    if not topic["content_translated"]:
        target = llm.other_lang(topic["language"])
        trans = json.loads(topic["translations_json"]) if topic["translations_json"] else {}
        entry = trans.get(target) or {}

        def _save(done: bool):
            trans[target] = entry
            fields = {"translations_json": json.dumps(trans, ensure_ascii=False),
                      "content_translated": 1 if done else 0}
            if done:
                fields["progress_msg"] = ""
            _update(topic["id"], **fields)

        if "plan" not in entry:
            _update(topic["id"], progress_msg="translating_content:plan")
            key = f"cplan:{topic['id']}"
            try:
                translated_plan = await _await_or_pause(
                    llm.translate_plan(translate_user, plan, target), topic["id"])
                entry["plan"] = translated_plan
                entry["title"] = str(translated_plan.get("title", ""))[:120]
                _fail_counts.pop(key, None)
            except _Paused:
                return True
            except Exception as e:
                log.warning("Plan translation for topic %s failed: %s", topic["id"], e)
                if _record_failure(key):
                    entry["plan"] = {}  # attempted; UI falls back to base language
                else:
                    await asyncio.sleep(POLL_INTERVAL)
                    return True
            _save(done=False)
            return True

        mat_t = entry.get("material") or []
        if len(mat_t) < len(material):
            idx = len(mat_t)
            source_entry = material[idx]
            _update(topic["id"],
                    progress_msg=f"translating_content:{idx + 1}/{len(material)}")
            if not source_entry.get("text"):
                mat_t.append({})  # failed/empty unit: keep indexes aligned
            else:
                key = f"cmat:{topic['id']}:{idx}"
                try:
                    mat_t.append(await _await_or_pause(
                        llm.translate_material_unit(translate_user, source_entry, target),
                        topic["id"]))
                    _fail_counts.pop(key, None)
                except _Paused:
                    return True
                except Exception as e:
                    log.warning("Material translation %s/%s failed: %s", topic["id"], idx, e)
                    if _record_failure(key):
                        mat_t.append({})
                    else:
                        await asyncio.sleep(POLL_INTERVAL)
                        return True
            entry["material"] = mat_t
            done = len(mat_t) >= len(material)
            _save(done=done)
            if done:
                log.info("Content translation for topic %s complete", topic["id"])
            return True

        _save(done=True)
        log.info("Content translation for topic %s complete", topic["id"])
        return True

    _update(topic["id"], progress_msg="")
    return True


# ------------------------------------------------------------- nightly refresh

REFRESH_BATCH = 8
# Nightly refresh stops growing a deck once it reaches this multiple of the
# originally requested size — otherwise decks inflate by 8 cards forever.
REFRESH_CAP_FACTOR = 3

# Mastery-driven plan deepening: when a learner has answered a card correctly in
# at least this many separate rounds (streak), it counts as "mastered". Once a
# learner masters this fraction of a deck's cards, the nightly job extends the
# study plan with deeper/neighbouring units instead of just drilling weak spots.
MASTERY_STREAK = 2
DEEPEN_THRESHOLD = 0.75
MAX_PLAN_UNITS = 12


def _top_mastery(con, topic_id: int, total_cards: int):
    """Return (user_id, fraction_mastered) for the strongest learner on a topic."""
    if not total_cards:
        return None, 0.0
    row = db.one(
        con,
        """SELECT p.user_id, COUNT(*) AS mastered
           FROM card_progress p JOIN cards c ON c.id = p.card_id
           WHERE c.topic_id = ? AND p.streak >= ?
           GROUP BY p.user_id ORDER BY mastered DESC LIMIT 1""",
        (topic_id, MASTERY_STREAK),
    )
    if not row:
        return None, 0.0
    return row["user_id"], row["mastered"] / total_cards


async def _deepen_plan(topic: dict, plan: dict, actor: dict, trigger_user_id: int,
                       all_questions: list[str], srcs: list[dict]) -> bool:
    """Append 1 deeper/neighbouring unit to a mastered plan and generate its cards.

    Adding a unit dilutes the mastery fraction, so the trigger won't re-fire until
    the learner masters the larger plan too — naturally self-limiting, bounded by
    MAX_PLAN_UNITS.
    """
    new_units = await llm.deepen_plan(actor, topic, plan, n_new=1)
    base = len(plan["units"])
    plan["units"].extend(new_units)
    with db.connect() as con:
        # Persist the expanded plan and force content re-translation (new units +
        # their learning material need translating); material auto-generates via
        # the enrichment pipeline since plan now has more units than material.
        con.execute("UPDATE topics SET plan_json=?, content_translated=0 WHERE id=?",
                    (json.dumps(plan, ensure_ascii=False), topic["id"]))
    total_new = 0
    for offset in range(len(new_units)):
        idx = base + offset
        cards = await llm.generate_unit_cards(
            actor, topic, plan, idx, llm.cards_per_unit(topic["card_count"], base or 1),
            extract.combine_sources(srcs), avoid_questions=all_questions[-60:])
        with db.connect() as con:
            for card in cards:
                _insert_card(con, topic["id"], idx, topic["language"], card)
        total_new += len(cards)
    with db.connect() as con:
        con.execute("UPDATE topics SET last_refresh_at=? WHERE id=?", (db.now(), topic["id"]))
        learner = db.one(con, "SELECT * FROM users WHERE id=?", (trigger_user_id,))
    log.info("Deepened topic %s: +%s unit(s), +%s cards", topic["id"], len(new_units), total_new)
    if learner and learner["email_notifications"] and not learner["disabled"]:
        emailer.send_notice_sync(
            learner["email"], learner["language"], "plan_deepened",
            link_path=f"/#/topic/{topic['id']}", name=learner["name"],
            title=topic["title"] or topic["prompt"][:60],
            unit=new_units[0].get("title", ""))
    return True


async def _maybe_refresh_topics() -> bool:
    """Generate a fresh batch of questions for one opted-in topic per night.

    Targets the unit the learner currently gets wrong most often (active-recall
    coaching: practice where it hurts); falls back to round-robin when there is
    no answer history. New cards enter the normal enrichment pipeline.
    """
    if background_paused():
        return False
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
        # Nightly refresh + plan deepening use the dedicated 'refresh' model.
        user = _ollama_actor(con, db.one(con, "SELECT * FROM users WHERE id=?", (topic["user_id"],)), task="refresh")
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
            all_questions = [r["question"] for r in db.all_rows(
                con, "SELECT question FROM cards WHERE topic_id=?", (topic["id"],))]
            srcs = db.all_rows(con, "SELECT * FROM sources WHERE topic_id=?", (topic["id"],))
            total_cards = len(all_questions)
            trigger_user, mastery = _top_mastery(con, topic["id"], total_cards)

        # If a learner has mastered the plan, grow the curriculum deeper instead of
        # just drilling weak spots (they have none). Bounded by MAX_PLAN_UNITS.
        if (mastery >= DEEPEN_THRESHOLD and len(plan["units"]) < MAX_PLAN_UNITS
                and trigger_user):
            log.info("Topic %s: learner %s at %.0f%% mastery -> deepening plan",
                     topic["id"], trigger_user, mastery * 100)
            await _deepen_plan(topic, plan, user, trigger_user, all_questions, srcs)
            _fail_counts.pop(key, None)
            return True

        if len(all_questions) >= topic["card_count"] * REFRESH_CAP_FACTOR:
            log.info("Nightly refresh: topic %s at cap (%s cards), skipping",
                     topic["id"], len(all_questions))
            with db.connect() as con:
                con.execute("UPDATE topics SET last_refresh_at=? WHERE id=?",
                            (db.now(), topic["id"]))
            return True
        unit_index = weak["unit_index"] if weak and weak["w"] else \
            int(now.timestamp() // 86400) % len(plan["units"])
        cards = await llm.generate_unit_cards(
            user, topic, plan, unit_index, REFRESH_BATCH,
            extract.combine_sources(srcs), avoid_questions=all_questions[-60:],
        )
        # Belt-and-braces dedup: the prompt asks for new angles, but models repeat.
        seen = {q.strip().lower() for q in all_questions}
        cards = [c for c in cards if c["question"].strip().lower() not in seen]
        with db.connect() as con:
            for card in cards:
                _insert_card(con, topic["id"], unit_index, topic["language"], card)
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
        with db.connect() as con:
            actor = _ollama_actor(con, user, task="report")
        body = await llm.generate_weakness_report(actor, cards_block)
    except Exception as e:
        log.warning("LLM report for user %s failed (%s), using template fallback", user["id"], e)
        body = emailer.fallback_report_body(user, weak)

    if source_lines:
        body += "\n\n" + emailer.sources_heading(user) + "\n" + "\n".join(source_lines[:12])
    await emailer.send_weakness_report(user, body, len(weak))
    with db.connect() as con:
        con.execute("UPDATE users SET last_report_at=? WHERE id=?", (db.now(), user["id"]))
    log.info("Sent weakness report to %s (%s weak cards)", user["email"], len(weak))