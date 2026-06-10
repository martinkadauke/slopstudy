from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.flashcard import Flashcard
from app.models.study_plan import StudyPlan
from app.models.study_topic import StudyTopic
from app.models.topic_source import TopicSource
from app.models.user import User
from app.schemas.topics import TopicCreate, TopicDetail, TopicOut, TopicSourceOut, TopicUpdate
from app.services.ingestion import (
    extract_from_docx,
    extract_from_pdf,
    extract_from_text,
    extract_from_url,
)

router = APIRouter(prefix="/api/topics", tags=["topics"])

_UPLOAD_ROOT = Path("/data/uploads")

_FILE_EXTRACTORS = {
    "pdf": extract_from_pdf,
    "docx": extract_from_docx,
    "doc": extract_from_docx,
    "txt": extract_from_text,
    "md": extract_from_text,
}


async def _get_topic_or_404(topic_id: str, user_id: str, db: AsyncSession) -> StudyTopic:
    result = await db.execute(
        select(StudyTopic).where(StudyTopic.id == topic_id, StudyTopic.user_id == user_id)
    )
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic


@router.get("", response_model=list[TopicOut])
async def list_topics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source_count_sq = (
        select(func.count(TopicSource.id))
        .where(TopicSource.topic_id == StudyTopic.id)
        .correlate(StudyTopic)
        .scalar_subquery()
    )
    card_count_sq = (
        select(func.count(Flashcard.id))
        .join(StudyPlan, Flashcard.plan_id == StudyPlan.id)
        .where(StudyPlan.topic_id == StudyTopic.id)
        .correlate(StudyTopic)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(
            StudyTopic,
            source_count_sq.label("source_count"),
            card_count_sq.label("card_count"),
        )
        .where(StudyTopic.user_id == current_user.id)
        .order_by(StudyTopic.created_at.desc())
    )
    return [
        TopicOut(
            id=t.id,
            title=t.title,
            description=t.description,
            status=t.status,
            created_at=t.created_at,
            source_count=sc or 0,
            card_count=cc or 0,
        )
        for t, sc, cc in rows.all()
    ]


@router.post("", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
async def create_topic(
    body: TopicCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topic = StudyTopic(
        user_id=current_user.id,
        title=body.title,
        description=body.description,
        status="draft",
    )
    db.add(topic)
    await db.commit()
    return TopicOut(
        id=topic.id,
        title=topic.title,
        description=topic.description,
        status=topic.status,
        created_at=topic.created_at,
        source_count=0,
        card_count=0,
    )


@router.get("/{topic_id}", response_model=TopicDetail)
async def get_topic(
    topic_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topic = await _get_topic_or_404(topic_id, current_user.id, db)
    sources_result = await db.execute(
        select(TopicSource).where(TopicSource.topic_id == topic_id).order_by(TopicSource.created_at)
    )
    sources = sources_result.scalars().all()
    return TopicDetail(
        id=topic.id,
        title=topic.title,
        description=topic.description,
        status=topic.status,
        generation_error=topic.generation_error,
        created_at=topic.created_at,
        updated_at=topic.updated_at,
        sources=[
            TopicSourceOut(
                id=s.id,
                topic_id=s.topic_id,
                type=s.type,
                filename=s.filename,
                url=s.url,
                created_at=s.created_at,
            )
            for s in sources
        ],
    )


@router.put("/{topic_id}", response_model=TopicOut)
async def update_topic(
    topic_id: str,
    body: TopicUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topic = await _get_topic_or_404(topic_id, current_user.id, db)
    if body.title is not None:
        topic.title = body.title
    if body.description is not None:
        topic.description = body.description
    await db.commit()

    source_count = await db.scalar(
        select(func.count(TopicSource.id)).where(TopicSource.topic_id == topic_id)
    )
    card_count = await db.scalar(
        select(func.count(Flashcard.id))
        .join(StudyPlan, Flashcard.plan_id == StudyPlan.id)
        .where(StudyPlan.topic_id == topic_id)
    )
    return TopicOut(
        id=topic.id,
        title=topic.title,
        description=topic.description,
        status=topic.status,
        created_at=topic.created_at,
        source_count=source_count or 0,
        card_count=card_count or 0,
    )


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(
    topic_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topic = await _get_topic_or_404(topic_id, current_user.id, db)
    await db.delete(topic)
    await db.commit()


@router.post("/{topic_id}/sources", response_model=TopicSourceOut, status_code=status.HTTP_201_CREATED)
async def add_source(
    topic_id: str,
    file: Optional[UploadFile] = File(None),
    type: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_topic_or_404(topic_id, current_user.id, db)

    if file is not None:
        raw = await file.read()
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        extractor = _FILE_EXTRACTORS.get(ext)
        if extractor is None:
            # fallback: try as plain text
            extractor = extract_from_text
        extracted = await extractor(raw)

        upload_dir = _UPLOAD_ROOT / current_user.id / topic_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        # avoid collisions by prefixing with a short uuid fragment
        safe_name = f"{uuid4().hex[:8]}_{file.filename}"
        dest = upload_dir / safe_name
        dest.write_bytes(raw)

        source = TopicSource(
            topic_id=topic_id,
            type="file",
            filename=file.filename,
            file_path=str(dest),
            content=extracted,
        )

    elif type == "url":
        if not url:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="url is required")
        extracted = await extract_from_url(url)
        source = TopicSource(
            topic_id=topic_id,
            type="url",
            url=url,
            content=extracted,
        )

    elif type == "text":
        if not content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="content is required"
            )
        source = TopicSource(
            topic_id=topic_id,
            type="text",
            content=content,
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide a file upload or type='url'/'text' with matching fields",
        )

    db.add(source)
    await db.commit()
    return TopicSourceOut(
        id=source.id,
        topic_id=source.topic_id,
        type=source.type,
        filename=source.filename,
        url=source.url,
        created_at=source.created_at,
    )


@router.delete("/{topic_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    topic_id: str,
    source_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_topic_or_404(topic_id, current_user.id, db)
    result = await db.execute(
        select(TopicSource).where(TopicSource.id == source_id, TopicSource.topic_id == topic_id)
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    await db.delete(source)
    await db.commit()
