"""Local-only AquaConnect: traceability, private documents, records readiness, and price scenarios."""
from datetime import date, datetime
import hashlib
import io
import math
import os
from pathlib import Path
import re
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .connect_models import HarvestBatch, QualityDocument
from .db import get_db
from .models import ExpenseRecord, FeedingRecord, FarmingUnit, GrowthSample, ProductionCycle, Species, WaterQualityRecord

router = APIRouter(tags=['AquaConnect'])
DOC_ROOT = Path(__file__).resolve().parents[1] / 'private_uploads' / 'quality_documents'
MAX_FILE_BYTES = 5 * 1024 * 1024
STANDARD_URL = 'https://tieuchuan.vsqi.gov.vn/tieuchuan/view?sohieu=TCVN+13528-1%3A2022'
FILE_TYPES = {'application/pdf': '.pdf', 'image/png': '.png', 'image/jpeg': '.jpg'}


class BatchCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    batch_code: str = Field(min_length=3, max_length=48, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]+$')
    harvest_date: date
    quantity_kg: float = Field(gt=0, le=1_000_000_000, allow_inf_nan=False)
    source_kind: Literal['user_reported', 'synthetic_demo']
    public_label: str = Field(default='', max_length=100)
    notes: str = Field(default='', max_length=700)

    @model_validator(mode='after')
    def valid_user_date(self):
        if self.source_kind == 'user_reported' and self.harvest_date > date.today():
            raise ValueError('User-reported harvest date cannot be in the future')
        return self


class BatchRead(BatchCreate):
    id: int
    cycle_id: int
    is_published: bool
    public_token: str
    created_at: datetime


class PublishRequest(BaseModel):
    published: bool


class DocumentRead(BaseModel):
    id: int
    batch_id: int
    kind: str
    title: str
    issuer: str
    reference_number: str
    document_date: date | None
    original_filename: str
    content_type: str
    size_bytes: int
    sha256_hex: str
    verification_status: str
    created_at: datetime


class ReadinessItem(BaseModel):
    key: str
    title: str
    available: bool
    reason: str


class ReadinessReport(BaseModel):
    standard_reference: str
    standard_url: str
    template_version: str
    nature: str
    complete_count: int
    total_count: int
    items: list[ReadinessItem]


class MarketScenario(BaseModel):
    baseline_price_vnd_per_kg: int = Field(ge=0, le=1_000_000_000)
    proposed_price_vnd_per_kg: int = Field(ge=0, le=1_000_000_000)
    testing_cost_vnd: int = Field(ge=0, le=1_000_000_000_000)
    certification_cost_vnd: int = Field(ge=0, le=1_000_000_000_000)
    additional_logistics_vnd: int = Field(ge=0, le=1_000_000_000_000)


class MarketComparison(BaseModel):
    quantity_kg: float
    baseline_revenue_vnd: int
    proposed_revenue_vnd: int
    additional_cost_vnd: int
    net_difference_vnd: int
    minimum_premium_vnd_per_kg: int
    warning: str


def _cycle(cycle_id: int, db: Session) -> ProductionCycle:
    cycle = db.get(ProductionCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail='Production cycle not found')
    if cycle.species_id != 'monopterus_albus':
        raise HTTPException(status_code=422, detail='Species not validated for this MVP')
    return cycle


def _batch(batch_id: int, db: Session) -> HarvestBatch:
    item = db.get(HarvestBatch, batch_id)
    if item is None:
        raise HTTPException(status_code=404, detail='Harvest batch not found')
    return item


def _serialize_batch(item: HarvestBatch) -> BatchRead:
    return BatchRead.model_validate(item, from_attributes=True)


@router.get('/api/cycles/{cycle_id}/batches', response_model=list[BatchRead])
def list_batches(cycle_id: int, db: Session = Depends(get_db)):
    _cycle(cycle_id, db)
    return [_serialize_batch(b) for b in db.scalars(select(HarvestBatch).where(HarvestBatch.cycle_id == cycle_id).order_by(HarvestBatch.id.desc())).all()]


