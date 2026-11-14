"""Validated input and output contracts for Phase 1."""

from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SpeciesRead(ReadSchema):
    id: str
    scientific_name: str
    common_name_vi: str
    status: str


class CultureSystemRead(ReadSchema):
    id: str
    name_vi: str
    description: str


class FarmCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    region: str | None = Field(default=None, max_length=120)


class FarmRead(ReadSchema):
    id: int
    name: str
    region: str | None
    created_at: datetime


class TankCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    unit_type: Literal["tank"] = "tank"
    culture_system_id: str = "mudfree_tank"
    area_m2: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    volume_m3: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class TankRead(ReadSchema):
    id: int
    farm_id: int
    name: str
    unit_type: str
    culture_system_id: str
    area_m2: float | None
    volume_m3: float | None


class CycleCreate(BaseModel):
    species_id: str = "monopterus_albus"
    start_date: date
    planned_end_date: date | None = None
    stocked_count: int = Field(gt=0)
    stocked_avg_weight_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_dates(self) -> "CycleCreate":
        if self.planned_end_date and self.planned_end_date < self.start_date:
            raise ValueError("planned_end_date cannot precede start_date")
        return self


class CycleRead(ReadSchema):
    id: int
    unit_id: int
    species_id: str
    start_date: date
    planned_end_date: date | None
    stocked_count: int
    stocked_avg_weight_g: float | None


# Phase 1C journal validation. Values are observations or user-entered data,
# never safety thresholds or inferred biological predictions.
class JournalBase(BaseModel):
    recorded_on: date
    notes: str | None = Field(default=None, max_length=1000)


class FeedingCreate(JournalBase):
    feed_name: str = Field(min_length=1, max_length=120)
    amount_kg: float = Field(gt=0, allow_inf_nan=False)


class FeedingRead(FeedingCreate, ReadSchema):
    id: int
    cycle_id: int


class WaterQualityCreate(JournalBase):
    temperature_c: float | None = Field(default=None, ge=0, le=50, allow_inf_nan=False)
    ph: float | None = Field(default=None, ge=0, le=14, allow_inf_nan=False)
    dissolved_oxygen_mg_l: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ammonia_mg_l: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ammonia_type: Literal["TAN", "NH3"] | None = None

    @model_validator(mode="after")
    def measurements_present(self) -> "WaterQualityCreate":
        if all(value is None for value in (self.temperature_c, self.ph, self.dissolved_oxygen_mg_l, self.ammonia_mg_l)):
            raise ValueError("At least one water measurement is required")
        if (self.ammonia_mg_l is None) != (self.ammonia_type is None):
            raise ValueError("ammonia_mg_l and ammonia_type must be provided together")
        return self


class WaterQualityRead(WaterQualityCreate, ReadSchema):
    id: int
    cycle_id: int


class GrowthSampleCreate(JournalBase):
    sample_count: int = Field(gt=0)
    avg_weight_g: float = Field(gt=0, allow_inf_nan=False)


class GrowthSampleRead(GrowthSampleCreate, ReadSchema):
    id: int
    cycle_id: int


class ExpenseCreate(JournalBase):
    category: Literal["feed", "seed", "electricity", "labor", "equipment", "treatment", "testing", "other"]
    amount_vnd: int = Field(gt=0)


class ExpenseRead(ExpenseCreate, ReadSchema):
    id: int
    cycle_id: int


class CareActivityCreate(JournalBase):
    activity_type: Literal["water_change", "cleaning", "grading", "inspection", "other"]
    water_replaced_percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    notes: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def percent_only_for_water_changes(self) -> "CareActivityCreate":
        if self.water_replaced_percent is not None and self.activity_type != "water_change":
            raise ValueError("water_replaced_percent is only for water_change")
        return self


class CareActivityRead(CareActivityCreate, ReadSchema):
    id: int
    cycle_id: int


class CycleJournalSummary(BaseModel):
    cycle_id: int
    feeding_entries: int
    feed_total_kg: float
    water_entries: int
    growth_samples: int
    care_entries: int
    expense_entries: int
    recorded_expenses_vnd: int
