"""SMTP notification mail, configured via environment variables (see .env.example)."""
import asyncio
import html as html_mod
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


# ------------------------------------------------------------------ HTML layer

_CTA_OPEN = {"en": "Open SlopStudy", "de": "SlopStudy öffnen"}


def wrap_html(heading: str, text_body: str, cta_text: str | None = None,
              cta_url: str | None = None) -> str:
    """Wrap a plain-text body in the SlopStudy look: dark card, gradient brand,
    gradient CTA button. Inline styles only (email clients strip <style>)."""
    paragraphs = "".join(
        f'<p style="margin:0 0 14px;">{html_mod.escape(p).replace(chr(10), "<br>")}</p>'
        for p in text_body.split("\n\n") if p.strip()
    )
    cta = ""
    if cta_text and cta_url:
        cta = (
            f'<div style="text-align:center;margin:24px 0 6px;">'
            f'<a href="{html_mod.escape(cta_url, quote=True)}" '
            f'style="display:inline-block;background:linear-gradient(135deg,#6d5cff,#b14bf4);'
            f'background-color:#7d5cff;color:#ffffff;text-decoration:none;font-weight:700;'
            f'font-size:15px;padding:13px 26px;border-radius:12px;">'
            f'{html_mod.escape(cta_text)}</a></div>'
        )
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background-color:#12121c;">
<div style="background-color:#12121c;padding:28px 12px;">
  <div style="max-width:540px;margin:0 auto;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <div style="text-align:center;padding-bottom:18px;font-size:24px;font-weight:800;">
      <span style="color:#9b6dff;">🎴 SlopStudy</span>
    </div>
    <div style="background-color:#1c1c2b;border:1px solid #2e2e45;border-radius:18px;padding:28px 26px;color:#ececf5;font-size:15px;line-height:1.65;">
      <h2 style="margin:0 0 16px;font-size:19px;color:#ffffff;">{html_mod.escape(heading)}</h2>
      {paragraphs}
      {cta}
    </div>
    <p style="text-align:center;color:#9a9ab5;font-size:12px;margin-top:16px;">
      SlopStudy — AI flashcards, self-hosted.
    </p>
  </div>
