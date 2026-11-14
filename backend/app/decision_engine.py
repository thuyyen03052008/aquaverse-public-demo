"""Deterministic, assumption-based scenario arithmetic; NOT a biological forecast."""
from decimal import Decimal, ROUND_HALF_UP
from pydantic import BaseModel, Field, model_validator

ENGINE_VERSION = 'scenario_finance_v1'


class ScenarioAssumptions(BaseModel):
    # All numerical inputs are entered assumptions; none is a fitted biological parameter.
    starting_avg_weight_g: float = Field(gt=0, le=100000, allow_inf_nan=False)
    harvest_avg_weight_g: float = Field(gt=0, le=100000, allow_inf_nan=False)
    survival_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    fcr_assumed: float = Field(gt=0, le=100, allow_inf_nan=False)
    feed_price_vnd_per_kg: int = Field(ge=0, le=1000000000)
    seed_price_vnd_per_animal: int = Field(ge=0, le=1000000000)
    other_cost_vnd: int = Field(ge=0, le=1000000000000)
    quality_cost_vnd: int = Field(default=0, ge=0, le=1000000000000)
    selling_price_vnd_per_kg: int = Field(ge=0, le=1000000000)

    @model_validator(mode='after')
    def validate_growth(self):
        if self.harvest_avg_weight_g <= self.starting_avg_weight_g:
            raise ValueError('Khối lượng thu hoạch giả định phải lớn hơn khối lượng đầu vụ')
        return self


class ScenarioResult(BaseModel):
    engine_version: str
    stocked_count: int
    expected_surviving_animals: float
    harvest_biomass_kg: float
    survivor_biomass_gain_kg: float
    estimated_feed_kg: float
    feed_cost_vnd: int
    seed_cost_vnd: int
    operating_and_quality_cost_vnd: int
    total_cost_vnd: int
    estimated_revenue_vnd: int
    estimated_balance_vnd: int
    break_even_price_vnd_per_kg: float | None
    assumptions_warning: str


def _d(value: int | float) -> Decimal:
    return Decimal(str(value))


def _vnd(value: Decimal) -> int:
    return int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def compute_scenario(stocked_count: int, p: ScenarioAssumptions) -> ScenarioResult:
    if stocked_count <= 0:
        raise ValueError('Stocked count must be positive')
    surviving = _d(stocked_count) * _d(p.survival_percent) / Decimal('100')
    harvest_biomass = surviving * _d(p.harvest_avg_weight_g) / Decimal('1000')
    surviving_gain = surviving * (_d(p.harvest_avg_weight_g) - _d(p.starting_avg_weight_g)) / Decimal('1000')
    feed_kg = surviving_gain * _d(p.fcr_assumed)
    feed_cost = _vnd(feed_kg * _d(p.feed_price_vnd_per_kg))
    seed_cost = _vnd(_d(stocked_count) * _d(p.seed_price_vnd_per_animal))
    other = p.other_cost_vnd + p.quality_cost_vnd
    total = feed_cost + seed_cost + other
    revenue = _vnd(harvest_biomass * _d(p.selling_price_vnd_per_kg))
    balance = revenue - total
    break_even = float(_d(total) / harvest_biomass) if harvest_biomass > 0 else None
    return ScenarioResult(
        engine_version=ENGINE_VERSION,
        stocked_count=stocked_count,
        expected_surviving_animals=float(surviving),
        harvest_biomass_kg=float(harvest_biomass),
        survivor_biomass_gain_kg=float(surviving_gain),
        estimated_feed_kg=float(feed_kg),
        feed_cost_vnd=feed_cost,
        seed_cost_vnd=seed_cost,
        operating_and_quality_cost_vnd=other,
        total_cost_vnd=total,
        estimated_revenue_vnd=revenue,
        estimated_balance_vnd=balance,
        break_even_price_vnd_per_kg=break_even,
        assumptions_warning=(
            'CHỈ LÀ KỊCH BẢN GIẢ ĐỊNH, KHÔNG PHẢI DỰ BÁO TĂNG TRƯỞNG. '
            'FCR được áp dụng cho mức tăng sinh khối của nhóm sống tới thu hoạch; '
            'chưa mô hình hóa riêng lượng thức ăn tiêu thụ của con chết, hao hụt hoặc thời gian nuôi. '
            'Không tự cộng chi phí nhật ký AquaFarm để tránh tính trùng; người dùng phải nhập đầy đủ chi phí.'
        ),
    )
