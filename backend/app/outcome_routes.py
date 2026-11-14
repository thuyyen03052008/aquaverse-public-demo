"""User-reported vs saved-scenario comparison; NOT prediction accuracy validation."""
from datetime import date, datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import get_db
from .decision_models import DecisionChoice, DecisionScenario
from .decision_routes import cycle_or_404
from .outcome_models import DecisionOutcome

router = APIRouter(prefix='/api/cycles/{cycle_id}/decision', tags=['AquaDecision Outcomes'])


class OutcomeCreate(BaseModel):
    choice_id: int = Field(gt=0)
    recorded_on: date
    source_kind: Literal['user_reported', 'synthetic_demo']
    harvested_count: int = Field(ge=0)
    harvest_biomass_kg: float = Field(ge=0, le=1_000_000_000, allow_inf_nan=False)
    actual_feed_kg: float | None = Field(default=None, ge=0, le=1_000_000_000, allow_inf_nan=False)
    total_cost_vnd: int = Field(ge=0, le=1_000_000_000_000_000)
    revenue_vnd: int = Field(ge=0, le=1_000_000_000_000_000)
    notes: str = Field(default='', max_length=600)

    @model_validator(mode='after')
    def count_matches_weight(self):
        if (self.harvested_count == 0) != (self.harvest_biomass_kg == 0):
            raise ValueError('Nếu không thu hoạch con nào thì khối lượng phải bằng 0, và ngược lại')
        if self.source_kind == 'user_reported' and self.recorded_on > date.today():
            raise ValueError('Không được khai báo dữ liệu quan sát thực tế với ngày trong tương lai')
        return self


class OutcomeComparison(BaseModel):
    scenario_id: int
    scenario_name: str
    planned_harvest_biomass_kg: float
    reported_harvest_biomass_kg: float
    delta_harvest_biomass_kg: float
    planned_revenue_vnd: int
    reported_revenue_vnd: int
    delta_revenue_vnd: int
    planned_cost_vnd: int
    reported_cost_vnd: int
    delta_cost_vnd: int
    planned_balance_vnd: int
    reported_balance_vnd: int
    delta_balance_vnd: int
    planned_feed_kg: float
    reported_feed_kg: float | None
    delta_feed_kg: float | None
    explanation: str


class OutcomeRead(OutcomeCreate):
    id: int
    cycle_id: int
    created_at: datetime
    comparison: OutcomeComparison


def _render_outcome(outcome: DecisionOutcome, scenario: DecisionScenario) -> OutcomeRead:
    planned = scenario.results  # Frozen scenario snapshot from when the choice was saved.
    actual_balance = outcome.revenue_vnd - outcome.total_cost_vnd
    feed_diff = None if outcome.actual_feed_kg is None else round(outcome.actual_feed_kg - planned['estimated_feed_kg'], 3)
    diff = OutcomeComparison(
        scenario_id=scenario.id, scenario_name=scenario.name,
        planned_harvest_biomass_kg=planned['harvest_biomass_kg'],
        reported_harvest_biomass_kg=outcome.harvest_biomass_kg,
        delta_harvest_biomass_kg=round(outcome.harvest_biomass_kg - planned['harvest_biomass_kg'], 3),
        planned_revenue_vnd=planned['estimated_revenue_vnd'], reported_revenue_vnd=outcome.revenue_vnd,
        delta_revenue_vnd=outcome.revenue_vnd - planned['estimated_revenue_vnd'],
        planned_cost_vnd=planned['total_cost_vnd'], reported_cost_vnd=outcome.total_cost_vnd,
        delta_cost_vnd=outcome.total_cost_vnd - planned['total_cost_vnd'],
        planned_balance_vnd=planned['estimated_balance_vnd'], reported_balance_vnd=actual_balance,
        delta_balance_vnd=actual_balance - planned['estimated_balance_vnd'],
        planned_feed_kg=planned['estimated_feed_kg'], reported_feed_kg=outcome.actual_feed_kg,
        delta_feed_kg=feed_diff,
        explanation=(
            'Chênh lệch giữa kịch bản đã lưu và số liệu do người dùng nhập. '
            'Không phải bằng chứng mô hình sinh học dự báo chính xác, '
            'và không được kiểm toán độc lập. Tổng chi phí do người dùng khai báo.'
        ),
    )
    return OutcomeRead(
        id=outcome.id, cycle_id=outcome.cycle_id, choice_id=outcome.choice_id,
        recorded_on=outcome.recorded_on, source_kind=outcome.source_kind,
        harvested_count=outcome.harvested_count, harvest_biomass_kg=outcome.harvest_biomass_kg,
        actual_feed_kg=outcome.actual_feed_kg, total_cost_vnd=outcome.total_cost_vnd,
        revenue_vnd=outcome.revenue_vnd, notes=outcome.notes,
        created_at=outcome.created_at, comparison=diff,
    )


@router.get('/outcomes', response_model=list[OutcomeRead])
def list_outcomes(cycle_id: int, db: Session = Depends(get_db)):
    cycle_or_404(cycle_id, db)
    rows = db.scalars(select(DecisionOutcome).where(DecisionOutcome.cycle_id == cycle_id).order_by(DecisionOutcome.id.desc())).all()
    output = []
    for row in rows:
        choice = db.get(DecisionChoice, row.choice_id)
        scenario = db.get(DecisionScenario, choice.scenario_id)
        output.append(_render_outcome(row, scenario))
    return output


@router.post('/outcomes', response_model=OutcomeRead, status_code=status.HTTP_201_CREATED)
def record_outcome(cycle_id: int, payload: OutcomeCreate, db: Session = Depends(get_db)):
    cycle = cycle_or_404(cycle_id, db)
    choice = db.get(DecisionChoice, payload.choice_id)
    if choice is None or choice.cycle_id != cycle_id:
        raise HTTPException(status_code=404, detail='Decision choice not found for this production cycle')
    scenario = db.get(DecisionScenario, choice.scenario_id)
    if scenario is None or scenario.cycle_id != cycle_id:
        raise HTTPException(status_code=409, detail='Saved scenario is inconsistent with decision choice')
    if payload.recorded_on < cycle.start_date:
        raise HTTPException(status_code=422, detail='Harvest date cannot precede cycle start')
    if payload.harvested_count > cycle.stocked_count:
        raise HTTPException(status_code=422, detail='Reported harvested count exceeds initial stocking count')
    if db.scalar(select(DecisionOutcome.id).where(DecisionOutcome.choice_id == choice.id)) is not None:
        raise HTTPException(status_code=409, detail='This decision already has a recorded outcome')
    row = DecisionOutcome(cycle_id=cycle_id, **payload.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='This decision already has a recorded outcome')
    db.refresh(row)
    return _render_outcome(row, scenario)
