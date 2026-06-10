from email.mime.text import MIMEText

import aiosmtplib
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.user import UserOut, UserSettingsOut, UserSettingsUpdate, UserUpdate
from app.security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


async def _get_or_create_settings(user_id: str, db: AsyncSession) -> UserSettings:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    s = result.scalar_one_or_none()
    if s is None:
        s = UserSettings(user_id=user_id)
        db.add(s)
        await db.commit()
        await db.refresh(s)
    return s


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.put("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.username is not None:
        current_user.username = body.username
    if body.email is not None:
        current_user.email = body.email
    if body.password is not None:
        current_user.password_hash = hash_password(body.password)
    if body.language is not None:
        current_user.language = body.language
    if body.dark_mode is not None:
        current_user.dark_mode = body.dark_mode

    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.get("/me/settings", response_model=UserSettingsOut)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    s = await _get_or_create_settings(current_user.id, db)
    return UserSettingsOut.model_validate(s)


@router.put("/me/settings", response_model=UserSettingsOut)
async def update_settings(
    body: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    s = await _get_or_create_settings(current_user.id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    await db.commit()
    await db.refresh(s)
    return UserSettingsOut.model_validate(s)


@router.post("/me/settings/test-ollama")
async def test_ollama(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    s = await _get_or_create_settings(current_user.id, db)
    if not s.ollama_url:
        return {"ok": False, "model_list": [], "error": "No Ollama URL configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{s.ollama_url.rstrip('/')}/api/tags")
            resp.raise_for_status()
            model_list = [m["name"] for m in resp.json().get("models", [])]
        return {"ok": True, "model_list": model_list}
    except Exception as e:
        return {"ok": False, "model_list": [], "error": str(e)}


@router.post("/me/settings/test-smtp")
async def test_smtp(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    s = await _get_or_create_settings(current_user.id, db)
    if not s.smtp_host:
        return {"ok": False, "error": "No SMTP host configured"}

    try:
        msg = MIMEText("This is a test email from slopstudy.")
        msg["Subject"] = "slopstudy SMTP Test"
        msg["From"] = s.smtp_from or s.smtp_user or "noreply@slopstudy.local"
        msg["To"] = current_user.email

        await aiosmtplib.send(
            msg,
            hostname=s.smtp_host,
            port=s.smtp_port,
            username=s.smtp_user,
            password=s.smtp_password,
            use_tls=s.smtp_tls,
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
