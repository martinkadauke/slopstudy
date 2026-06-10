"""FlashDeck — self-hosted AI flashcard study app (single container)."""
import asyncio
import json
import logging
import os
import random
import re
import secrets
import unicodedata
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from . import auth, db, emailer, gamification as game, llm, worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("flashdeck")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
SESSION_SIZE_DEFAULT = 10
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    task = asyncio.create_task(worker.run_forever())
    yield
    task.cancel()


app = FastAPI(title="FlashDeck", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- auth

class RegisterBody(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=200)
    language: str = "en"


class LoginBody(BaseModel):
    email: EmailStr
    password: str


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(
        "fd_session", token, httponly=True, samesite="lax",
        secure=COOKIE_SECURE, max_age=auth.TOKEN_TTL,
    )


@app.post("/api/register")
def register(body: RegisterBody, response: Response):
    language = body.language if body.language in ("en", "de") else "en"
    with db.connect() as con:
        if db.one(con, "SELECT id FROM users WHERE email=?", (body.email,)):
            raise HTTPException(409, "email_taken")
        cur = con.execute(
            """INSERT INTO users (email, name, password_hash, language, created_at)
               VALUES (?,?,?,?,?)""",
            (body.email, body.name.strip(), auth.hash_password(body.password),
             language, db.now()),
        )
        user_id = cur.lastrowid
    _set_session_cookie(response, auth.create_token(user_id))
    return {"ok": True}


@app.post("/api/login")
def login(body: LoginBody, response: Response):
    with db.connect() as con:
        user = db.one(con, "SELECT * FROM users WHERE email=?", (body.email,))
    if not user or not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "invalid_credentials")
    _set_session_cookie(response, auth.create_token(user["id"]))
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("fd_session")
    if token:
        auth.revoke_token(token)
    response.delete_cookie("fd_session")
    return {"ok": True}


# ---------------------------------------------------------------- profile / settings

def _public_user(user: dict) -> dict:
    info = game.level_info(user["lifetime_points"])
    return {
        "id": user["id"], "email": user["email"], "name": user["name"],
        "language": user["language"], "theme": user["theme"],
        "ollama_url": user["ollama_url"], "ollama_model": user["ollama_model"],
        "ollama_api_key_set": bool(user["ollama_api_key"]),
        "email_notifications": bool(user["email_notifications"]),
        "points": user["points"], "lifetime_points": user["lifetime_points"],
        "level": info, "smtp_enabled": emailer.smtp_configured(),
    }


