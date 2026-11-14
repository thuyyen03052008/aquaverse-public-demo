"""Additive decision history tables, isolated by cycle."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class DecisionScenario(Base):
    __tablename__ = 'decision_scenarios'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey('production_cycles.id', ondelete='RESTRICT'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    assumptions: Mapped[dict] = mapped_column(JSON, nullable=False)
    results: Mapped[dict] = mapped_column(JSON, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DecisionChoice(Base):
    __tablename__ = 'decision_choices'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey('production_cycles.id', ondelete='RESTRICT'), nullable=False, index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey('decision_scenarios.id', ondelete='RESTRICT'), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
