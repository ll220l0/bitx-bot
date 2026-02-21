from datetime import datetime

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)

    source: Mapped[str] = mapped_column(String(30), default="telegram")
    name: Mapped[str] = mapped_column(String(100))
    company: Mapped[str] = mapped_column(String(150))
    service: Mapped[str] = mapped_column(String(100))
    budget: Mapped[str] = mapped_column(String(50))
    contact: Mapped[str] = mapped_column(String(100))
    details: Mapped[str] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(20), default="new")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class LeadDraft(Base):
    __tablename__ = "lead_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(unique=True, index=True)
    source: Mapped[str] = mapped_column(String(30), default="telegram")
    tg_user_id: Mapped[int | None] = mapped_column(nullable=True)
    tg_username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    step: Mapped[str] = mapped_column(String(20), default="name")

    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company: Mapped[str | None] = mapped_column(String(150), nullable=True)
    service: Mapped[str | None] = mapped_column(String(100), nullable=True)
    budget: Mapped[str | None] = mapped_column(String(50), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