@router.post('/api/cycles/{cycle_id}/batches', response_model=BatchRead, status_code=status.HTTP_201_CREATED)
def create_batch(cycle_id: int, payload: BatchCreate, db: Session = Depends(get_db)):
    cycle = _cycle(cycle_id, db)
    if os.getenv('AQUAVERSE_PUBLIC_DEMO') == '1' and payload.source_kind != 'synthetic_demo':
        raise HTTPException(status_code=422, detail='Public demo accepts synthetic harvest data only')
    if payload.harvest_date < cycle.start_date:
        raise HTTPException(status_code=422, detail='Harvest date precedes production cycle start')
    row = HarvestBatch(cycle_id=cycle_id, **payload.model_dump(), public_token=secrets.token_urlsafe(32), is_published=False)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Batch code already exists')
    db.refresh(row)
    return _serialize_batch(row)


@router.post('/api/batches/{batch_id}/publish', response_model=BatchRead)
def publish_batch(batch_id: int, payload: PublishRequest, db: Session = Depends(get_db)):
    row = _batch(batch_id, db)
    row.is_published = payload.published
    db.commit()
    db.refresh(row)
    return _serialize_batch(row)


@router.get('/api/public/trace/{token}')
def public_trace(token: str, db: Session = Depends(get_db)):
    # Explicit allowlist only; do not expose any farm, expense, or document details.
    item = db.scalar(select(HarvestBatch).where(HarvestBatch.public_token == token, HarvestBatch.is_published.is_(True)))
    if item is None:
        raise HTTPException(status_code=404, detail='Public traceability record not found')
    cycle = db.get(ProductionCycle, item.cycle_id)
    species = db.get(Species, cycle.species_id)
    return {
        'batch_code': item.batch_code, 'species_name': species.common_name_vi,
        'scientific_name': species.scientific_name, 'harvest_date': item.harvest_date,
        'quantity_kg': item.quantity_kg, 'source_kind': item.source_kind,
        'public_label': item.public_label, 'verification': 'Người dùng khai báo, chưa được bên thứ ba kiểm định',
    }


def _sniff(raw: bytes, name: str, mimetype: str) -> str:
    extension = Path(name).suffix.lower()
    if extension == '.jpeg': extension = '.jpg'
    if extension not in {'.pdf', '.png', '.jpg'}:
        raise HTTPException(status_code=422, detail='Only PDF, PNG and JPG files are allowed')
    match = (extension == '.pdf' and raw.startswith(b'%PDF-')) or \
        (extension == '.png' and raw.startswith(b'\x89PNG\r\n\x1a\n')) or \
        (extension == '.jpg' and raw.startswith(b'\xff\xd8\xff'))
    if not match:
        raise HTTPException(status_code=422, detail='File content does not match allowed extension')
    expected = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg'}[extension]
    if mimetype not in {expected, 'application/octet-stream'}:
        raise HTTPException(status_code=422, detail='File MIME type does not match its content')
    return expected


