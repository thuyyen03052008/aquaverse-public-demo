"""Phase 2B: human-entered full-harvest outcomes, independent of predictions."""
from datetime import date, datetime, timezone
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class DecisionOutcome(Base):
    __tablename__ = 'decision_outcomes'
    __table_args__ = (UniqueConstraint('choice_id', name='uq_outcome_choice'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey('production_cycles.id', ondelete='RESTRICT'), nullable=False, index=True)
    choice_id: Mapped[int] = mapped_column(ForeignKey('decision_choices.id', ondelete='RESTRICT'), nullable=False, index=True)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    harvested_count: Mapped[int] = mapped_column(Integer, nullable=False)
    harvest_biomass_kg: Mapped[float] = mapped_column(Float, nullable=False)
    actual_feed_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
