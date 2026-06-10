"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-10

"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("dark_mode", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("points", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("streak_days", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_session_date", sa.Date, nullable=True),
        sa.Column("badges", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    op.create_table(
        "user_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ollama_url", sa.String(512), nullable=True),
        sa.Column("ollama_model", sa.String(255), nullable=True),
        sa.Column("smtp_host", sa.String(255), nullable=True),
        sa.Column("smtp_port", sa.Integer, nullable=False, server_default=sa.text("587")),
        sa.Column("smtp_user", sa.String(255), nullable=True),
        sa.Column("smtp_password", sa.String(255), nullable=True),
        sa.Column("smtp_from", sa.String(255), nullable=True),
        sa.Column("smtp_tls", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("user_id", name="uq_user_settings_user_id"),
    )

    op.create_table(
        "study_topics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("generation_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "topic_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "topic_id",
            sa.String(36),
            sa.ForeignKey("study_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(512), nullable=True),
        sa.Column("file_path", sa.String(1024), nullable=True),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "study_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "topic_id",
            sa.String(36),
            sa.ForeignKey("study_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("topic_id", name="uq_study_plans_topic_id"),
    )

    op.create_table(
        "flashcards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "plan_id",
            sa.String(36),
            sa.ForeignKey("study_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("card_type", sa.String(30), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("correct_answer", sa.Text, nullable=False),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("difficulty", sa.Integer, nullable=False),
        sa.Column("source_hint", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "flashcard_options",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "flashcard_id",
            sa.String(36),
            sa.ForeignKey("flashcards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("option_text", sa.Text, nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False),
    )

    op.create_table(
        "study_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.String(36),
            sa.ForeignKey("study_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("points_earned", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "participation_bonus_awarded",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "session_cards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("study_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "flashcard_id",
            sa.String(36),
            sa.ForeignKey("flashcards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("answer_given", sa.Text, nullable=True),
        sa.Column("is_correct", sa.Boolean, nullable=True),
        sa.Column("skipped", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("points_spent_to_skip", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("points_earned", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("answered_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "point_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("reference_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
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
