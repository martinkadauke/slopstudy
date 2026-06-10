"""SMTP notification mail, configured via environment variables (see .env.example)."""
import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("slopstudy.email")

TEMPLATES = {
    "en": {
        "subject": 'Your study topic "{title}" is ready',
        "body": (
            "Hi {name},\n\n"
            'Your study topic "{title}" has finished generating: {cards} flashcards '
            "across {units} units are waiting for you.\n\n"
            "Start studying: {link}\n\n"
            "Happy learning!\nSlopStudy"
        ),
        "subject_failed": 'Generating "{title}" failed',
        "body_failed": (
            "Hi {name},\n\n"
            'Unfortunately, generating your study topic "{title}" failed:\n{error}\n\n'
            "You can retry it from your dashboard: {link}\n\nSlopStudy"
        ),
    },
    "de": {
        "subject": 'Dein Lernthema "{title}" ist fertig',
        "body": (
            "Hallo {name},\n\n"
            'dein Lernthema "{title}" wurde fertig erstellt: {cards} Karteikarten '
            "in {units} Einheiten warten auf dich.\n\n"
            "Jetzt lernen: {link}\n\n"
            "Viel Erfolg!\nSlopStudy"
        ),
        "subject_failed": 'Erstellung von "{title}" fehlgeschlagen',
        "body_failed": (
            "Hallo {name},\n\n"
            'die Erstellung deines Lernthemas "{title}" ist leider fehlgeschlagen:\n{error}\n\n'
            "Du kannst es im Dashboard erneut versuchen: {link}\n\nSlopStudy"
        ),
    },
}

REPORT_STRINGS = {
    "en": {
        "subject": "Your study review: {n} concepts to revisit",
        "footer": "\n\nStudy now: {link}\nSlopStudy — you can disable these emails in Settings.",
        "sources_heading": "Further reading:",
        "fallback_intro": (
            "Hi {name},\n\nhere are the concepts you missed recently. Read each explanation, "
            "then — important — try to recall the answer from memory before your next session "
            "(active recall beats re-reading):\n"
        ),
        "fallback_item": "\n• {question}\n  Correct answer: {answer}\n  {explanation}\n",
    },
    "de": {
        "subject": "Dein Lern-Review: {n} Konzepte zum Wiederholen",
        "footer": "\n\nJetzt lernen: {link}\nSlopStudy — diese Mails kannst du in den Einstellungen abschalten.",
        "sources_heading": "Weiterführende Quellen:",
        "fallback_intro": (
            "Hallo {name},\n\nhier sind die Konzepte, die du zuletzt falsch hattest. Lies die "
            "Erklärungen und versuche dann — wichtig — die Antwort vor der nächsten Sitzung aus "
            "dem Gedächtnis abzurufen (Active Recall schlägt bloßes Wiederlesen):\n"
        ),
        "fallback_item": "\n• {question}\n  Richtige Antwort: {answer}\n  {explanation}\n",
    },
}


INVITE_STRINGS = {
    "en": {
        "subject": "You're invited to SlopStudy",
        "body": (
            "Hi,\n\n{inviter} invited you to SlopStudy — AI-generated flashcards for studying.\n\n"
            "Create your account here (your email is already filled in, just pick a password):\n"
            "{link}\n\nSee you there!\nSlopStudy"
        ),
    },
    "de": {
        "subject": "Du wurdest zu SlopStudy eingeladen",
        "body": (
            "Hallo,\n\n{inviter} hat dich zu SlopStudy eingeladen — KI-generierte Karteikarten "
            "zum Lernen.\n\n"
            "Erstelle hier dein Konto (deine E-Mail ist schon eingetragen, du musst nur ein "
            "Passwort wählen):\n{link}\n\nBis gleich!\nSlopStudy"
        ),
    },
}


def invitation_email(lang: str, inviter_name: str, link: str) -> tuple[str, str]:
    s = INVITE_STRINGS.get(lang, INVITE_STRINGS["en"])
    return s["subject"], s["body"].format(inviter=inviter_name, link=link)


