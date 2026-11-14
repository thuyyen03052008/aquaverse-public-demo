"""Core multi-species farm entities. No biological prediction is included."""

from datetime import date, datetime, timezone
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class Species(Base):
    __tablename__ = "species"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    scientific_name: Mapped[str] = mapped_column(String(140), nullable=False)
    common_name_vi: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class CultureSystem(Base):
    __tablename__ = "culture_systems"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name_vi: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")


class Farm(Base):
    __tablename__ = "farms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    units: Mapped[list["FarmingUnit"]] = relationship(back_populates="farm")


class FarmingUnit(Base):
    __tablename__ = "farming_units"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(20), nullable=False)
    culture_system_id: Mapped[str] = mapped_column(ForeignKey("culture_systems.id"), nullable=False)
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    farm: Mapped[Farm] = relationship(back_populates="units")
    cycles: Mapped[list["ProductionCycle"]] = relationship(back_populates="unit")


class ProductionCycle(Base):
    __tablename__ = "production_cycles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("farming_units.id", ondelete="RESTRICT"), nullable=False, index=True)
    species_id: Mapped[str] = mapped_column(ForeignKey("species.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    stocked_count: Mapped[int] = mapped_column(Integer, nullable=False)
    stocked_avg_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[FarmingUnit] = relationship(back_populates="cycles")


# Phase 1C: additive journal tables. Existing farm/tank/cycle data is not migrated.
class FeedingRecord(Base):
    __tablename__ = "feeding_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("production_cycles.id", ondelete="RESTRICT"), nullable=False, index=True)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    feed_name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount_kg: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class WaterQualityRecord(Base):
    __tablename__ = "water_quality_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("production_cycles.id", ondelete="RESTRICT"), nullable=False, index=True)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    ph: Mapped[float | None] = mapped_column(Float, nullable=True)
    dissolved_oxygen_mg_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    ammonia_mg_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    ammonia_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class GrowthSample(Base):
    __tablename__ = "growth_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("production_cycles.id", ondelete="RESTRICT"), nullable=False, index=True)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_weight_g: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExpenseRecord(Base):
    __tablename__ = "expense_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("production_cycles.id", ondelete="RESTRICT"), nullable=False, index=True)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    amount_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CareActivity(Base):
    __tablename__ = "care_activities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("production_cycles.id", ondelete="RESTRICT"), nullable=False, index=True)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    activity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    water_replaced_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
