"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False, server_default="en"),
        sa.Column("dark_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("streak_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_session_date", sa.Date(), nullable=True),
        sa.Column("badges", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "user_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("ollama_url", sa.String(), nullable=True),
        sa.Column("ollama_model", sa.String(), nullable=True),
        sa.Column("smtp_host", sa.String(), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("smtp_user", sa.String(), nullable=True),
        sa.Column("smtp_password", sa.String(), nullable=True),
        sa.Column("smtp_from", sa.String(), nullable=True),
        sa.Column("smtp_tls", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "study_topics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("generation_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "topic_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("topic_id", sa.String(36), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["topic_id"], ["study_topics.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "study_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("topic_id", sa.String(36), nullable=False),
        sa.Column("plan_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["topic_id"], ["study_topics.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("topic_id"),
    )

    op.create_table(
        "flashcards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("card_type", sa.String(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("correct_answer", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("source_hint", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["plan_id"], ["study_plans.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "flashcard_options",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("flashcard_id", sa.String(36), nullable=False),
        sa.Column("option_text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["flashcard_id"], ["flashcards.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "study_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("topic_id", sa.String(36), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("points_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("participation_bonus_awarded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["study_topics.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "session_cards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("flashcard_id", sa.String(36), nullable=False),
        sa.Column("answer_given", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("points_spent_to_skip", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("points_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["study_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["flashcard_id"], ["flashcards.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "point_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("reference_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("point_transactions")
    op.drop_table("session_cards")
    op.drop_table("study_sessions")
    op.drop_table("flashcard_options")
    op.drop_table("flashcards")
    op.drop_table("study_plans")
    op.drop_table("topic_sources")
    op.drop_table("study_topics")
    op.drop_table("user_settings")
    op.drop_table("users")
