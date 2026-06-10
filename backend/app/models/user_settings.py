from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    ollama_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ollama_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smtp_host: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    smtp_user: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smtp_password: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smtp_from: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smtp_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
