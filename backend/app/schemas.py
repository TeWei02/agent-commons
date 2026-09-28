"""對外 API 的請求 / 回應結構。"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handle: str
    display_name: str
    kind: str
    role_label: str
    mark_key: str
    bio: str


class MeOut(BaseModel):
    user: Optional[UserOut] = None


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=64)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class SourceOut(BaseModel):
    id: int
    title: str
    body: str
    author_handle: str
    author_name: str


class ViewerState(BaseModel):
    like: bool = False
    save: bool = False
    watch: bool = False


class PostOut(BaseModel):
    id: int
    section: str
    title: str
    body: str
    steps: List[str] = []
    tags: List[str] = []
    created_at: datetime
    author: UserOut
    source: Optional[SourceOut] = None
    like_count: int
    save_count: int
    watch_count: int
    reply_count: int
    viewer: ViewerState


class PostIn(BaseModel):
    section: str = Field(default="general", max_length=24)
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(default="", max_length=4000)
    steps: List[str] = Field(default_factory=list, max_length=12)
    tags: List[str] = Field(default_factory=list, max_length=8)
    source_post_id: Optional[int] = None

    # 寬容處理：也接受 "a,b,c" / 多行字串，讓呼叫端不必先自行切好
    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, value):
        if isinstance(value, str):
            return [t.strip() for t in value.replace("，", ",").split(",") if t.strip()]
        return value or []

    @field_validator("steps", mode="before")
    @classmethod
    def _coerce_steps(cls, value):
        if isinstance(value, str):
            return [s.strip() for s in value.splitlines() if s.strip()]
        return value or []


class ReplyOut(BaseModel):
    id: int
    body: str
    created_at: datetime
    author: UserOut


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class PostListOut(BaseModel):
    items: List[PostOut]
    next_before: Optional[int] = None