@router.post('/api/batches/{batch_id}/documents', response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    batch_id: int,
    kind: Literal['lab_report', 'certificate', 'supplier_record', 'other'] = Form(...),
    title: str = Form(..., min_length=3, max_length=140),
    issuer: str = Form('', max_length=140),
    reference_number: str = Form('', max_length=100),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if os.getenv('AQUAVERSE_PUBLIC_DEMO') == '1':
        raise HTTPException(status_code=403, detail='File uploads are disabled in public demo')
    _batch(batch_id, db)
    # Do not trust client-declared size, filename or content type.
    payload = await file.read(MAX_FILE_BYTES + 1)
    await file.close()
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail='File must be between 1 byte and 5 MB')
    original = Path((file.filename or '').replace('\\', '/')).name
    if not original or len(original) > 180:
        raise HTTPException(status_code=422, detail='Invalid filename')
    content_type = _sniff(payload, original, file.content_type or '')
    destination = secrets.token_hex(20) + FILE_TYPES[content_type]
    DOC_ROOT.mkdir(parents=True, exist_ok=True)
    path = DOC_ROOT / destination
    # Exclusive file creation; uploaded files are NOT served from the public API.
    with path.open('xb') as handle:
        handle.write(payload)
    row = QualityDocument(
        batch_id=batch_id, kind=kind, title=title.strip(), issuer=issuer.strip(),
        reference_number=reference_number.strip(), document_date=None,
        original_filename=original, stored_filename=destination,
        content_type=content_type, size_bytes=len(payload), sha256_hex=hashlib.sha256(payload).hexdigest(),
        verification_status='not_independently_verified',
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    db.refresh(row)
    return DocumentRead.model_validate(row, from_attributes=True)


@router.get('/api/batches/{batch_id}/documents', response_model=list[DocumentRead])
def list_documents(batch_id: int, db: Session = Depends(get_db)):
    _batch(batch_id, db)
    return [DocumentRead.model_validate(d, from_attributes=True) for d in db.scalars(select(QualityDocument).where(QualityDocument.batch_id == batch_id).order_by(QualityDocument.id.desc())).all()]


@router.get('/api/batches/{batch_id}/readiness', response_model=ReadinessReport)
def document_readiness(batch_id: int, db: Session = Depends(get_db)):
    batch = _batch(batch_id, db)
    cycle_id = batch.cycle_id
    docs = db.scalars(select(QualityDocument).where(QualityDocument.batch_id == batch_id)).all()
    def exists(model):
        return db.scalar(select(model.id).where(model.cycle_id == cycle_id).limit(1)) is not None
    flags = [
        ('stocking', 'Thông tin thả giống', True, 'Vụ nuôi có hồ sơ thả giống; chưa kiểm tra nguồn giống'),
        ('feeding', 'Nhật ký thức ăn', exists(FeedingRecord), 'Cần có dữ liệu cho ăn trong AquaFarm'),
        ('water', 'Nhật ký chất lượng nước', exists(WaterQualityRecord), 'Cần có bản ghi theo dõi nước trong AquaFarm'),
        ('expenses', 'Nhật ký chi phí', exists(ExpenseRecord), 'Cần có bản ghi chi phí trong AquaFarm'),
        ('lab', 'Phiếu kiểm nghiệm', any(d.kind == 'lab_report' for d in docs), 'Cần đính kèm phiếu kiểm nghiệm; chưa xác minh tính thật'),
        ('supplier', 'Hồ sơ nhà cung cấp', any(d.kind == 'supplier_record' for d in docs), 'Có thể đính kèm hóa đơn/biên nhận nguồn giống hoặc thức ăn'),
    ]
    items = [ReadinessItem(key=key, title=title, available=flag, reason=reason) for key, title, flag, reason in flags]
    return ReadinessReport(
        standard_reference='TCVN 13528-1:2022 — VietGAP (tham khảo phạm vi)',
        standard_url=STANDARD_URL,
        template_version='internal-doc-checklist-v1',
        nature='Checklist sự hiện diện của hồ sơ, KHÔNG phải danh mục đầy đủ hoặc xác nhận đạt chuẩn VietGAP.',
        complete_count=sum(i.available for i in items), total_count=len(items), items=items,
    )


@router.post('/api/batches/{batch_id}/market-comparison', response_model=MarketComparison)
def market_comparison(batch_id: int, payload: MarketScenario, db: Session = Depends(get_db)):
    batch = _batch(batch_id, db)
    kg = batch.quantity_kg
    base = round(kg * payload.baseline_price_vnd_per_kg)
    proposed = round(kg * payload.proposed_price_vnd_per_kg)
    additional_cost = payload.testing_cost_vnd + payload.certification_cost_vnd + payload.additional_logistics_vnd
    return MarketComparison(
        quantity_kg=kg, baseline_revenue_vnd=base, proposed_revenue_vnd=proposed,
        additional_cost_vnd=additional_cost, net_difference_vnd=proposed - base - additional_cost,
        minimum_premium_vnd_per_kg=math.ceil(additional_cost / kg),
        warning='Chỉ là phân tích kịch bản giá và chi phí BỔ SUNG. Không có người mua, mức giá chênh lệch hoặc chứng nhận nào được bảo đảm.',
    )


@router.get('/api/batches/{batch_id}/qr.svg')
def batch_qr(batch_id: int, db: Session = Depends(get_db)):
    batch = _batch(batch_id, db)
    if not batch.is_published:
        raise HTTPException(status_code=409, detail='Publish batch before generating its traceability QR')
    import qrcode
    from qrcode.image.svg import SvgPathImage
    base_url = (os.environ.get('AQUAVERSE_PUBLIC_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL') or 'http://localhost:5173').rstrip('/')
    if not (base_url.startswith('http://localhost:') or base_url.startswith('http://127.0.0.1:') or base_url.startswith('https://')):
        raise HTTPException(status_code=500, detail='Public frontend URL is not configured securely')
    address = f'{base_url}/trace/{batch.public_token}'
    svg = qrcode.make(address, image_factory=SvgPathImage).to_string()
    return Response(content=svg, media_type='image/svg+xml', headers={'Cache-Control': 'no-store'})