RESET_STRINGS = {
    "en": {
        "subject": "Reset your SlopStudy password",
        "body": (
            "Hi {name},\n\nsomeone (hopefully you) requested a password reset for your "
            "SlopStudy account.\n\nSet a new password here (link valid for 1 hour):\n{link}\n\n"
            "If you didn't request this, you can ignore this email.\nSlopStudy"
        ),
    },
    "de": {
        "subject": "Setze dein SlopStudy-Passwort zurück",
        "body": (
            "Hallo {name},\n\njemand (hoffentlich du) hat das Zurücksetzen des Passworts für "
            "dein SlopStudy-Konto angefordert.\n\nSetze hier ein neues Passwort (Link 1 Stunde "
            "gültig):\n{link}\n\nFalls du das nicht warst, ignoriere diese E-Mail einfach.\nSlopStudy"
        ),
    },
}


def password_reset_email(lang: str, name: str, link: str) -> tuple[str, str]:
    s = RESET_STRINGS.get(lang, RESET_STRINGS["en"])
    return s["subject"], s["body"].format(name=name, link=link)


def send_invitation_sync(to_addr: str, subject: str, body: str):
    """Synchronous send, used from the admin request handler (small, blocking)."""
    _send_sync(to_addr, subject, body)


def _report_strings(user: dict) -> dict:
    return REPORT_STRINGS.get(user.get("language", "en"), REPORT_STRINGS["en"])


def sources_heading(user: dict) -> str:
    return _report_strings(user)["sources_heading"]


def fallback_report_body(user: dict, weak_cards: list[dict]) -> str:
    s = _report_strings(user)
    body = s["fallback_intro"].format(name=user["name"])
    for row in weak_cards:
        explanation = (row["long_explanation"] or row["explanation"] or "")[:400]
        body += s["fallback_item"].format(
            question=row["question"], answer=row["answer"], explanation=explanation)
    return body


async def send_weakness_report(user: dict, body: str, n_weak: int):
    if not smtp_configured() or not user.get("email_notifications", 1):
        return
    s = _report_strings(user)
    link = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    subject = s["subject"].format(n=n_weak)
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _send_sync, user["email"], subject, body + s["footer"].format(link=link)
        )
        log.info("Sent weakness report to %s", user["email"])
    except Exception:
        log.exception("Failed to send weakness report to %s", user["email"])


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def _send_sync(to_addr: str, subject: str, body: str):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    security = os.environ.get("SMTP_SECURITY", "starttls").lower()  # starttls|ssl|none
    from_addr = os.environ.get("SMTP_FROM", user or "slopstudy@localhost")

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    if security == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
    try:
        if security == "starttls":
            server.starttls()
        if user:
            server.login(user, password)
        server.send_message(msg)
    finally:
        server.quit()


async def send_topic_ready(user: dict, topic: dict, cards: int, units: int):
    await _send_templated(
        user, "subject", "body",
        title=topic["title"] or topic["prompt"][:60], cards=cards, units=units,
    )


async def send_topic_failed(user: dict, topic: dict, error: str):
    await _send_templated(
        user, "subject_failed", "body_failed",
        title=topic["title"] or topic["prompt"][:60], error=error,
    )


async def _send_templated(user: dict, subject_key: str, body_key: str, **kwargs):
    if not smtp_configured() or not user.get("email_notifications", 1):
        return
    tpl = TEMPLATES.get(user.get("language", "en"), TEMPLATES["en"])
    link = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    subject = tpl[subject_key].format(**kwargs, name=user["name"], link=link)
    body = tpl[body_key].format(**kwargs, name=user["name"], link=link)
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _send_sync, user["email"], subject, body
        )
        log.info("Sent notification mail to %s", user["email"])
    except Exception:
        log.exception("Failed to send notification mail to %s", user["email"])
