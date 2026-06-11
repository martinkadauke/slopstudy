"""Password hashing (stdlib PBKDF2) and cookie-token session auth."""
import hashlib
import hmac
import os
import secrets

from fastapi import HTTPException, Request

from . import db

# Emails listed here are granted admin on registration/login. As a fresh-install
# fallback, the very first user (id=1) is also treated as admin.
ADMIN_EMAILS = {
    e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()
}

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


def sync_admin_flag(user_id: int, email: str):
    """Grant admin to configured emails / the first user; revoke if de-listed.

    A user explicitly promoted in-app (not by env/id rule) keeps admin.
    """
    should = email.lower() in ADMIN_EMAILS or user_id == 1
    if should:
        with db.connect() as con:
            con.execute("UPDATE users SET is_admin=1 WHERE id=?", (user_id,))


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
    if row.get("disabled"):
        # Deactivated accounts lose access immediately, existing sessions included.
        raise HTTPException(status_code=401, detail="account_disabled")
    row.pop("password_hash", None)
    return row


def current_admin(request: Request) -> dict:
    user = current_user(request)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="admin_required")
    return user
