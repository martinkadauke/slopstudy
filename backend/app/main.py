import logging
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import func, select

from app.config import settings
from app.database import async_session_factory
from app.limiter import limiter
from app.models.point_transaction import PointTransaction
from app.models.user import User
from app.routers import auth, users
from app.routers.gamification import router as gamification_router
from app.routers.sessions import router as sessions_router
from app.routers.topics import router as topics_router

logger = logging.getLogger(__name__)


async def _check_point_consistency() -> None:
    async with async_session_factory() as db:
        rows = await db.execute(
            select(
                User.id,
                User.username,
                User.points,
                func.coalesce(func.sum(PointTransaction.amount), 0).label("tx_sum"),
            )
            .outerjoin(PointTransaction, PointTransaction.user_id == User.id)
            .group_by(User.id)
        )
        for row in rows.all():
            if row.points != int(row.tx_sum):
                logger.warning(
                    "Point inconsistency for user %s (%s): users.points=%d, SUM(transactions)=%d",
                    row.username,
                    row.id,
                    row.points,
                    int(row.tx_sum),
                )


@asynccontextmanager
async def lifespan(app: FastAPI):
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    await _check_point_consistency()
    yield


app = FastAPI(title="slopstudy", version=settings.version, lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(topics_router)
app.include_router(sessions_router)
app.include_router(gamification_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.version}


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
