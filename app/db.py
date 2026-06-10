"""SQLite persistence layer. One connection per call, WAL mode for concurrency."""
import os
import sqlite3
import time
from contextlib import contextmanager

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "slopstudy.db")
LEGACY_DB_PATH = os.path.join(DATA_DIR, "flashdeck.db")  # pre-rename; migrated on first start
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    theme TEXT NOT NULL DEFAULT 'dark',
    ollama_url TEXT NOT NULL DEFAULT 'http://host.docker.internal:11434',
    ollama_model TEXT NOT NULL DEFAULT 'llama3.1',
    ollama_api_key TEXT NOT NULL DEFAULT '',
    points INTEGER NOT NULL DEFAULT 0,
    lifetime_points INTEGER NOT NULL DEFAULT 0,
    email_notifications INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'multiple_choice',
    card_count INTEGER NOT NULL DEFAULT 40,
    language TEXT NOT NULL DEFAULT 'en',
    status TEXT NOT NULL DEFAULT 'queued',
    progress_msg TEXT NOT NULL DEFAULT '',
    progress_pct INTEGER NOT NULL DEFAULT 0,
    plan_json TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    ready_at INTEGER
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,              -- 'file' | 'url'
    name TEXT NOT NULL,              -- filename or url
    file_path TEXT NOT NULL DEFAULT '',
    content_text TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    unit_index INTEGER NOT NULL DEFAULT 0,
    type TEXT NOT NULL,              -- 'multiple_choice' | 'exact' | 'yes_no' | 'open'
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    choices_json TEXT NOT NULL DEFAULT '',
    explanation TEXT NOT NULL DEFAULT '',
    difficulty INTEGER NOT NULL DEFAULT 2,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS card_progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    streak INTEGER NOT NULL DEFAULT 0,
    seen INTEGER NOT NULL DEFAULT 0,
    due_at INTEGER NOT NULL DEFAULT 0,
    last_result TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, card_id)
);

CREATE TABLE IF NOT EXISTS study_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    card_ids_json TEXT NOT NULL DEFAULT '[]',
    answered_json TEXT NOT NULL DEFAULT '{}',  -- card_id -> 'correct'|'wrong'|'skipped'
    started_at INTEGER NOT NULL,
    finished_at INTEGER,
    points_earned INTEGER NOT NULL DEFAULT 0,
    bonus_awarded INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS answer_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    session_id INTEGER NOT NULL,
    result TEXT NOT NULL,            -- 'correct' | 'wrong' | 'skipped'
    answered_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    instruction TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',  -- queued|processing|done|failed
    result_msg TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_topics_user ON topics(user_id);
CREATE INDEX IF NOT EXISTS idx_cards_topic ON cards(topic_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON study_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_answer_log_user ON answer_log(user_id, answered_at);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invites (
    code TEXT PRIMARY KEY,
    email TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    used_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    used_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_revisions_topic ON topic_revisions(topic_id);
"""

# Columns added after the 1.0 schema; applied idempotently so existing
# deployments upgrade in place on container start.
MIGRATIONS = [
    ("cards", "long_explanation", "TEXT NOT NULL DEFAULT ''"),
    ("cards", "sources_json", "TEXT NOT NULL DEFAULT ''"),
    ("cards", "lang", "TEXT NOT NULL DEFAULT ''"),
    ("cards", "translations_json", "TEXT NOT NULL DEFAULT ''"),
    ("topics", "material_json", "TEXT NOT NULL DEFAULT ''"),
    ("topics", "nightly_refresh", "INTEGER NOT NULL DEFAULT 0"),
    ("topics", "last_refresh_at", "INTEGER NOT NULL DEFAULT 0"),
    ("topics", "queue_priority", "INTEGER NOT NULL DEFAULT 0"),
    ("topics", "paused", "INTEGER NOT NULL DEFAULT 0"),
    ("topics", "cancel_requested", "INTEGER NOT NULL DEFAULT 0"),
    ("topics", "enrich_paused", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "last_report_at", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "is_admin", "INTEGER NOT NULL DEFAULT 0"),
    ("invites", "email", "TEXT NOT NULL DEFAULT ''"),
    ("study_sessions", "jokers_json", "TEXT NOT NULL DEFAULT '{}'"),
]


def _migrate_legacy_db():
    """Rename a pre-rename flashdeck.db (and its WAL/SHM sidecars) to slopstudy.db.

    Keeps existing deployments' accounts and decks intact across the app rename.
    """
    if os.path.exists(DB_PATH) or not os.path.exists(LEGACY_DB_PATH):
        return
    for suffix in ("", "-wal", "-shm"):
        src, dst = LEGACY_DB_PATH + suffix, DB_PATH + suffix
        if os.path.exists(src):
            os.rename(src, dst)


def init():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    _migrate_legacy_db()
    with connect() as con:
        con.executescript(SCHEMA)
        for table, col, decl in MIGRATIONS:
            existing = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            if col not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        _seed_ollama_settings(con)


@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def now() -> int:
    return int(time.time())


DEFAULT_OLLAMA_URL = "http://host.docker.internal:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1"


def ollama_config(con) -> dict:
    """The single, admin-managed Ollama connection (shared by all users)."""
    return {
        "ollama_url": get_setting(con, "ollama_url", DEFAULT_OLLAMA_URL),
        "ollama_model": get_setting(con, "ollama_model", DEFAULT_OLLAMA_MODEL),
        "ollama_api_key": get_setting(con, "ollama_api_key", ""),
    }


def _seed_ollama_settings(con):
    """First run after the per-user→global move: adopt an existing user's Ollama
    config (prefer an admin, else the first user) so deployments keep working."""
    if get_setting(con, "ollama_url"):
        return
    row = con.execute(
        """SELECT ollama_url, ollama_model, ollama_api_key FROM users
           WHERE ollama_url != '' ORDER BY is_admin DESC, id LIMIT 1"""
    ).fetchone()
    if row and row["ollama_url"]:
        set_setting(con, "ollama_url", row["ollama_url"])
        set_setting(con, "ollama_model", row["ollama_model"])
        set_setting(con, "ollama_api_key", row["ollama_api_key"])


def get_setting(con, key: str, default: str = "") -> str:
    row = con.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(con, key: str, value: str):
    con.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def one(con, sql, params=()):
    row = con.execute(sql, params).fetchone()
    return dict(row) if row else None


def all_rows(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]
