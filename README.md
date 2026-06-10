# 🎴 SlopStudy

Self-hosted, single-container flashcard study app powered by **your own Ollama instance**.

Describe what you want to learn in natural language, optionally upload documents (PDF, DOCX,
TXT, MD, CSV) and reference web sources — the AI designs a pedagogically structured study plan
(foundations → application → exam traps, following Bloom's taxonomy) and generates a full deck
of flashcards from it. You get an email when the deck is ready.

**Features**

- 🦙 Per-user Ollama credentials (URL, model, optional API key) — your data never leaves your infra
- 🧠 AI-designed study plans with units, learning objectives, key concepts and typical pitfalls
- 📄 Document upload + web sources as grounding material
- ❓ Four question modes per topic: multiple choice, exact written answer, yes/no, exam-style
  questions (incl. open ones you self-grade against a model solution)
- 👥 Multi-user with email/password accounts; host locally or on the internet
- 📧 SMTP email notification when a topic finishes generating (generation may take a while —
  it runs in a background queue)
- 🏆 Gamification: difficulty-based points, skip-cheats, a Millionaire-style **50:50 joker**,
  session bonuses, streaks, levels, leaderboard (see [Points economy](#points-economy))
- 🔎 **Web-sourced deep explanations**: after every answer you get a longer, tutor-style
  explanation with 2–3 vetted web sources (keyless DuckDuckGo search + Wikipedia fallback,
  curated by the LLM — no search API key needed)
- 📖 **Learning material**: per-unit study notes with further-reading links, generated in the
  background after the deck is ready
- 🧠 **Learning science built in**: multiple-choice options stay hidden until you've tried to
  recall the answer (active recall), and the UI tells you to test first, read after
  (pre-testing effect)
- 📬 **Nightly weakness report**: a background job reviews what you answered wrong, has the AI
  write a personal coaching email (with the stored web sources) — with a template fallback if
  your Ollama host is asleep at night
- 🌙 **Nightly fresh questions** (per-topic toggle): each night the AI generates a new batch of
  questions for the unit you currently get wrong most often, explicitly avoiding duplicates of
  existing cards (deck growth is capped at 3× the originally requested size)
- 🔁 Spaced-repetition-lite scheduling (due cards come back at growing intervals); decks can be
  re-run indefinitely and every answer is logged
- 🌍 **Fully bilingual (EN/DE)** — not just the UI: every card is generated in the creator's
  language and then translated to the other language in the background, so toggling German
  switches the questions, answers and explanations too (falls back to the original language
  until a card's translation is ready)
- 🛡️ **Admin role** — admins see every user's topics, control the generation queue (reorder,
  pause, resume, stop), delete any topic, and promote/demote other admins
- ✏️ **Edit decks in plain language** — the creator (or an admin) can type instructions like
  "add 8 harder questions about X" or "remove the questions about Y"; the AI applies them in the
  background
- 🗂️ **Card management** — browse, filter and delete individual cards of a deck
  (owner or admin)
- 🔑 **Password reset by email**, invite-by-email onboarding, and rate-limited
  auth endpoints (brute-force protection) for safe public hosting
- ⌨️ Keyboard shortcuts while studying (1–4 pick an option, Enter advances)
- 🌍 dark/light mode, editable profile
- 📱 Responsive — works on phones and desktops

## Quick start

```bash
cp .env.example .env       # edit SMTP settings if you want email notifications
docker compose up -d --build
```

Open http://localhost:8000, create an account, then go to **Settings → Ollama connection**:

| You run Ollama… | Use this URL |
|---|---|
| on the Docker host (default `ollama serve`) | `http://host.docker.internal:11434` |
| in another container on the same Docker network | `http://ollama:11434` |
| on a remote machine / behind a proxy | `https://your-ollama.example.com` (+ API key if proxied) |

> On the host, Ollama must listen on all interfaces for the container to reach it:
> `OLLAMA_HOST=0.0.0.0 ollama serve`

Use the **Test connection** button to verify. Recommended models: `llama3.1:8b` or better;
small models may fail to produce valid JSON and the topic will be marked failed (you can retry).

### Without compose

```bash
docker build -t slopstudy .
docker run -d -p 8000:8000 -v slopstudy_data:/data --env-file .env \
  --add-host host.docker.internal:host-gateway slopstudy
```

### Hosting on the internet

Put the container behind a reverse proxy with TLS (Caddy, Traefik, nginx), set
`APP_BASE_URL=https://your.domain` and `COOKIE_SECURE=true` in `.env`.

## Configuration (environment)

| Variable | Default | Purpose |
|---|---|---|
| `APP_BASE_URL` | `http://localhost:8000` | Link used in notification emails |
| `COOKIE_SECURE` | `false` | Set `true` behind HTTPS |
| `ADMIN_EMAILS` | *(empty)* | Comma-separated emails auto-granted admin; the first registered user is admin too |
| `SMTP_HOST` | *(empty = email disabled)* | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` / `SMTP_PASSWORD` | | SMTP credentials (optional) |
| `SMTP_FROM` | | From address |
| `SMTP_SECURITY` | `starttls` | `starttls`, `ssl` or `none` |
| `SEARXNG_URL` | *(empty)* | Your SearXNG instance for web-source research; falls back to DuckDuckGo/Wikipedia. The instance must allow `format=json` (`search.formats: [html, json]` in its settings.yml) |
| `REPORT_HOUR` | `5` | Hour (container local time) after which the nightly weakness report may be sent |
| `DATA_DIR` | `/data` | SQLite DB + uploads (mount a volume here) |

A 50:50 joker turns a blind 4-option guess (expected value −0.5×difficulty) into a coin flip
(EV +3×difficulty before cost), so at −4×difficulty it's worth buying exactly when you can't
rule anything out yourself — a real decision, not a freebie. The nightly report only includes
cards that are *still* weak (wrong more recently than last answered correctly), needs at least
3 of them, and is sent at most once per day per user.

## Points economy

Designed so that *knowing things* beats grinding, and the skip-cheat is a real decision:

| Event | Points |
|---|---|
| Correct answer | **+10 × difficulty** (difficulty 1–5, judged by the AI per card) |
| Wrong answer | **−4 × difficulty** (balance never drops below 0) |
| Skip a card (cheat) | **−7 × difficulty** — the card is dodged and rescheduled, not counted wrong |
| 50:50 joker | **−4 × difficulty** — removes two wrong options on 4-choice questions, once per card |
| Finish a session | **+25 bonus**, plus +2 per day of your study streak (max +15 extra) |

Skipping costs more than an average wrong answer loses, but less than a guaranteed fail on a
hard card — so guessing usually stays the better bet. Anti-farming rules: the session bonus is
paid **once per session**, only for the **first 3 finished sessions per day**, and only if you
actually answered **at least 3 cards**. Levels are computed from *lifetime* points, so spending
points on skips never demotes you.

## Architecture

Single container: FastAPI + SQLite (WAL) + an in-process background worker that processes the
generation queue (extract sources → design study plan → generate cards unit by unit → send
email). Jobs are persisted, so a container restart resumes pending topics. The frontend is a
dependency-free vanilla-JS SPA served statically — no build step, no CDN calls, works fully
offline/air-gapped.

```
app/
  main.py    API routes (auth, topics, study sessions, stats)
  worker.py  background generation queue
  llm.py     Ollama client + prompt engineering
  extract.py PDF/DOCX/web text extraction
  gamification.py  points economy + spaced repetition scheduling
  emailer.py SMTP notifications (EN/DE)
  auth.py    PBKDF2 passwords, cookie sessions
  db.py      SQLite schema
static/      SPA (index.html, app.js, i18n.js, styles.css)
```

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
DATA_DIR=./data .venv/bin/uvicorn app.main:app --reload
```
