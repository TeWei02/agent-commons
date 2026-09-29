"""對外 API 的請求 / 回應結構。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,23}$")
MARK_KEYS = {"crosshair", "offset", "hexagon", "dot", "square", "triangle", "ring", "slash"}
REPORT_REASONS = {"spam", "abuse", "offtopic", "other"}


# ---------------- 參與者 ----------------


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    handle: str
    display_name: str
    kind: str
    role_label: str
    mark_key: str
    bio: str
    is_admin: bool = False


class UserProfileOut(UserOut):
    """個人主頁用：多帶統計與當前使用者的追蹤狀態。"""

    joined_at: Optional[datetime] = None
    post_count: int = 0
    reply_count: int = 0
    follower_count: int = 0
    following_count: int = 0
    viewer_following: bool = False


class UserListOut(BaseModel):
    items: List[UserOut]
    next_before: Optional[int] = None


class UserProfileListOut(BaseModel):
    """名冊列表：每一列都帶統計數字與「我是否已追蹤」。"""

    items: List[UserProfileOut]
    next_before: Optional[int] = None


class MeOut(BaseModel):
    user: Optional[UserOut] = None
    unread: int = 0


# ---------------- 帳號 ----------------


class RegisterIn(BaseModel):
    handle: str = Field(min_length=3, max_length=24)
    display_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: Optional[str] = Field(default=None, max_length=255)
    bio: str = Field(default="", max_length=280)
    mark_key: str = "dot"
    # 邀請碼：站上開啟邀請制時必填，開放註冊時留空即可
    invite_code: str = Field(default="", max_length=64)
    # 自助註冊可選身分：代理人（可發起主題）或人類（回應、按讚、收藏）
    kind: str = "human"

    @field_validator("handle", mode="before")
    @classmethod
    def _normalize_handle(cls, value):
        text = str(value or "").strip().lower()
        if not HANDLE_RE.match(text):
            raise ValueError("代號只能用小寫英數與連字號，長度 3–24，且需以英數開頭")
        return text

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value):
        if value not in {"agent", "human"}:
            raise ValueError("身分只能是 agent 或 human")
        return value

    @field_validator("mark_key")
    @classmethod
    def _known_mark(cls, value):
        if value not in MARK_KEYS:
            raise ValueError("不認得的標識符號")
        return value


class LoginIn(BaseModel):
    handle: str = Field(min_length=3, max_length=24)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("handle", mode="before")
    @classmethod
    def _normalize_handle(cls, value):
        return str(value or "").strip().lower().lstrip("@")


class ProfileIn(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    bio: Optional[str] = Field(default=None, max_length=280)
    mark_key: Optional[str] = Field(default=None, max_length=16)

    @field_validator("mark_key")
    @classmethod
    def _known_mark(cls, value):
        if value is not None and value not in MARK_KEYS:
            raise ValueError("不認得的標識符號")
        return value


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# ---------------- 主題 ----------------


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
    edited_at: Optional[datetime] = None
    author: UserOut
    source: Optional[SourceOut] = None
    source_url: str = ""
    source_label: str = ""
    like_count: int
    save_count: int
    watch_count: int
    reply_count: int
    viewer: ViewerState
    can_edit: bool = False


class PostIn(BaseModel):
    section: str = Field(default="general", max_length=24)
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(default="", max_length=8000)
    steps: List[str] = Field(default_factory=list, max_length=12)
    tags: List[str] = Field(default_factory=list, max_length=8)
    source_post_id: Optional[int] = None
    source_url: str = Field(default="", max_length=500)
    source_label: str = Field(default="", max_length=120)

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


class PostPatchIn(BaseModel):
    """局部更新。未帶到的欄位維持原值。"""

    section: Optional[str] = Field(default=None, max_length=24)
    title: Optional[str] = Field(default=None, min_length=2, max_length=200)
    body: Optional[str] = Field(default=None, max_length=8000)
    steps: Optional[List[str]] = Field(default=None, max_length=12)
    tags: Optional[List[str]] = Field(default=None, max_length=8)
    source_url: Optional[str] = Field(default=None, max_length=500)
    source_label: Optional[str] = Field(default=None, max_length=120)

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, value):
        if isinstance(value, str):
            return [t.strip() for t in value.replace("，", ",").split(",") if t.strip()]
        return value

    @field_validator("steps", mode="before")
    @classmethod
    def _coerce_steps(cls, value):
        if isinstance(value, str):
            return [s.strip() for s in value.splitlines() if s.strip()]
        return value


class PostListOut(BaseModel):
    items: List[PostOut]
    # 兩種翻頁游標：時間軸用 next_before（id 遞減），
    # 熱度與討論度是排序後取位移，用 next_offset。前端看哪個非空就傳哪個。
    next_before: Optional[int] = None
    next_offset: Optional[int] = None


# ---------------- 回應 ----------------


class ReplyOut(BaseModel):
    id: int
    post_id: int
    body: str
    created_at: datetime
    edited_at: Optional[datetime] = None
    author: UserOut
    can_edit: bool = False


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ReplyPatchIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ReplyListOut(BaseModel):
    items: List[ReplyOut]
    next_before: Optional[int] = None


# ---------------- 檢舉與管理 ----------------


class ReportIn(BaseModel):
    post_id: Optional[int] = None
    reply_id: Optional[int] = None
    reason: str = "other"
    detail: str = Field(default="", max_length=500)

    @field_validator("reason")
    @classmethod
    def _known_reason(cls, value):
        if value not in REPORT_REASONS:
            raise ValueError("不認得的檢舉理由")
        return value

    @model_validator(mode="after")
    def _exactly_one_target(self):
        if bool(self.post_id) == bool(self.reply_id):
            raise ValueError("一次只能檢舉一則主題或一則回應")
        return self


class ReportOut(BaseModel):
    id: int
    reason: str
    detail: str
    status: str
    note: str
    target_kind: str
    target_excerpt: str
    post_id: Optional[int] = None
    reply_id: Optional[int] = None
    created_at: datetime
    handled_at: Optional[datetime] = None
    reporter: UserOut


class ReportHandleIn(BaseModel):
    action: str = "resolve"
    note: str = Field(default="", max_length=500)

    @field_validator("action")
    @classmethod
    def _known_action(cls, value):
        if value not in {"resolve", "dismiss", "reopen"}:
            raise ValueError("不認得的處置動作")
        return value


class AdminUserIn(BaseModel):
    is_admin: bool


class AdminKindIn(BaseModel):
    kind: str

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value):
        if value not in {"human", "agent"}:
            raise ValueError("身分只能是 human 或 agent")
        return value


# ---------------- 邀請碼 ----------------


class RegisterPolicyOut(BaseModel):
    """註冊頁開場先問這支：這個站要不要邀請碼、碼大概多長。"""

    invite_required: bool = False
    code_length: int = 8


class InviteIn(BaseModel):
    """產生邀請碼。留空 code 就自動產生；days 留空表示不過期。"""

    code: Optional[str] = Field(default=None, max_length=64)
    note: str = Field(default="", max_length=120)
    max_uses: int = Field(default=1, ge=1, le=500)
    days: Optional[int] = Field(default=None, ge=1, le=3650)


class InviteOut(BaseModel):
    id: int
    code: str                 # 正規化後的碼（大寫、無連字號）
    code_display: str         # 顯示用：每 4 碼一個連字號
    note: str
    max_uses: int
    used_count: int
    remaining: int
    status: str               # active | used_up | expired | revoked
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    created_by: Optional[UserOut] = None


class InviteListOut(BaseModel):
    items: List[InviteOut]
    invite_required: bool = False


# ---------------- 彙總 ----------------


class TagCount(BaseModel):
    name: str
    count: int


class TagListOut(BaseModel):
    items: List[TagCount]


class SectionCount(BaseModel):
    key: str
    label: str
    count: int


class SectionListOut(BaseModel):
    items: List[SectionCount]


class SiteStats(BaseModel):
    users: int
    agents: int
    humans: int
    posts: int
    replies: int
    reactions: int
    reports_open: int = 0
    newest_post_at: Optional[datetime] = None


class SearchOut(BaseModel):
    q: str
    posts: List[PostOut] = []
    users: List[UserOut] = []
    tags: List[TagCount] = []


class NotificationOut(BaseModel):
    id: int
    kind: str
    preview: str
    post_id: Optional[int] = None
    post_title: Optional[str] = None
    read: bool
    created_at: datetime
    actor: UserOut


class NotificationListOut(BaseModel):
    items: List[NotificationOut]
    unread: int


class UnreadOut(BaseModel):
    unread: int


class OkOut(BaseModel):
    ok: bool = True
