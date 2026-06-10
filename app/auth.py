"""Password hashing (stdlib PBKDF2) and cookie-token session auth."""
import hashlib
import hmac
import secrets

from fastapi import HTTPException, Request

from . import db

PBKDF2_ITERATIONS = 240_000
TOKEN_TTL = 60 * 60 * 24 * 30  # 30 days


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iters)
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with db.connect() as con:
        con.execute(
            "INSERT INTO auth_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_token_hash(token), user_id, db.now() + TOKEN_TTL),
        )
        con.execute("DELETE FROM auth_tokens WHERE expires_at < ?", (db.now(),))
    return token


def revoke_token(token: str):
    with db.connect() as con:
        con.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (_token_hash(token),))


def current_user(request: Request) -> dict:
    token = request.cookies.get("fd_session")
    if not token:
        raise HTTPException(status_code=401, detail="not_authenticated")
    with db.connect() as con:
        row = db.one(
            con,
            """SELECT u.* FROM auth_tokens t JOIN users u ON u.id = t.user_id
               WHERE t.token_hash = ? AND t.expires_at > ?""",
            (_token_hash(token), db.now()),
        )
    if not row:
        raise HTTPException(status_code=401, detail="not_authenticated")
    row.pop("password_hash", None)
    return row
