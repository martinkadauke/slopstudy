from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_serializer


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    username: str
    language: str
    dark_mode: bool
    points: int
    streak_days: int
    badges: List
    created_at: datetime


class UserSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_tls: bool = True

    @field_serializer("smtp_password")
    def mask_smtp_password(self, value: Optional[str]) -> Optional[str]:
        return "***" if value else None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    language: Optional[str] = None
    dark_mode: Optional[bool] = None


class UserSettingsUpdate(BaseModel):
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_tls: Optional[bool] = None
