"""AquaMentor read-only farm snapshot for user-selected, owned cycles.

No model inference, safe/unsafe thresholds, medication advice, or external API
calls occur here. Only aggregated recorded data are returned, not free-text notes.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Farm, FarmingUnit, ProductionCycle, FeedingRecord,
    ExpenseRecord, GrowthSample, WaterQualityRecord, CareActivity,
)


def _last_record(db: Session, model, cycle_id: int):
    return db.scalar(
        select(model).where(model.cycle_id == cycle_id)
        .order_by(model.recorded_on.desc(), model.id.desc()).limit(1)
    )


def _total(db: Session, model, value_col, cycle_id: int, since=None):
    q = select(func.count(model.id), func.coalesce(func.sum(value_col), 0)).where(model.cycle_id == cycle_id)
    if since is not None:
        q = q.where(model.recorded_on >= since)
    count, value = db.execute(q).one()
    return int(count), float(value)


def _r(value):
    return None if value is None else round(float(value), 3)


def cycle_snapshot(db: Session, cycle_id: int) -> dict:
    """Call only after the caller has verified the cycle belongs to this user."""
    cycle = db.get(ProductionCycle, cycle_id)
    tank = db.get(FarmingUnit, cycle.unit_id)
    farm = db.get(Farm, tank.farm_id)

    # A fixed 7-calendar-day lookback including the current day in VN time.
    today = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    since = today - timedelta(days=6)
    feed_entries, feed_kg = _total(db, FeedingRecord, FeedingRecord.amount_kg, cycle_id)
    feed_recent_entries, feed_recent_kg = _total(db, FeedingRecord, FeedingRecord.amount_kg, cycle_id, since)
    expense_entries, expense_vnd = _total(db, ExpenseRecord, ExpenseRecord.amount_vnd, cycle_id)
    recent_expense_entries, recent_expense_vnd = _total(db, ExpenseRecord, ExpenseRecord.amount_vnd, cycle_id, since)
    water = _last_record(db, WaterQualityRecord, cycle_id)
    growth = _last_record(db, GrowthSample, cycle_id)
    feeding = _last_record(db, FeedingRecord, cycle_id)
    care = _last_record(db, CareActivity, cycle_id)
    return {
        'source': 'aquafarm_user_entered_records',
        'farm_name': farm.name,
        'tank_name': tank.name,
        'cycle_id': cycle.id,
        'species_id': cycle.species_id,
        'stocked_count': cycle.stocked_count,
        'start_date': cycle.start_date.isoformat(),
        'as_of_date': today.isoformat(),
        'window_start': since.isoformat(),
        'feed': {'total_entries': feed_entries, 'total_kg': round(feed_kg, 3),
                 'recent_entries': feed_recent_entries, 'recent_kg': round(feed_recent_kg, 3),
                 'last_date': feeding.recorded_on.isoformat() if feeding else None},
        'expenses': {'total_entries': expense_entries, 'total_vnd': int(expense_vnd),
                     'recent_entries': recent_expense_entries, 'recent_vnd': int(recent_expense_vnd)},
        'water_latest': ({'date': water.recorded_on.isoformat(), 'temperature_c': _r(water.temperature_c),
                          'ph': _r(water.ph), 'dissolved_oxygen_mg_l': _r(water.dissolved_oxygen_mg_l),
                          'ammonia_mg_l': _r(water.ammonia_mg_l), 'ammonia_type': water.ammonia_type}
                         if water else None),
        'growth_latest': ({'date': growth.recorded_on.isoformat(), 'sample_count': growth.sample_count,
                           'avg_weight_g': _r(growth.avg_weight_g)} if growth else None),
        'care_last_date': care.recorded_on.isoformat() if care else None,
    }


def explain_snapshot(snapshot: dict) -> str:
    feed = snapshot['feed']
    expense = snapshot['expenses']
    water = snapshot['water_latest']
    growth = snapshot['growth_latest']
    result = [
        f"**Dữ liệu ghi nhận của {snapshot['tank_name']} – vụ #{snapshot['cycle_id']}**",
        f"Thời gian truy vấn: {snapshot['as_of_date']} (Việt Nam). Nguồn: nhật ký AquaFarm do người dùng nhập.",
        f"- Thức ăn: {feed['total_kg']:g} kg / {feed['total_entries']} lần ghi; "
        f"7 ngày lịch gần nhất: {feed['recent_kg']:g} kg / {feed['recent_entries']} lần.",
        f"- Chi phí đã ghi trong nhật ký: {expense['total_vnd']:,} VND "
        f"({expense['total_entries']} khoản); 7 ngày gần nhất: {expense['recent_vnd']:,} VND. ",
    ]
    if water:
        pieces = []
        for key, label, unit in [
            ('temperature_c', 'nhiệt độ', '°C'), ('ph', 'pH', ''),
            ('dissolved_oxygen_mg_l', 'DO', 'mg/L'), ('ammonia_mg_l', 'ammonia', 'mg/L')]:
            if water[key] is not None:
                suffix = f" {water['ammonia_type']}" if key == 'ammonia_mg_l' and water['ammonia_type'] else ''
                pieces.append(f"{label} {water[key]:g} {unit}{suffix}".strip())
        result.append(f"- Lần đo nước gần nhất ({water['date']}): " + (', '.join(pieces) or 'chưa có số đo') + '.')
    else:
        result.append('- Chưa có số đo chất lượng nước trong nhật ký vụ nuôi.')
    if growth:
        result.append(f"- Mẫu tăng trưởng gần nhất ({growth['date']}): trung bình {growth['avg_weight_g']:g} g/con "
                      f"trên {growth['sample_count']} con lấy mẫu.")
    else:
        result.append('- Chưa có mẫu tăng trưởng trong nhật ký.')
    result.append('\nĐây chỉ là **tổng hợp dữ liệu đã nhập**, không phải chẩn đoán hay khẳng định bể an toàn. '
                  'Dữ liệu thiếu hoặc chưa được đo không được suy đoán; '
                  'chi phí ở đây chỉ gồm khoản đã ghi, không phải tổng chi phí sản xuất đã kiểm toán.')
    return '\n'.join(result)
