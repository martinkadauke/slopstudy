from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TopicCreate(BaseModel):
    title: str
    description: Optional[str] = None


class TopicUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class TopicOut(BaseModel):
    id: str
    title: str
    description: Optional[str]
    status: str
    created_at: datetime
    source_count: int
    card_count: int

    model_config = {"from_attributes": True}


class TopicSourceOut(BaseModel):
    id: str
    topic_id: str
    type: str
    filename: Optional[str]
    url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class TopicDetail(BaseModel):
    id: str
    title: str
    description: Optional[str]
    status: str
    generation_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    sources: list[TopicSourceOut]

    model_config = {"from_attributes": True}
