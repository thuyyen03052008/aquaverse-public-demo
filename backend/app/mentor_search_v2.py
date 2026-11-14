"""AquaMentor Phase 5M1: deterministic BM25 lexical retrieval.

This module deliberately does not claim semantic embedding retrieval. Embeddings,
reranking, and private farm tools are separate, explicitly evaluated phases.
"""
from __future__ import annotations

from collections import Counter
import math
import re

# Import from the existing module at function-call time to avoid circular imports.


def query_terms(question: str, keyword_func) -> set[str]:
    terms = set(keyword_func(question))
    # Small, explicit and auditable synonym handling for common Vietnamese variants.
    if {'thuc', 'an'} <= terms or {'cho', 'an'} <= terms or 'khau' in terms:
        terms.update({'thuc', 'an', 'khau', 'phan'})
    if 'oxygen' in terms or 'oxy' in terms or 'do' in terms and 'hoa' in terms and 'tan' in terms:
        terms.update({'oxy', 'suc', 'khi'})
    if {'gia', 'ban'} <= terms or {'hoa', 'von'} <= terms:
        terms.update({'loi', 'nhuan', 'chi', 'phi'})
    if {'loi', 'nhuan'} <= terms:
        terms.update({'gia', 'ban', 'chi', 'phi'})
    if {'sinh', 'san'} <= terms or 'de' in terms or {'trung', 'luon'} <= terms:
        terms.update({'sinh', 'san', 'de', 'trung', 'bo', 'me', 'duc', 'cai', 'thanh', 'thuc', 'to', 'bot'})
    return terms


def classify_intent(question: str) -> str:
    import unicodedata
    folded = question.casefold()
    normalized = unicodedata.normalize('NFD', folded)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn').replace('đ', 'd')
    # A user's real-life example is not a request to secretly query their farm database.
    if (any(term in folded for term in ('nấm', 'điều trị', 'bệnh', 'bỏ ăn', 'lở loét', 'trầy', 'chết hàng loạt'))
            or any(term in normalized for term in ('dieu tri', 'benh', 'bo an', 'lo loet', 'tray minh', 'chet hang loat'))):
        return 'high_risk_health'
    if any(term in normalized for term in ('sinh san', 'khong de', 'chua de', 'mua de', 'de trung', 'trung luon', 'khong thay trung',
                                           'luon de', 'phoi giong', 'ghep cap', 'luon bo me', 'lam to')):
        return 'reproduction'
    if any(t in folded for t in ('bể của tôi', 'ao của tôi', 'trang trại của tôi', 'vụ nuôi của tôi',
                                   'nhật ký của tôi', 'dữ liệu bể', 'bể hiện tại', 'vụ này của tôi')):
        return 'farm_data'
    if any(t in folded for t in ('kịch bản tôi đã lưu', 'phương án a của tôi', 'phương án b của tôi',
                                   'so sánh hai kịch bản của tôi')):
        return 'saved_decision'
    if any(t in folded for t in ('vietgap', 'asc ', 'bap ', 'giấy chứng nhận', 'chứng chỉ', 'kiểm định')):
        return 'quality'
    if any(t in folded for t in ('nấm', 'saprolegnia', 'điều trị', 'thuốc chữa', 'liều thuốc', 'kê thuốc')):
        return 'high_risk_health'
    return 'knowledge'


def resolve_followup(question: str, history: list[dict] | None) -> str:
    """Use only latest user question as short retrieval context; never persist it."""
    if not history or len(question) > 130:
        return question
    folded = question.strip().casefold()
    followup_starts = ('còn ', 'thế ', 'vậy ', 'giải thích thêm', 'nói rõ hơn', 'tại sao vậy',
                       'vì sao vậy', 'nó ', 'điều đó ', 'cái đó ')
    if not any(folded.startswith(prefix) for prefix in followup_starts):
        return question
    last_user = next((m.get('content', '') for m in reversed(history) if m.get('role') == 'user'), '')
    return f'{last_user} {question}' if last_user else question


def rank_passages(question: str, species_id: str, sources: tuple[dict, ...], keywords, limit: int = 4, intent: str = 'knowledge') -> list[dict]:
    if not (1 <= limit <= 10):
        raise ValueError('limit must be between 1 and 10')
    terms = query_terms(question, keywords)
    if not terms:
        return []
    passages = []
    for source in sources:
        if source.get('species_id') != species_id:
            continue
        if intent == 'reproduction' and source.get('category') != 'reproduction':
            continue
        if intent == 'knowledge' and source.get('category') == 'reproduction':
            continue
        for part in source.get('passages', []):
            text = ' '.join((part.get('topic', ''), part['text'], source.get('title', ''), source.get('context', '')))
            tokens = list(keywords(text))  # set-based baseline; no false term-frequency precision claimed
            if tokens:
                passages.append((source, part, set(tokens), set(keywords(part.get('topic', '')))))
    n = len(passages)
    if not n:
        return []
    dfs = Counter(word for _, _, words, _ in passages for word in words)
    scores = []
    for source, part, words, topic_words in passages:
        matched = terms & words
        if not matched:
            continue
        # Reject low-information single-word matches. One technical term is permitted.
        technical = {'fcr', 'ras', 'moina', 'tubifex', 'saprolegnia', 'ammonia', 'oxy'}
        if len(matched) < 2 and not matched & technical:
            continue
        # BM25-inspired IDF score for presence, plus stronger topic match.
        score = sum(math.log(1 + (n - dfs[w] + 0.5) / (dfs[w] + 0.5)) for w in matched)
        score += 0.40 * len(matched & topic_words)
        score += 0.08 * len(matched)
        scores.append((score, {
            'passage_id': part['id'], 'source_id': source['id'], 'title': source['title'],
            'year': source['year'], 'url': source['url'], 'scope': source['context'],
            'excerpt': part['text'], 'score': round(score, 4), 'page': part.get('page'),
            'source_type': source.get('source_type', 'curated_summary'),
        }))
    scores.sort(key=lambda x: (-x[0], x[1]['source_id'], x[1]['passage_id']))
    if not scores:
        return []
    best = scores[0][0]
    selected = []
    used_sources = set()
    for score, item in scores:
        if score < best * 0.45:
            continue
        # Keep source diversity while still allowing a second passage from one PDF if needed.
        if item['source_id'] in used_sources and len(selected) >= 2:
            continue
        selected.append(item)
        used_sources.add(item['source_id'])
        if len(selected) >= limit:
            break
    return selected