</div>
</body></html>"""


def send_invitation_sync(to_addr: str, subject: str, body: str,
                         cta_text: str | None = None, cta_url: str | None = None):
    """Synchronous send, used from the admin request handler (small, blocking)."""
    _send_sync(to_addr, subject, body, html=wrap_html(subject, body, cta_text, cta_url))


# ------------------------------------------------------------------ notices
# Account/security events. Every notice links back to SlopStudy (or deeplinks
# to the relevant item). Security notices ignore the email_notifications pref.

NOTICES = {
    "pw_admin_set": {
        "en": ("Your SlopStudy password was changed by an administrator",
               "Hi {name},\n\nan administrator just set a new password for your account and "
               "you have been signed out everywhere. If you did not expect this, contact your "
               "administrator.\n\nLog in with your new password here:\n{link}"),
        "de": ("Dein SlopStudy-Passwort wurde von einem Administrator geändert",
               "Hallo {name},\n\nein Administrator hat soeben ein neues Passwort für dein Konto "
               "gesetzt und du wurdest überall abgemeldet. Falls du das nicht erwartet hast, "
               "wende dich an deinen Administrator.\n\nHier mit dem neuen Passwort anmelden:\n{link}"),
    },
    "pw_changed": {
        "en": ("Your SlopStudy password was changed",
               "Hi {name},\n\nyour password was just changed. If this was you, you're all set. "
               "If not, reset it immediately or contact your administrator.\n\n{link}"),
        "de": ("Dein SlopStudy-Passwort wurde geändert",
               "Hallo {name},\n\ndein Passwort wurde soeben geändert. Wenn du das warst, ist "
               "alles in Ordnung. Falls nicht, setze es sofort zurück oder wende dich an deinen "
               "Administrator.\n\n{link}"),
    },
    "email_changed": {
        "en": ("Your SlopStudy email address was changed",
               "Hi {name},\n\nthe email address of your account was just changed to {new_email}. "
               "If this wasn't you, contact your administrator immediately.\n\n{link}"),
        "de": ("Deine SlopStudy-E-Mail-Adresse wurde geändert",
               "Hallo {name},\n\ndie E-Mail-Adresse deines Kontos wurde soeben zu {new_email} "
               "geändert. Falls das nicht du warst, wende dich sofort an deinen Administrator."
               "\n\n{link}"),
    },
    "topic_shared": {
        "en": ("{actor} shared a study topic with you",
               "Hi {name},\n\n{actor} shared the study topic \"{title}\" with you on SlopStudy. "
               "You can start studying it right away:\n{link}"),
        "de": ("{actor} hat ein Lernthema mit dir geteilt",
               "Hallo {name},\n\n{actor} hat das Lernthema \"{title}\" auf SlopStudy mit dir "
               "geteilt. Du kannst sofort loslegen:\n{link}"),
    },
    "admin_granted": {
        "en": ("You are now a SlopStudy administrator",
               "Hi {name},\n\nyou were just given administrator rights on SlopStudy. You can "
               "now manage users, invitations, the AI queue and the Ollama connection.\n\n{link}"),
        "de": ("Du bist jetzt SlopStudy-Administrator",
               "Hallo {name},\n\ndir wurden soeben Administratorrechte auf SlopStudy gegeben. "
               "Du kannst jetzt Nutzer, Einladungen, die KI-Warteschlange und die "
               "Ollama-Verbindung verwalten.\n\n{link}"),
    },
    "account_disabled": {
        "en": ("Your SlopStudy account was deactivated",
               "Hi {name},\n\nyour account was deactivated by an administrator and you have "
               "been signed out. If you believe this is a mistake, contact your administrator."
               "\n\n{link}"),
        "de": ("Dein SlopStudy-Konto wurde deaktiviert",
               "Hallo {name},\n\ndein Konto wurde von einem Administrator deaktiviert und du "
               "wurdest abgemeldet. Wenn du das für einen Fehler hältst, wende dich an deinen "
               "Administrator.\n\n{link}"),
    },
    "account_enabled": {
        "en": ("Your SlopStudy account was reactivated",
               "Hi {name},\n\ngood news — your account was reactivated. Welcome back!\n\n{link}"),
        "de": ("Dein SlopStudy-Konto wurde reaktiviert",
               "Hallo {name},\n\ngute Nachrichten — dein Konto wurde reaktiviert. "
               "Willkommen zurück!\n\n{link}"),
    },
}


def send_notice_sync(to_addr: str, lang: str, key: str, link_path: str = "", **fmt):
    """Send one branded notice mail (best-effort; never raises into the caller)."""
    if not smtp_configured():
        return
    base = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    link = base + link_path
    subject_t, body_t = NOTICES[key].get(lang, NOTICES[key]["en"])
    subject = subject_t.format(link=link, **fmt)
    body = body_t.format(link=link, **fmt)
    cta = _CTA_OPEN.get(lang, _CTA_OPEN["en"])
    try:
        _send_sync(to_addr, subject, body, wrap_html(subject, body, cta, link))
        log.info("Sent %s notice to %s", key, to_addr)
    except Exception:
        log.exception("Failed to send %s notice to %s", key, to_addr)


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
    full_body = body + s["footer"].format(link=link)
    cta = _CTA_OPEN.get(user.get("language", "en"), _CTA_OPEN["en"])
    html = wrap_html(subject, full_body, cta, link)
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _send_sync, user["email"], subject, full_body, html
        )
        log.info("Sent weakness report to %s", user["email"])
    except Exception:
        log.exception("Failed to send weakness report to %s", user["email"])


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def _send_sync(to_addr: str, subject: str, body: str, html: str | None = None):
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
    msg.set_content(body)  # plain-text fallback for strict clients
    if html:
        msg.add_alternative(html, subtype="html")

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
        user, "subject", "body", link_path=f"/#/topic/{topic['id']}",
        title=topic["title"] or topic["prompt"][:60], cards=cards, units=units,
    )


async def send_topic_failed(user: dict, topic: dict, error: str):
    await _send_templated(
        user, "subject_failed", "body_failed", link_path=f"/#/topic/{topic['id']}",
        title=topic["title"] or topic["prompt"][:60], error=error,
    )


async def _send_templated(user: dict, subject_key: str, body_key: str,
                          link_path: str = "", **kwargs):
    if not smtp_configured() or not user.get("email_notifications", 1):
        return
    tpl = TEMPLATES.get(user.get("language", "en"), TEMPLATES["en"])
    link = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/") + link_path
    subject = tpl[subject_key].format(**kwargs, name=user["name"], link=link)
    body = tpl[body_key].format(**kwargs, name=user["name"], link=link)
    cta = _CTA_OPEN.get(user.get("language", "en"), _CTA_OPEN["en"])
    html = wrap_html(subject, body, cta, link)
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _send_sync, user["email"], subject, body, html
        )
        log.info("Sent notification mail to %s", user["email"])
    except Exception:
        log.exception("Failed to send notification mail to %s", user["email"])
