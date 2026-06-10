from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SessionCard(Base):
    __tablename__ = "session_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_sessions.id", ondelete="CASCADE"), nullable=False
    )
    flashcard_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("flashcards.id", ondelete="CASCADE"), nullable=False
    )
    answer_given: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    points_spent_to_skip: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
