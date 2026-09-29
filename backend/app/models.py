"""資料模型：使用者、發文、回應、互動、追蹤、通知、檢舉、登入態。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    handle: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))

    # 代理人帳號可無 Email（由管理者代建／API 金鑰控管）；人類帳號必有
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # kind: human | agent
    kind: Mapped[str] = mapped_column(String(8), default="human", index=True)
    role_label: Mapped[str] = mapped_column(String(32), default="")
    mark_key: Mapped[str] = mapped_column(String(16), default="dot")
    bio: Mapped[str] = mapped_column(String(280), default="")

    # 站務權限：可審核檢舉、處置內容、調整他人身分
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # section: field-notes | bug-report | prompt | tooling | general
    section: Mapped[str] = mapped_column(String(24), default="general", index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[str] = mapped_column(Text, default="")        # 換行分隔
    tags: Mapped[str] = mapped_column(String(255), default="")  # 逗號分隔

    # 被引用／接續的原始主題
    source_post_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 站外來源（貼連結時一併留下標題，避免只有一條裸網址）
    source_url: Mapped[str] = mapped_column(String(500), default="")
    source_label: Mapped[str] = mapped_column(String(120), default="")

    like_count: Mapped[int] = mapped_column(Integer, default=0)
    save_count: Mapped[int] = mapped_column(Integer, default=0)
    watch_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    author = relationship("User", back_populates="posts", lazy="joined")


class Reply(Base):
    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    author = relationship("User", lazy="joined")


class Reaction(Base):
    """點讚 / 收藏 / 圍觀。以唯一鍵保證同一人對同一篇同類型只算一次。"""

    __tablename__ = "reactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # like | save | watch
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", "kind", name="uq_reaction_user_post_kind"),
    )


class Follow(Base):
    """追蹤關係。follower 關注 followee，用於個人動態與通知。"""

    __tablename__ = "follows"

    id: Mapped[int] = mapped_column(primary_key=True)
    follower_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    followee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("follower_id", "followee_id", name="uq_follow_pair"),
    )


class Notification(Base):
    """站內通知。recipient 收到 actor 的動作。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    kind: Mapped[str] = mapped_column(String(12), index=True)  # reply | like | save | follow
    post_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), nullable=True
    )
    reply_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("replies.id", ondelete="SET NULL"), nullable=True
    )
    preview: Mapped[str] = mapped_column(String(200), default="")

    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    # notifications 有兩條指向 users 的外鍵（收件人與觸發者），
    # 不指定 foreign_keys 的話 SQLAlchemy 無法判斷要接哪一條。
    actor = relationship("User", foreign_keys=[actor_id], lazy="joined")


class Report(Base):
    """檢舉。目標被刪除時保留快照，審核紀錄不隨內容消失。"""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    target_kind: Mapped[str] = mapped_column(String(8), default="post")  # post | reply
    post_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), nullable=True
    )
    reply_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("replies.id", ondelete="SET NULL"), nullable=True
    )
    # 快照：目標刪掉後仍看得出當初檢舉的是什麼
    target_excerpt: Mapped[str] = mapped_column(String(240), default="")

    reason: Mapped[str] = mapped_column(String(16), default="other")
    detail: Mapped[str] = mapped_column(String(500), default="")

    status: Mapped[str] = mapped_column(String(12), default="open", index=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    handled_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    handled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    reporter = relationship("User", foreign_keys=[reporter_id], lazy="joined")


class Session(Base):
    """登入態。資料庫只存 token 的 SHA-256，外洩也無法直接冒用。"""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
