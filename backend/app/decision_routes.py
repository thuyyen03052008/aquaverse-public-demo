"""Preview, save, list and select assumption-based production scenarios."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ProductionCycle
from .decision_models import DecisionScenario, DecisionChoice
from .decision_engine import ENGINE_VERSION, ScenarioAssumptions, ScenarioResult, compute_scenario

router = APIRouter(prefix='/api/cycles/{cycle_id}/decision', tags=['AquaDecision'])


class ScenarioDraft(BaseModel):
    assumptions: ScenarioAssumptions


class ScenarioSave(ScenarioDraft):
    name: str = Field(min_length=2, max_length=100)


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cycle_id: int
    name: str
    assumptions: ScenarioAssumptions
    results: ScenarioResult
    engine_version: str
    created_at: datetime


class ChoiceCreate(BaseModel):
    scenario_id: int = Field(gt=0)
    notes: str = Field(default='', max_length=500)


class ChoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cycle_id: int
    scenario_id: int
    notes: str
    created_at: datetime


def cycle_or_404(cycle_id: int, db: Session) -> ProductionCycle:
    cycle = db.get(ProductionCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail='Production cycle not found')
    if cycle.species_id != 'monopterus_albus':
        raise HTTPException(status_code=422, detail='Species profile not validated for scenario engine')
    return cycle


@router.post('/preview', response_model=ScenarioResult)
def preview(cycle_id: int, payload: ScenarioDraft, db: Session = Depends(get_db)):
    cycle = cycle_or_404(cycle_id, db)
    return compute_scenario(cycle.stocked_count, payload.assumptions)


@router.get('/scenarios', response_model=list[ScenarioRead])
def list_scenarios(cycle_id: int, db: Session = Depends(get_db)):
    cycle_or_404(cycle_id, db)
    return db.scalars(select(DecisionScenario).where(DecisionScenario.cycle_id == cycle_id).order_by(DecisionScenario.id.desc())).all()


@router.post('/scenarios', response_model=ScenarioRead, status_code=status.HTTP_201_CREATED)
def save_scenario(cycle_id: int, payload: ScenarioSave, db: Session = Depends(get_db)):
    cycle = cycle_or_404(cycle_id, db)
    result = compute_scenario(cycle.stocked_count, payload.assumptions)
    row = DecisionScenario(
        cycle_id=cycle_id,
        name=payload.name.strip(),
        assumptions=payload.assumptions.model_dump(mode='json'),
        results=result.model_dump(mode='json'),
        engine_version=ENGINE_VERSION,
    )
    if not row.name:
        raise HTTPException(status_code=422, detail='Scenario name cannot be blank')
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get('/choices', response_model=list[ChoiceRead])
def list_choices(cycle_id: int, db: Session = Depends(get_db)):
    cycle_or_404(cycle_id, db)
    return db.scalars(select(DecisionChoice).where(DecisionChoice.cycle_id == cycle_id).order_by(DecisionChoice.id.desc())).all()


@router.post('/choices', response_model=ChoiceRead, status_code=status.HTTP_201_CREATED)
def choose_scenario(cycle_id: int, payload: ChoiceCreate, db: Session = Depends(get_db)):
    cycle_or_404(cycle_id, db)
    scenario = db.get(DecisionScenario, payload.scenario_id)
    if scenario is None or scenario.cycle_id != cycle_id:
        raise HTTPException(status_code=404, detail='Scenario not found for this cycle')
    choice = DecisionChoice(cycle_id=cycle_id, scenario_id=scenario.id, notes=payload.notes)
    db.add(choice)
    db.commit()
    db.refresh(choice)
    return choice
