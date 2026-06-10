# SlopStudy

A self-hostable, Ollama-powered flashcard app. Create study topics, upload sources (PDF, URL, text), generate flashcards with AI, and track your progress with streaks, points, and badges.

## Quick Start

```bash
git clone https://github.com/martinkadauke/slopstudy
cd slopstudy
docker compose -f docker-compose.prod.yml up -d
```

Open http://localhost and register your first account. The first registered user receives admin access.

## Configuration

All settings can be configured via environment variables or the in-app Settings page.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | **Required.** `openssl rand -hex 32` |
| `DATABASE_URL` | `sqlite:////data/db.sqlite3` | SQLite path or PostgreSQL URL |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2` | Model used to generate cards |
| `SMTP_HOST` | — | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP server port |
| `SMTP_USER` | — | SMTP username |
| `SMTP_PASSWORD` | — | SMTP password |
| `SMTP_FROM` | — | Sender address for outgoing mail |
| `SMTP_TLS` | `true` | Enable STARTTLS |

Create a `.env` file at the repo root (never commit it):

```dotenv
SECRET_KEY=your_generated_secret_here
```

## Ollama Setup

Ollama runs locally and provides the AI that generates flashcards and grades exam answers. Install from [ollama.com](https://ollama.com), then pull a model:

```bash
ollama pull llama3.2   # recommended — fast, good quality
ollama pull mistral    # alternative — slightly larger context
```

Configure the endpoint in Settings → Ollama, or set `OLLAMA_URL` if Ollama runs on a different host. When running the whole stack in Docker, set `OLLAMA_URL=http://host.docker.internal:11434` to reach Ollama on your host machine.

## SMTP Setup

Email is optional (used for password resets). Configure via Settings → SMTP or environment variables.

**Gmail (App Password)**
```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=xxxx_xxxx_xxxx_xxxx
SMTP_FROM=you@gmail.com
```
Generate an App Password at myaccount.google.com → Security → App passwords (requires 2FA).

**Mailgun**
```dotenv
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USER=postmaster@mg.yourdomain.com
SMTP_PASSWORD=your_mailgun_smtp_password
SMTP_FROM=noreply@yourdomain.com
```

**Self-hosted Postfix**
```dotenv
SMTP_HOST=mail.yourdomain.com
SMTP_PORT=587
SMTP_USER=noreply@yourdomain.com
SMTP_PASSWORD=your_password
SMTP_FROM=noreply@yourdomain.com
```

## First User

Register at http://localhost/register. The first account created automatically receives admin privileges. Subsequent registrations create regular user accounts.

## Screenshots

<!-- Add screenshots here -->
