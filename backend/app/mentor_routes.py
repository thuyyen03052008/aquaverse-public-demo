"""AquaMentor HTTP API - no farm records or private keys are sent by default."""
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.orm import Session
from .auth import current_user, require_farm_owner, owned_farm_for_cycle
from .auth_models import User
from .db import get_db
from .mentor_farm_context import cycle_snapshot, explain_snapshot
from .mentor_search_v2 import classify_intent
from .mentor_engine import answer_question, load_knowledge
from .mentor_semantic import semantic_ready, load_verified_index

router = APIRouter(prefix='/api/mentor', tags=['AquaMentor'])

class ChatTurn(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=800)

class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=600)
    species_id: str = 'monopterus_albus'
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)
    # Read local farm records ONLY if the user explicitly selected this scope in the UI.
    cycle_id: int | None = Field(default=None, gt=0)

@router.get('/status')
def mentor_status():
    return {
        'status': 'ready',
        'mode': 'rag_llm' if os.getenv('OPENAI_API_KEY') and os.getenv('AQUAVERSE_OPENAI_MODEL') else 'evidence_only',
        'source_count': len(load_knowledge()),
        'semantic_ready': semantic_ready(load_knowledge()),
        'semantic_index_valid': load_verified_index(load_knowledge()) is not None,
        'imported_document_count': sum(s.get('source_type') == 'user_pdf' for s in load_knowledge()),
        'species_supported': ['monopterus_albus'],
        'knowledge_level': 'curated_summaries_and_reviewed_pdf_excerpts',
    }

@router.get('/sources')
def mentor_sources():
    return [{**{k: s[k] for k in ('id', 'title', 'authors', 'year', 'url', 'context', 'species_id')},
             'source_type': s.get('source_type', 'curated_summary'),
             'pages': s.get('pages')} for s in load_knowledge()]

@router.post('/ask')
def ask(data: AskRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Never forward previous assistant responses (which may include farm data) into an external AI call.
    history = [m.model_dump() for m in data.history if m.role == 'user']
    if data.cycle_id is None:
        return answer_question(data.question, data.species_id, history)
    farm_id = owned_farm_for_cycle(db, data.cycle_id)
    if farm_id is None:
        raise HTTPException(status_code=404, detail='Vụ nuôi không tồn tại')
    require_farm_owner(db, farm_id, user.id)
    snapshot = cycle_snapshot(db, data.cycle_id)
    # A question about farm observations is answered deterministically, not by an LLM.
    if classify_intent(data.question) in ('farm_data', 'saved_decision'):
        return {
            'species_id': data.species_id, 'evidence': [], 'mode': 'farm_data',
            'intent': 'farm_data', 'search_method': 'read_only_aquafarm_snapshot',
            'answer': explain_snapshot(snapshot), 'farm_snapshot': snapshot,
            'warning': ('Tóm tắt từ nhật ký do người dùng nhập; số đo không được tự động xác minh. '
                        'Không kết luận an toàn, bệnh hoặc lợi nhuận thực tế từ dữ liệu thiếu.'),
        }
    # RAG and external LLM (when configured) receive ONLY the user's question/history.
    # The private farm snapshot is attached to the local response AFTER generation.
    reply = answer_question(data.question, data.species_id, history)
    return {**reply, 'farm_snapshot': snapshot,
            'warning': reply['warning'] + ' Thông tin AquaFarm chỉ hiển thị riêng; không được gửi vào LLM.'}

