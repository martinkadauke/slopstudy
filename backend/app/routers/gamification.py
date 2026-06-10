from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.flashcard import Flashcard
from app.models.point_transaction import PointTransaction
from app.models.study_session import SessionCard, StudySession
from app.models.user import User

router = APIRouter(tags=["gamification"])


class PointTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    amount: int
    reason: str
    reference_id: Optional[str] = None
    created_at: datetime


class PointsHistoryEntry(BaseModel):
    date: date
    points_earned: int


class StatsOut(BaseModel):
    total_points: int
    streak_days: int
    sessions_completed: int
    cards_answered: int
    cards_correct: int
    accuracy_pct: float
    points_history: list[PointsHistoryEntry]
    recent_transactions: list[PointTransactionOut]


class CanSkipOut(BaseModel):
    can_spend: bool
    cost: int
    current_points: int


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    points: int
    streak_days: int


@router.get("/api/users/me/stats", response_model=StatsOut)
async def get_my_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions_result = await db.execute(
        select(func.count())
        .select_from(StudySession)
        .where(
            StudySession.user_id == current_user.id,
            StudySession.finished_at.isnot(None),
        )
    )
    sessions_completed = sessions_result.scalar_one()

    answered_result = await db.execute(
        select(func.count())
        .select_from(SessionCard)
        .join(StudySession, SessionCard.session_id == StudySession.id)
        .where(
            StudySession.user_id == current_user.id,
            SessionCard.is_correct.isnot(None),
        )
    )
    cards_answered = answered_result.scalar_one()

    correct_result = await db.execute(
        select(func.count())
        .select_from(SessionCard)
        .join(StudySession, SessionCard.session_id == StudySession.id)
        .where(
            StudySession.user_id == current_user.id,
            SessionCard.is_correct == True,
        )
    )
    cards_correct = correct_result.scalar_one()

    accuracy_pct = round(cards_correct / cards_answered * 100, 1) if cards_answered > 0 else 0.0

    thirty_days_ago_dt = datetime.combine(date.today() - timedelta(days=29), datetime.min.time())
    history_result = await db.execute(
        select(
            func.date(PointTransaction.created_at).label("tx_date"),
            func.sum(PointTransaction.amount).label("pts"),
        )
        .where(
            PointTransaction.user_id == current_user.id,
            PointTransaction.created_at >= thirty_days_ago_dt,
            PointTransaction.amount > 0,
        )
        .group_by(func.date(PointTransaction.created_at))
        .order_by(func.date(PointTransaction.created_at))
    )
    points_history = [
        PointsHistoryEntry(date=date.fromisoformat(str(row.tx_date)), points_earned=int(row.pts))
        for row in history_result.all()
    ]

    tx_result = await db.execute(
        select(PointTransaction)
        .where(PointTransaction.user_id == current_user.id)
        .order_by(PointTransaction.created_at.desc())
        .limit(20)
    )
    recent_transactions = [
        PointTransactionOut.model_validate(tx)
        for tx in tx_result.scalars().all()
    ]

    return StatsOut(
        total_points=current_user.points,
        streak_days=current_user.streak_days,
        sessions_completed=sessions_completed,
        cards_answered=cards_answered,
        cards_correct=cards_correct,
        accuracy_pct=accuracy_pct,
        points_history=points_history,
        recent_transactions=recent_transactions,
    )


@router.get("/api/users/me/stats/can-skip/{flashcard_id}", response_model=CanSkipOut)
async def can_skip_flashcard(
    flashcard_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    card_result = await db.execute(select(Flashcard).where(Flashcard.id == flashcard_id))
    card = card_result.scalar_one_or_none()
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard not found")

    cost = card.difficulty * 3
    return CanSkipOut(
        can_spend=current_user.points >= cost,
        cost=cost,
        current_points=current_user.points,
    )


@router.get("/api/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User.username, User.points, User.streak_days)
        .order_by(User.points.desc())
        .limit(limit)
    )
    rows = result.all()
    return [
        LeaderboardEntry(
            rank=i + 1,
            username=row.username,
            points=row.points,
            streak_days=row.streak_days,
        )
        for i, row in enumerate(rows)
    ]
