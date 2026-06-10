from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FlashcardOption(Base):
    __tablename__ = "flashcard_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    flashcard_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("flashcards.id", ondelete="CASCADE"), nullable=False
    )
    option_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
