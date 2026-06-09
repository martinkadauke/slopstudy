# slopstudy

A noob vibecoded studying flashcard app that lets you study any topic. Self-hostable and Ollama ready.

## Quick start

```bash
docker compose up --build
```

Then open [http://localhost:8000](http://localhost:8000).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:////data/slopstudy.db` | SQLAlchemy async database URL |
| `SECRET_KEY` | `changeme` | Secret key for JWT signing — **change in production** |
| `CORS_ORIGINS` | `*` | Comma-separated list of allowed CORS origins |

Copy `.env.example` to `.env` and adjust values before running in production.

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```
