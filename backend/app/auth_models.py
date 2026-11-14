"""AQUAVERSE Phase 5A: additive account, session, and ownership tables.

No existing farm/cycle tables are rewritten by this phase. Legacy farms remain
unclaimed (and inaccessible through authenticated APIs) until explicitly assigned
by the local CLI tool after a backup.
"""

from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    experience_level: Mapped[str] = mapped_column(String(30), default='beginner', nullable=False)
    goal: Mapped[str] = mapped_column(String(200), default='manage_farm', nullable=False)
    preferred_species_id: Mapped[str] = mapped_column(String(80), default='monopterus_albus', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class FarmOwnership(Base):
    __tablename__ = 'farm_ownership'
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