@app.get("/api/me")
def me(user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        full = db.one(con, "SELECT * FROM users WHERE id=?", (user["id"],))
        streak = game.current_streak(con, user["id"])
    out = _public_user(full)
    out["streak"] = streak
    return out


class ProfileBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr | None = None
    language: str | None = None
    theme: str | None = None
    email_notifications: bool | None = None


@app.put("/api/me")
def update_profile(body: ProfileBody, user: dict = Depends(auth.current_user)):
    updates = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.email is not None:
        updates["email"] = body.email
    if body.language in ("en", "de"):
        updates["language"] = body.language
    if body.theme in ("dark", "light"):
        updates["theme"] = body.theme
    if body.email_notifications is not None:
        updates["email_notifications"] = int(body.email_notifications)
    if not updates:
        return {"ok": True}
    with db.connect() as con:
        if "email" in updates:
            other = db.one(con, "SELECT id FROM users WHERE email=? AND id!=?",
                           (updates["email"], user["id"]))
            if other:
                raise HTTPException(409, "email_taken")
        cols = ", ".join(f"{k}=?" for k in updates)
        con.execute(f"UPDATE users SET {cols} WHERE id=?", (*updates.values(), user["id"]))
    return {"ok": True}


class PasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


@app.put("/api/me/password")
def change_password(body: PasswordBody, user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        full = db.one(con, "SELECT password_hash FROM users WHERE id=?", (user["id"],))
        if not auth.verify_password(body.current_password, full["password_hash"]):
            raise HTTPException(403, "wrong_password")
        con.execute("UPDATE users SET password_hash=? WHERE id=?",
                    (auth.hash_password(body.new_password), user["id"]))
    return {"ok": True}


class OllamaBody(BaseModel):
    ollama_url: str = Field(min_length=1, max_length=300)
    ollama_model: str = Field(min_length=1, max_length=100)
    ollama_api_key: str | None = None  # None = keep existing


@app.put("/api/me/ollama")
def update_ollama(body: OllamaBody, user: dict = Depends(auth.current_user)):
    if not re.match(r"^https?://", body.ollama_url):
        raise HTTPException(422, "invalid_url")
    with db.connect() as con:
        con.execute("UPDATE users SET ollama_url=?, ollama_model=? WHERE id=?",
                    (body.ollama_url.rstrip("/"), body.ollama_model.strip(), user["id"]))
        if body.ollama_api_key is not None:
            con.execute("UPDATE users SET ollama_api_key=? WHERE id=?",
                        (body.ollama_api_key.strip(), user["id"]))
    return {"ok": True}


@app.post("/api/ollama/test")
async def test_ollama(user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        full = db.one(con, "SELECT * FROM users WHERE id=?", (user["id"],))
    try:
        return await llm.test_connection(full)
    except llm.OllamaError as e:
        return JSONResponse(status_code=502, content={"ok": False, "error": str(e)})


# ---------------------------------------------------------------- topics

VALID_MODES = ("multiple_choice", "exact", "yes_no", "exam")


@app.post("/api/topics")
async def create_topic(
    user: dict = Depends(auth.current_user),
    prompt: str = Form(..., min_length=3, max_length=4000),
    mode: str = Form("multiple_choice"),
    card_count: int = Form(40),
    language: str = Form("en"),
    urls: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    if mode not in VALID_MODES:
        raise HTTPException(422, "invalid_mode")
    card_count = max(10, min(120, card_count))
    language = language if language in ("en", "de") else "en"
    url_list = [u.strip() for u in urls.splitlines() if u.strip()][:10]
    for u in url_list:
        if not re.match(r"^https?://", u):
            raise HTTPException(422, f"invalid_url:{u}")

    with db.connect() as con:
        cur = con.execute(
            """INSERT INTO topics (user_id, prompt, mode, card_count, language, status, created_at)
               VALUES (?,?,?,?,?, 'queued', ?)""",
            (user["id"], prompt.strip(), mode, card_count, language, db.now()),
        )
        topic_id = cur.lastrowid
        for u in url_list:
            con.execute("INSERT INTO sources (topic_id, kind, name) VALUES (?, 'url', ?)",
                        (topic_id, u))
        for f in files[:10]:
            ext = os.path.splitext(f.filename or "")[1].lower()
            if ext not in {".txt", ".md", ".pdf", ".docx", ".csv"}:
                raise HTTPException(422, f"unsupported_file_type:{ext or f.filename}")
            data = await f.read()
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"file_too_large:{f.filename}")
            safe_name = f"{topic_id}_{secrets.token_hex(6)}{ext}"
            path = os.path.join(db.UPLOAD_DIR, safe_name)
            with open(path, "wb") as fh:
                fh.write(data)
            con.execute(
                "INSERT INTO sources (topic_id, kind, name, file_path) VALUES (?, 'file', ?, ?)",
                (topic_id, f.filename, path),
            )
    return {"ok": True, "topic_id": topic_id}


def _topic_summary(con, topic: dict) -> dict:
    cards = db.one(con, "SELECT COUNT(*) AS c FROM cards WHERE topic_id=?", (topic["id"],))["c"]
    plan = json.loads(topic["plan_json"]) if topic["plan_json"] else None
    return {
        "id": topic["id"], "title": topic["title"] or topic["prompt"][:60],
        "prompt": topic["prompt"], "mode": topic["mode"], "language": topic["language"],
        "status": topic["status"], "progress_msg": topic["progress_msg"],
        "progress_pct": topic["progress_pct"], "error": topic["error"],
        "card_count": cards, "requested_cards": topic["card_count"],
        "units": len(plan["units"]) if plan else 0,
        "nightly_refresh": bool(topic["nightly_refresh"]),
        "created_at": topic["created_at"], "ready_at": topic["ready_at"],
    }


@app.get("/api/topics")
def list_topics(user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        topics = db.all_rows(
            con, "SELECT * FROM topics WHERE user_id=? ORDER BY id DESC", (user["id"],))
        return [_topic_summary(con, t) for t in topics]


def _own_topic(con, topic_id: int, user_id: int) -> dict:
    topic = db.one(con, "SELECT * FROM topics WHERE id=? AND user_id=?", (topic_id, user_id))
    if not topic:
        raise HTTPException(404, "topic_not_found")
    return topic


@app.get("/api/topics/{topic_id}")
def get_topic(topic_id: int, user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        topic = _own_topic(con, topic_id, user["id"])
        out = _topic_summary(con, topic)
        out["plan"] = json.loads(topic["plan_json"]) if topic["plan_json"] else None
        out["material"] = json.loads(topic["material_json"]) if topic["material_json"] else []
        out["sources"] = [
            {"kind": s["kind"], "name": s["name"]}
            for s in db.all_rows(con, "SELECT * FROM sources WHERE topic_id=?", (topic_id,))
        ]
        out["due_cards"] = _count_due(con, user["id"], topic_id)
        stats = db.one(
            con,
            """SELECT COUNT(*) AS sessions, COALESCE(SUM(points_earned),0) AS points
               FROM study_sessions WHERE topic_id=? AND user_id=? AND finished_at IS NOT NULL""",
            (topic_id, user["id"]),
        )
        out["stats"] = stats
        return out


class TopicSettingsBody(BaseModel):
    nightly_refresh: bool


@app.put("/api/topics/{topic_id}")
def update_topic(topic_id: int, body: TopicSettingsBody,
                 user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        _own_topic(con, topic_id, user["id"])
        con.execute("UPDATE topics SET nightly_refresh=? WHERE id=?",
                    (int(body.nightly_refresh), topic_id))
    return {"ok": True}


@app.delete("/api/topics/{topic_id}")
def delete_topic(topic_id: int, user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        _own_topic(con, topic_id, user["id"])
        for s in db.all_rows(con, "SELECT file_path FROM sources WHERE topic_id=?", (topic_id,)):
            if s["file_path"] and os.path.exists(s["file_path"]):
                os.remove(s["file_path"])
        con.execute("DELETE FROM topics WHERE id=?", (topic_id,))
    return {"ok": True}


@app.post("/api/topics/{topic_id}/retry")
def retry_topic(topic_id: int, user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        topic = _own_topic(con, topic_id, user["id"])
        if topic["status"] != "failed":
            raise HTTPException(409, "not_failed")
        con.execute("DELETE FROM cards WHERE topic_id=?", (topic_id,))
        con.execute(
            "UPDATE topics SET status='queued', error='', progress_pct=0, plan_json='' WHERE id=?",
            (topic_id,),
        )
    return {"ok": True}


# ---------------------------------------------------------------- study sessions

def _count_due(con, user_id: int, topic_id: int) -> int:
    return db.one(
        con,
        """SELECT COUNT(*) AS c FROM cards c
           LEFT JOIN card_progress p ON p.card_id = c.id AND p.user_id = ?
           WHERE c.topic_id = ? AND (p.card_id IS NULL OR p.due_at <= ?)""",
        (user_id, topic_id, db.now()),
    )["c"]


def _card_payload(card: dict, reveal: bool = False) -> dict:
    out = {
        "id": card["id"], "type": card["type"], "question": card["question"],
        "difficulty": card["difficulty"],
        "choices": json.loads(card["choices_json"]) if card["choices_json"] else [],
        "skip_cost": game.skip_cost(card["difficulty"]),
        "fifty_cost": game.fifty_cost(card["difficulty"]),
        "points_correct": game.points_correct(card["difficulty"]),
        "points_wrong": game.points_wrong(card["difficulty"]),
        "unit_index": card["unit_index"],
    }
    if reveal:
        out["answer"] = card["answer"]
        out["explanation"] = card["explanation"]
    return out


class StartSessionBody(BaseModel):
    topic_id: int
    size: int = SESSION_SIZE_DEFAULT


@app.post("/api/sessions/start")
def start_session(body: StartSessionBody, user: dict = Depends(auth.current_user)):
    size = max(3, min(30, body.size))
    with db.connect() as con:
        topic = _own_topic(con, body.topic_id, user["id"])
        if topic["status"] != "ready":
            raise HTTPException(409, "topic_not_ready")
        # Due reviews and unseen cards first (unseen in plan order), then earliest-due refreshers.
        cards = db.all_rows(
            con,
            """SELECT c.*, COALESCE(p.due_at, 0) AS due_at, COALESCE(p.seen, 0) AS seen
               FROM cards c
               LEFT JOIN card_progress p ON p.card_id = c.id AND p.user_id = ?
               WHERE c.topic_id = ?
               ORDER BY (CASE WHEN p.card_id IS NULL THEN 0
                              WHEN p.due_at <= ? THEN 1 ELSE 2 END),
                        c.unit_index, p.due_at, c.id
               LIMIT ?""",
            (user["id"], body.topic_id, db.now(), size),
        )
        if not cards:
            raise HTTPException(409, "no_cards")
        cur = con.execute(
            """INSERT INTO study_sessions (user_id, topic_id, card_ids_json, started_at)
               VALUES (?,?,?,?)""",
            (user["id"], body.topic_id, json.dumps([c["id"] for c in cards]), db.now()),
        )
        session_id = cur.lastrowid
        points = db.one(con, "SELECT points FROM users WHERE id=?", (user["id"],))["points"]
    return {
        "session_id": session_id,
        "topic_title": topic["title"] or topic["prompt"][:60],
        # Self-graded 'open' cards need the model answer client-side at reveal time.
        "cards": [_card_payload(c, reveal=(c["type"] == "open")) for c in cards],
        "points": points,
    }


def _own_open_session(con, session_id: int, user_id: int) -> dict:
    session = db.one(con, "SELECT * FROM study_sessions WHERE id=? AND user_id=?",
                     (session_id, user_id))
    if not session:
        raise HTTPException(404, "session_not_found")
    if session["finished_at"]:
        raise HTTPException(409, "session_finished")
    return session


def _normalize_answer(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower().strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text)


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _check_answer(card: dict, given: str, self_grade: bool | None) -> bool:
    expected = card["answer"]
    if card["type"] == "open":
        return bool(self_grade)
    if card["type"] == "multiple_choice":
        return given.strip() == expected.strip()
    if card["type"] == "yes_no":
        return _normalize_answer(given) in ("yes", "ja") if expected == "yes" \
            else _normalize_answer(given) in ("no", "nein")
    # exact: normalized comparison with small typo tolerance on longer answers
    a, b = _normalize_answer(given), _normalize_answer(expected)
    if a == b:
        return True
    tolerance = 1 if len(b) >= 6 else 0
    if len(b) >= 12:
        tolerance = 2
    return tolerance > 0 and _levenshtein(a, b) <= tolerance


def _log_answer(con, user_id: int, session: dict, card: dict, result: str):
    con.execute(
        """INSERT INTO answer_log (user_id, topic_id, card_id, session_id, result, answered_at)
           VALUES (?,?,?,?,?,?)""",
        (user_id, card["topic_id"], card["id"], session["id"], result, db.now()),
    )


def _record_progress(con, user_id: int, card: dict, result: str):
    progress = db.one(con, "SELECT * FROM card_progress WHERE user_id=? AND card_id=?",
                      (user_id, card["id"]))
    streak = progress["streak"] if progress else 0
    if result == "correct":
        streak += 1
        due = game.next_due(streak)
    elif result == "wrong":
        streak = 0
        due = db.now() + 600
    else:  # skipped
        due = db.now() + 3600
    con.execute(
        """INSERT INTO card_progress (user_id, card_id, streak, seen, due_at, last_result)
           VALUES (?,?,?,1,?,?)
           ON CONFLICT(user_id, card_id) DO UPDATE
           SET streak=excluded.streak, seen=seen+1, due_at=excluded.due_at,
               last_result=excluded.last_result""",
        (user_id, card["id"], streak, due, result),
    )


class AnswerBody(BaseModel):
    card_id: int
    answer: str = ""
    self_grade: bool | None = None  # for 'open' exam cards


@app.post("/api/sessions/{session_id}/answer")
def answer_card(session_id: int, body: AnswerBody, user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        session = _own_open_session(con, session_id, user["id"])
        card_ids = json.loads(session["card_ids_json"])
        answered = json.loads(session["answered_json"] or "{}")
        if body.card_id not in card_ids:
            raise HTTPException(404, "card_not_in_session")
        if str(body.card_id) in answered:
            raise HTTPException(409, "already_answered")
        card = db.one(con, "SELECT * FROM cards WHERE id=?", (body.card_id,))
        correct = _check_answer(card, body.answer, body.self_grade)
        delta = game.points_correct(card["difficulty"]) if correct \
            else game.points_wrong(card["difficulty"])
        new_points = game.apply_points(con, user["id"], delta)
        answered[str(body.card_id)] = "correct" if correct else "wrong"
        con.execute(
            "UPDATE study_sessions SET answered_json=?, points_earned=points_earned+? WHERE id=?",
            (json.dumps(answered), delta, session_id),
        )
        result = "correct" if correct else "wrong"
        _record_progress(con, user["id"], card, result)
        _log_answer(con, user["id"], session, card, result)
    return {
        "correct": correct, "points_delta": delta, "points": new_points,
        "answer": card["answer"], "explanation": card["explanation"],
        "long_explanation": card["long_explanation"],
        "web_sources": json.loads(card["sources_json"] or "[]"),
    }


class SkipBody(BaseModel):
    card_id: int


@app.post("/api/sessions/{session_id}/skip")
def skip_card(session_id: int, body: SkipBody, user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        session = _own_open_session(con, session_id, user["id"])
        card_ids = json.loads(session["card_ids_json"])
        answered = json.loads(session["answered_json"] or "{}")
        if body.card_id not in card_ids:
            raise HTTPException(404, "card_not_in_session")
        if str(body.card_id) in answered:
            raise HTTPException(409, "already_answered")
        card = db.one(con, "SELECT * FROM cards WHERE id=?", (body.card_id,))
        cost = game.skip_cost(card["difficulty"])
        balance = db.one(con, "SELECT points FROM users WHERE id=?", (user["id"],))["points"]
        if balance < cost:
            raise HTTPException(402, "not_enough_points")
        new_points = game.apply_points(con, user["id"], -cost)
        answered[str(body.card_id)] = "skipped"
        con.execute(
            "UPDATE study_sessions SET answered_json=?, points_earned=points_earned-? WHERE id=?",
            (json.dumps(answered), cost, session_id),
        )
        _record_progress(con, user["id"], card, "skipped")
        _log_answer(con, user["id"], session, card, "skipped")
    return {"skipped": True, "points_delta": -cost, "points": new_points}


class FiftyBody(BaseModel):
    card_id: int


@app.post("/api/sessions/{session_id}/fifty")
def fifty_joker(session_id: int, body: FiftyBody, user: dict = Depends(auth.current_user)):
    """Who-wants-to-be-a-millionaire 50:50: removes half the wrong choices."""
    with db.connect() as con:
        session = _own_open_session(con, session_id, user["id"])
        card_ids = json.loads(session["card_ids_json"])
        answered = json.loads(session["answered_json"] or "{}")
        jokers = json.loads(session["jokers_json"] or "{}")
        if body.card_id not in card_ids:
            raise HTTPException(404, "card_not_in_session")
        if str(body.card_id) in answered:
            raise HTTPException(409, "already_answered")
        if str(body.card_id) in jokers:
            raise HTTPException(409, "joker_used")
        card = db.one(con, "SELECT * FROM cards WHERE id=?", (body.card_id,))
        choices = json.loads(card["choices_json"] or "[]")
        if card["type"] != "multiple_choice" or len(choices) < 4:
            raise HTTPException(422, "joker_not_applicable")
        cost = game.fifty_cost(card["difficulty"])
        balance = db.one(con, "SELECT points FROM users WHERE id=?", (user["id"],))["points"]
        if balance < cost:
            raise HTTPException(402, "not_enough_points")
        wrong = [c for c in choices if c.strip() != card["answer"].strip()]
        remove = random.sample(wrong, len(choices) // 2)
        new_points = game.apply_points(con, user["id"], -cost)
        jokers[str(body.card_id)] = remove
        con.execute(
            "UPDATE study_sessions SET jokers_json=?, points_earned=points_earned-? WHERE id=?",
            (json.dumps(jokers, ensure_ascii=False), cost, session_id),
        )
    return {"remove": remove, "points_delta": -cost, "points": new_points}


@app.post("/api/sessions/{session_id}/finish")
def finish_session(session_id: int, user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        session = _own_open_session(con, session_id, user["id"])
        con.execute("UPDATE study_sessions SET finished_at=? WHERE id=?", (db.now(), session_id))
        session["finished_at"] = db.now()
        bonus = game.session_bonus(con, user["id"], session)
        if bonus > 0:
            game.apply_points(con, user["id"], bonus)
            con.execute(
                """UPDATE study_sessions SET bonus_awarded=1, points_earned=points_earned+?
                   WHERE id=?""",
                (bonus, session_id),
            )
        answered = json.loads(session["answered_json"] or "{}")
        counts = {"correct": 0, "wrong": 0, "skipped": 0}
        for v in answered.values():
            counts[v] = counts.get(v, 0) + 1
        full = db.one(con, "SELECT points, lifetime_points FROM users WHERE id=?", (user["id"],))
        streak = game.current_streak(con, user["id"])
    return {
        "ok": True, "bonus": bonus, "counts": counts,
        "points_earned": session["points_earned"] + bonus,
        "points": full["points"], "level": game.level_info(full["lifetime_points"]),
        "streak": streak,
    }


# ---------------------------------------------------------------- stats & leaderboard

@app.get("/api/stats")
def stats(user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        totals = db.one(
            con,
            """SELECT COUNT(*) AS sessions, COALESCE(SUM(points_earned),0) AS session_points
               FROM study_sessions WHERE user_id=? AND finished_at IS NOT NULL""",
            (user["id"],),
        )
        week = db.all_rows(
            con,
            """SELECT date(finished_at,'unixepoch','localtime') AS day,
                      SUM(points_earned) AS points, COUNT(*) AS sessions
               FROM study_sessions
               WHERE user_id=? AND finished_at >= ? GROUP BY day ORDER BY day""",
            (user["id"], db.now() - 7 * 86400),
        )
        answers = db.one(
            con,
            """SELECT COALESCE(SUM(CASE WHEN last_result='correct' THEN 1 ELSE 0 END),0) AS correct,
                      COALESCE(SUM(seen),0) AS seen
               FROM card_progress WHERE user_id=?""",
            (user["id"],),
        )
        streak = game.current_streak(con, user["id"])
    return {"totals": totals, "week": week, "answers": answers, "streak": streak}


@app.get("/api/leaderboard")
def leaderboard(user: dict = Depends(auth.current_user)):
    with db.connect() as con:
        rows = db.all_rows(
            con,
            "SELECT name, lifetime_points FROM users ORDER BY lifetime_points DESC LIMIT 10",
        )
    return [
        {"rank": i + 1, "name": r["name"], "lifetime_points": r["lifetime_points"],
         "level": game.level_info(r["lifetime_points"])["level"]}
        for i, r in enumerate(rows)
    ]


# ---------------------------------------------------------------- static frontend

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/{path:path}")
def spa(path: str):
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
