import random
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.flashcard import Flashcard, FlashcardOption
from app.models.point_transaction import PointTransaction
from app.models.study_plan import StudyPlan
from app.models.study_session import SessionCard, StudySession
from app.models.study_topic import StudyTopic
from app.models.user import User
from app.models.user_settings import UserSettings
from app.services.evaluation import (
    evaluate_exact_answer,
    evaluate_exam_question,
    evaluate_multiple_choice,
    evaluate_yes_no,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class SessionCreateIn(BaseModel):
    topic_id: str
    mode: str
    card_limit: int = 20


class SessionCardOut(BaseModel):
    id: str
    flashcard_id: str
    card_type: str
    question: str
    difficulty: int
    options: Optional[list[str]] = None
    source_hint: Optional[str] = None
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None
    is_correct: Optional[bool] = None
    skipped: bool = False
    points_earned: int = 0
    answered_at: Optional[datetime] = None


class SessionOut(BaseModel):
    id: str
    topic_title: str
    mode: str
    total_cards: int
    cards_answered: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    cards: list[SessionCardOut]


class AnswerIn(BaseModel):
    answer: str


class AnswerOut(BaseModel):
    is_correct: bool
    correct_answer: str
    explanation: Optional[str] = None
    points_earned: int
    user_total_points: int
    feedback: Optional[str] = None


class SkipIn(BaseModel):
    spend_points: bool


class SkipOut(BaseModel):
    points_spent: int
    user_total_points: int


class SessionSummaryOut(BaseModel):
    points_this_session: int
    streak_days: int
    streak_bonus: int
    total_points: int
    cards_correct: int
    cards_skipped: int
    accuracy_pct: float


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _load_session(session_id: str, user_id: str, db: AsyncSession) -> StudySession:
    result = await db.execute(
        select(StudySession).where(
            StudySession.id == session_id,
            StudySession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


async def _build_card_out(sc: SessionCard, db: AsyncSession, *, reveal: bool) -> SessionCardOut:
    card_result = await db.execute(select(Flashcard).where(Flashcard.id == sc.flashcard_id))
    card = card_result.scalar_one()

    options: Optional[list[str]] = None
    if card.card_type == "multiple_choice":
        opts_result = await db.execute(
            select(FlashcardOption).where(FlashcardOption.flashcard_id == card.id)
        )
        options = [o.option_text for o in opts_result.scalars().all()]

    return SessionCardOut(
        id=sc.id,
        flashcard_id=card.id,
        card_type=card.card_type,
        question=card.question,
        difficulty=card.difficulty,
        options=options,
        source_hint=card.source_hint,
        correct_answer=card.correct_answer if reveal else None,
        explanation=card.explanation if reveal else None,
        is_correct=sc.is_correct,
        skipped=sc.skipped,
        points_earned=sc.points_earned,
        answered_at=sc.answered_at,
    )


async def _build_session_out(session: StudySession, db: AsyncSession) -> SessionOut:
    topic_result = await db.execute(
        select(StudyTopic).where(StudyTopic.id == session.topic_id)
    )
    topic = topic_result.scalar_one()

    sc_result = await db.execute(
        select(SessionCard).where(SessionCard.session_id == session.id)
    )
    session_cards = sc_result.scalars().all()

    cards_out = []
    for sc in session_cards:
        reveal = sc.is_correct is not None or sc.skipped
        cards_out.append(await _build_card_out(sc, db, reveal=reveal))

    cards_answered = sum(1 for sc in session_cards if sc.is_correct is not None)

    return SessionOut(
        id=session.id,
        topic_title=topic.title,
        mode=session.mode,
        total_cards=len(session_cards),
        cards_answered=cards_answered,
        started_at=session.started_at,
        finished_at=session.finished_at,
        cards=cards_out,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
async def create_session(
    body: SessionCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topic_result = await db.execute(
        select(StudyTopic).where(
            StudyTopic.id == body.topic_id,
            StudyTopic.user_id == current_user.id,
        )
    )
    topic = topic_result.scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    if topic.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Topic must be in 'ready' status",
        )

    cards_result = await db.execute(
        select(Flashcard)
        .join(StudyPlan, Flashcard.plan_id == StudyPlan.id)
        .where(StudyPlan.topic_id == body.topic_id)
    )
    all_cards = list(cards_result.scalars().all())

    if body.mode != "mixed":
        all_cards = [c for c in all_cards if c.card_type == body.mode]

    if not all_cards:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No cards available for the selected mode",
        )

    random.shuffle(all_cards)
    selected = all_cards[: body.card_limit]

    session = StudySession(
        user_id=current_user.id,
        topic_id=body.topic_id,
        mode=body.mode,
        started_at=datetime.utcnow(),
    )
    db.add(session)
    await db.flush()

    for card in selected:
        db.add(SessionCard(session_id=session.id, flashcard_id=card.id))

    await db.commit()

    return await _build_session_out(session, db)


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _load_session(session_id, current_user.id, db)
    return await _build_session_out(session, db)


@router.get("/{session_id}/next-card", response_model=SessionCardOut)
async def get_next_card(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_session(session_id, current_user.id, db)

    sc_result = await db.execute(
        select(SessionCard).where(
            SessionCard.session_id == session_id,
            SessionCard.is_correct.is_(None),
            SessionCard.skipped.is_(False),
        )
    )
    unanswered = sc_result.scalars().all()
    if not unanswered:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session complete")

    return await _build_card_out(unanswered[0], db, reveal=False)


@router.post("/{session_id}/cards/{card_id}/answer", response_model=AnswerOut)
async def answer_card(
    session_id: str,
    card_id: str,
    body: AnswerIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_session(session_id, current_user.id, db)

    sc_result = await db.execute(
        select(SessionCard).where(
            SessionCard.id == card_id,
            SessionCard.session_id == session_id,
        )
    )
    sc = sc_result.scalar_one_or_none()
    if sc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    if sc.is_correct is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Card already answered")
    if sc.skipped:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Card already skipped")

    card_result = await db.execute(select(Flashcard).where(Flashcard.id == sc.flashcard_id))
    card = card_result.scalar_one()

    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    user_settings = settings_result.scalar_one_or_none()
    ollama_url = user_settings.ollama_url if user_settings else None
    ollama_model = user_settings.ollama_model if user_settings else None

    feedback: Optional[str] = None
    if card.card_type == "multiple_choice":
        opts_result = await db.execute(
            select(FlashcardOption).where(FlashcardOption.flashcard_id == card.id)
        )
        opts = opts_result.scalars().all()
        is_correct = evaluate_multiple_choice(card, list(opts), body.answer)
    elif card.card_type == "yes_no":
        is_correct = evaluate_yes_no(card, body.answer)
    elif card.card_type == "exam_question":
        is_correct, feedback = await evaluate_exam_question(
            card, body.answer, ollama_url, ollama_model
        )
    else:
        is_correct = await evaluate_exact_answer(card, body.answer, ollama_url, ollama_model)

    points_earned = card.difficulty * 2 if is_correct else 0

    sc.answer_given = body.answer
    sc.is_correct = is_correct
    sc.points_earned = points_earned
    sc.answered_at = datetime.utcnow()

    current_user.points = current_user.points + points_earned
    if points_earned > 0:
        db.add(
            PointTransaction(
                user_id=current_user.id,
                amount=points_earned,
                reason="card_correct",
                reference_id=sc.id,
            )
        )

    await db.commit()

    return AnswerOut(
        is_correct=is_correct,
        correct_answer=card.correct_answer,
        explanation=card.explanation,
        points_earned=points_earned,
        user_total_points=current_user.points,
        feedback=feedback,
    )


@router.post("/{session_id}/cards/{card_id}/skip", response_model=SkipOut)
async def skip_card(
    session_id: str,
    card_id: str,
    body: SkipIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_session(session_id, current_user.id, db)

    sc_result = await db.execute(
        select(SessionCard).where(
            SessionCard.id == card_id,
            SessionCard.session_id == session_id,
        )
    )
    sc = sc_result.scalar_one_or_none()
    if sc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    if sc.is_correct is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Card already answered")
    if sc.skipped:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Card already skipped")

    card_result = await db.execute(select(Flashcard).where(Flashcard.id == sc.flashcard_id))
    card = card_result.scalar_one()

    cost = card.difficulty * 3 if body.spend_points else card.difficulty

    if current_user.points - cost < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Insufficient points",
        )

    current_user.points = current_user.points - cost
    sc.skipped = True
    sc.points_spent_to_skip = cost

    db.add(
        PointTransaction(
            user_id=current_user.id,
            amount=-cost,
            reason="card_skip",
            reference_id=sc.id,
        )
    )

    await db.commit()

    return SkipOut(points_spent=cost, user_total_points=current_user.points)


@router.post("/{session_id}/finish", response_model=SessionSummaryOut)
async def finish_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _load_session(session_id, current_user.id, db)
    if session.finished_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already finished")

    session.finished_at = datetime.utcnow()

    participation_bonus = 0
    if not session.participation_bonus_awarded:
        participation_bonus = 10
        session.participation_bonus_awarded = True
        current_user.points = current_user.points + participation_bonus
        db.add(
            PointTransaction(
                user_id=current_user.id,
                amount=participation_bonus,
                reason="participation_bonus",
                reference_id=session.id,
            )
        )

    today = date.today()
    if current_user.last_session_date is None:
        current_user.streak_days = 1
    elif today == current_user.last_session_date:
        pass
    elif today == current_user.last_session_date + timedelta(days=1):
        current_user.streak_days = current_user.streak_days + 1
    else:
        current_user.streak_days = 1

    streak_bonus = 5 * min(current_user.streak_days, 7)
    current_user.points = current_user.points + streak_bonus
    current_user.last_session_date = today

    if streak_bonus > 0:
        db.add(
            PointTransaction(
                user_id=current_user.id,
                amount=streak_bonus,
                reason="streak_bonus",
                reference_id=session.id,
            )
        )

    sc_result = await db.execute(
        select(SessionCard).where(SessionCard.session_id == session_id)
    )
    session_cards = sc_result.scalars().all()

    cards_correct = sum(1 for sc in session_cards if sc.is_correct is True)
    cards_skipped = sum(1 for sc in session_cards if sc.skipped)
    cards_answered = sum(1 for sc in session_cards if sc.is_correct is not None)
    accuracy_pct = (cards_correct / cards_answered * 100) if cards_answered > 0 else 0.0

    card_points = sum(sc.points_earned for sc in session_cards)
    points_this_session = card_points + participation_bonus + streak_bonus
    session.points_earned = points_this_session

    # Badge awards — each awarded at most once per user
    finished_count_result = await db.execute(
        select(func.count())
        .select_from(StudySession)
        .where(
            StudySession.user_id == current_user.id,
            StudySession.finished_at.isnot(None),
        )
    )
    finished_count = finished_count_result.scalar_one()

    total_correct_result = await db.execute(
        select(func.count())
        .select_from(SessionCard)
        .join(StudySession, SessionCard.session_id == StudySession.id)
        .where(
            StudySession.user_id == current_user.id,
            SessionCard.is_correct == True,
        )
    )
    cumulative_correct = total_correct_result.scalar_one()

    current_badges: set[str] = set(current_user.badges or [])

    def _award(key: str) -> None:
        current_badges.add(key)

    if finished_count == 1:
        _award("first_session")
    for threshold, badge_key in [(3, "streak_3"), (7, "streak_7"), (30, "streak_30")]:
        if current_user.streak_days >= threshold:
            _award(badge_key)
    if cumulative_correct >= 100:
        _award("century")
    if cards_answered > 0 and cards_correct == cards_answered and cards_skipped == 0:
        _award("perfect_session")

    current_user.badges = list(current_badges)

    await db.commit()

    return SessionSummaryOut(
        points_this_session=points_this_session,
        streak_days=current_user.streak_days,
        streak_bonus=streak_bonus,
        total_points=current_user.points,
        cards_correct=cards_correct,
        cards_skipped=cards_skipped,
        accuracy_pct=round(accuracy_pct, 1),
    )
