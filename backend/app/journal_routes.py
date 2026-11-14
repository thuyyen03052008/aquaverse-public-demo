"""Phase 1C: local-only AquaFarm journal endpoints.

These are CRUD creation/listing primitives, not water-safety alerts, animal-health
recommendations, or production forecasts. No auth: do not deploy publicly.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import (
    CareActivity, ExpenseRecord, FeedingRecord, GrowthSample,
    ProductionCycle, WaterQualityRecord,
)
from .schemas import (
    CareActivityCreate, CareActivityRead, CycleJournalSummary,
    ExpenseCreate, ExpenseRead, FeedingCreate, FeedingRead,
    GrowthSampleCreate, GrowthSampleRead, WaterQualityCreate, WaterQualityRead,
)

router = APIRouter(prefix="/api/cycles/{cycle_id}", tags=["AquaFarm Journal"])


def _cycle_or_404(db: Session, cycle_id: int) -> None:
    if db.get(ProductionCycle, cycle_id) is None:
        raise HTTPException(status_code=404, detail="Production cycle not found")


def _list(db: Session, cycle_id: int, table):
    _cycle_or_404(db, cycle_id)
    return db.scalars(
        select(table)
        .where(table.cycle_id == cycle_id)
        .order_by(table.recorded_on.desc(), table.id.desc())
    ).all()


def _create(db: Session, cycle_id: int, data, table):
    _cycle_or_404(db, cycle_id)
    row = table(cycle_id=cycle_id, **data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/feeding-records", response_model=list[FeedingRead])
def list_feeding_records(cycle_id: int, db: Session = Depends(get_db)):
    return _list(db, cycle_id, FeedingRecord)


@router.post("/feeding-records", response_model=FeedingRead, status_code=status.HTTP_201_CREATED)
def add_feeding_record(cycle_id: int, data: FeedingCreate, db: Session = Depends(get_db)):
    return _create(db, cycle_id, data, FeedingRecord)


@router.get("/water-records", response_model=list[WaterQualityRead])
def list_water_records(cycle_id: int, db: Session = Depends(get_db)):
    return _list(db, cycle_id, WaterQualityRecord)


@router.post("/water-records", response_model=WaterQualityRead, status_code=status.HTTP_201_CREATED)
def add_water_record(cycle_id: int, data: WaterQualityCreate, db: Session = Depends(get_db)):
    return _create(db, cycle_id, data, WaterQualityRecord)


@router.get("/growth-samples", response_model=list[GrowthSampleRead])
def list_growth_samples(cycle_id: int, db: Session = Depends(get_db)):
    return _list(db, cycle_id, GrowthSample)


@router.post("/growth-samples", response_model=GrowthSampleRead, status_code=status.HTTP_201_CREATED)
def add_growth_sample(cycle_id: int, data: GrowthSampleCreate, db: Session = Depends(get_db)):
    return _create(db, cycle_id, data, GrowthSample)


@router.get("/expenses", response_model=list[ExpenseRead])
def list_expenses(cycle_id: int, db: Session = Depends(get_db)):
    return _list(db, cycle_id, ExpenseRecord)


@router.post("/expenses", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def add_expense(cycle_id: int, data: ExpenseCreate, db: Session = Depends(get_db)):
    return _create(db, cycle_id, data, ExpenseRecord)


@router.get("/care-activities", response_model=list[CareActivityRead])
def list_care_activities(cycle_id: int, db: Session = Depends(get_db)):
    return _list(db, cycle_id, CareActivity)


@router.post("/care-activities", response_model=CareActivityRead, status_code=status.HTTP_201_CREATED)
def add_care_activity(cycle_id: int, data: CareActivityCreate, db: Session = Depends(get_db)):
    return _create(db, cycle_id, data, CareActivity)


@router.get("/summary", response_model=CycleJournalSummary)
def get_journal_summary(cycle_id: int, db: Session = Depends(get_db)):
    _cycle_or_404(db, cycle_id)

    def count(table):
        return db.scalar(select(func.count(table.id)).where(table.cycle_id == cycle_id)) or 0

    feed_sum = db.scalar(select(func.sum(FeedingRecord.amount_kg)).where(FeedingRecord.cycle_id == cycle_id)) or 0.0
    expense_sum = db.scalar(select(func.sum(ExpenseRecord.amount_vnd)).where(ExpenseRecord.cycle_id == cycle_id)) or 0
    return CycleJournalSummary(
        cycle_id=cycle_id,
        feeding_entries=count(FeedingRecord),
        feed_total_kg=round(float(feed_sum), 4),
        water_entries=count(WaterQualityRecord),
        growth_samples=count(GrowthSample),
        care_entries=count(CareActivity),
        expense_entries=count(ExpenseRecord),
        recorded_expenses_vnd=int(expense_sum),
    )
