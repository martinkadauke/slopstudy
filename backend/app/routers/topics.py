from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.flashcard import Flashcard
from app.models.study_plan import StudyPlan
from app.models.study_topic import StudyTopic
from app.models.user import User
from app.services.generation import run_generation

router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.post("/{topic_id}/generate")
async def generate_topic(
    topic_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudyTopic).where(
            StudyTopic.id == topic_id,
            StudyTopic.user_id == current_user.id,
        )
    )
    topic = result.scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    if topic.status not in ("draft", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Topic must be in draft or failed status to start generation",
        )

    topic.status = "generating"
    await db.commit()

    background_tasks.add_task(run_generation, topic_id, current_user.id)
    return {"message": "Generation started", "topic_id": topic_id}


@router.get("/{topic_id}/status")
async def get_topic_status(
    topic_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StudyTopic).where(
            StudyTopic.id == topic_id,
            StudyTopic.user_id == current_user.id,
        )
    )
    topic = result.scalar_one_or_none()
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    count_result = await db.execute(
        select(func.count(Flashcard.id))
        .join(StudyPlan, Flashcard.plan_id == StudyPlan.id)
        .where(StudyPlan.topic_id == topic_id)
    )
    card_count = count_result.scalar() or 0

    resp: dict = {"status": topic.status, "card_count": card_count}
    if topic.generation_error:
        resp["error"] = topic.generation_error
    return resp
