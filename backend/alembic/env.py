import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Ensure the backend/ directory is on sys.path so `app` is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Base  # noqa: E402 — must come after sys.path fix

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./slopstudy.db")


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(_get_url())
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
