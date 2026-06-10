from contextlib import asynccontextmanager
import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.limiter import limiter
from app.routers import auth, users
from app.routers.sessions import router as sessions_router
from app.routers.topics import router as topics_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    subprocess.run(["alembic", "upgrade", "head"], check=True)
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.version}


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
