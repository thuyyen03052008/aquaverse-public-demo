"""AquaConnect local pilot: user-entered batch facts and PRIVATE quality evidence.

These records do not establish any certification or lab authenticity.
"""
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class HarvestBatch(Base):
    __tablename__ = 'harvest_batches'
    __table_args__ = (UniqueConstraint('batch_code', name='uq_harvest_batch_code'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey('production_cycles.id', ondelete='RESTRICT'), nullable=False, index=True)
    batch_code: Mapped[str] = mapped_column(String(48), nullable=False)
    harvest_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_kg: Mapped[float] = mapped_column(Float, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default='', nullable=False)
    public_label: Mapped[str] = mapped_column(String(100), default='', nullable=False)
    public_token: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class QualityDocument(Base):
    __tablename__ = 'quality_documents'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('harvest_batches.id', ondelete='RESTRICT'), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    issuer: Mapped[str] = mapped_column(String(140), default='', nullable=False)
    reference_number: Mapped[str] = mapped_column(String(100), default='', nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_filename: Mapped[str] = mapped_column(String(180), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(80), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    sha256_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Upload is NOT third-party validation. Never mark verified from upload.
    verification_status: Mapped[str] = mapped_column(String(28), default='not_independently_verified', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
