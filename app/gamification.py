"""Points economy.

Design goals:
- Reward knowledge over grinding: points scale with card difficulty.
- Skipping (the "cheat") is a real economic decision: it costs more than an average
  wrong answer would lose you, but less than a guaranteed wrong answer on a hard card.
    correct:  +10 x difficulty
    wrong:     -4 x difficulty   (never below 0 total balance)
    skip:      -7 x difficulty   (cheat: card is dodged and rescheduled, not counted wrong)
    50:50:     -4 x difficulty   (joker: removes 2 wrong choices on 4-option cards)
  So skipping only pays off if you are almost certain you would fail the card —
  guessing is usually the better bet, which keeps people answering.
  The 50:50 joker turns a blind guess (25% -> EV -0.5xd) into a coin flip
  (50% -> EV +3xd before its cost), so at -4xd it is worth buying exactly when
  you can rule nothing out yourself — a real decision, not a freebie.
- Showing up is rewarded: finishing a session grants a one-time bonus per session
  (+25, plus +2 per day of current streak, capped at +15 extra). A session can pay
  its bonus only once, and only the first 3 finished sessions per day pay a bonus,
  so empty 1-card sessions can't be farmed. The bonus also requires >= 3 answered cards.
- Levels are computed from LIFETIME points (spending never demotes you).
"""
import json
from datetime import datetime, timedelta

from . import db

CORRECT_FACTOR = 10
WRONG_FACTOR = 4
SKIP_FACTOR = 7
FIFTY_FACTOR = 4
SESSION_BONUS = 25
STREAK_BONUS_PER_DAY = 2
STREAK_BONUS_CAP = 15
MAX_BONUS_SESSIONS_PER_DAY = 3
MIN_ANSWERS_FOR_BONUS = 3

LEVELS = [0, 100, 300, 700, 1500, 3000, 5500, 9000, 14000, 21000, 30000]


def points_correct(difficulty: int) -> int:
    return CORRECT_FACTOR * difficulty


def points_wrong(difficulty: int) -> int:
    return -WRONG_FACTOR * difficulty


def skip_cost(difficulty: int) -> int:
    return SKIP_FACTOR * difficulty


def fifty_cost(difficulty: int) -> int:
    return FIFTY_FACTOR * difficulty


def level_info(lifetime_points: int) -> dict:
    level = 1
    for i, threshold in enumerate(LEVELS):
        if lifetime_points >= threshold:
            level = i + 1
    cur = LEVELS[level - 1]
    nxt = LEVELS[level] if level < len(LEVELS) else None
    return {
        "level": level,
        "current_threshold": cur,
        "next_threshold": nxt,
        "progress": 1.0 if nxt is None else (lifetime_points - cur) / (nxt - cur),
    }


def apply_points(con, user_id: int, delta: int) -> int:
    """Apply a delta; balance floors at 0; lifetime only counts gains."""
    user = db.one(con, "SELECT points, lifetime_points FROM users WHERE id=?", (user_id,))
    new_points = max(0, user["points"] + delta)
    lifetime = user["lifetime_points"] + max(0, delta)
    con.execute(
        "UPDATE users SET points=?, lifetime_points=? WHERE id=?",
        (new_points, lifetime, user_id),
    )
    return new_points


def _day_of(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def current_streak(con, user_id: int) -> int:
    """Consecutive days (ending today or yesterday) with at least one finished session."""
    days = {
        _day_of(r["finished_at"])
        for r in con.execute(
            "SELECT finished_at FROM study_sessions WHERE user_id=? AND finished_at IS NOT NULL",
            (user_id,),
        )
    }
    if not days:
        return 0
    today = datetime.now().date()
    start = today if today.strftime("%Y-%m-%d") in days else today - timedelta(days=1)
    if start.strftime("%Y-%m-%d") not in days:
        return 0
    streak = 0
    day = start
    while day.strftime("%Y-%m-%d") in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def session_bonus(con, user_id: int, session: dict) -> int:
    """Bonus for finishing a session — 0 if this session already paid or daily cap hit."""
    if session["bonus_awarded"]:
        return 0
    answered = json.loads(session["answered_json"] or "{}")
    real_answers = sum(1 for v in answered.values() if v in ("correct", "wrong"))
    if real_answers < MIN_ANSWERS_FOR_BONUS:
        return 0
    today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    paid_today = db.one(
        con,
        """SELECT COUNT(*) AS c FROM study_sessions
           WHERE user_id=? AND bonus_awarded=1 AND finished_at>=?""",
        (user_id, today_start),
    )["c"]
    if paid_today >= MAX_BONUS_SESSIONS_PER_DAY:
        return 0
    streak = current_streak(con, user_id)
    return SESSION_BONUS + min(STREAK_BONUS_CAP, STREAK_BONUS_PER_DAY * streak)


# Spaced-repetition-lite scheduling: review intervals by correct-streak.
REVIEW_INTERVALS = [600, 86400, 3 * 86400, 7 * 86400, 14 * 86400, 30 * 86400]


def next_due(streak: int) -> int:
    idx = min(streak, len(REVIEW_INTERVALS) - 1)
    return db.now() + REVIEW_INTERVALS[idx]
