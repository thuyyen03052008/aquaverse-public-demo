"""Opt-in embedding search for AquaMentor's curated evidence.

- Disabled by default; remote queries/docs require explicit independent consent flags.
- Never indexes private farm records or locally imported PDFs.
- If the index is unavailable or stale, callers fall back to vetted lexical results.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

import httpx

INDEX_PATH = Path(__file__).resolve().parents[1] / 'data' / 'mentor_semantic_index.json'
DEFAULT_MODEL = 'text-embedding-3-small'


def embedding_model() -> str:
    return os.getenv('AQUAVERSE_EMBEDDING_MODEL', DEFAULT_MODEL).strip()


def _indexed_sources(sources: tuple[dict, ...]) -> list[dict]:
    """Only application-curated evidence, never user-submitted PDF contents."""
    return [s for s in sources if s.get('source_type', 'curated_summary') == 'curated_summary'
            and s.get('species_id') == 'monopterus_albus']


def _records(sources: tuple[dict, ...]) -> list[dict]:
    records = []
    for source in _indexed_sources(sources):
        for passage in source.get('passages', []):
            records.append({
                'source_id': source['id'], 'passage_id': passage['id'], 'category': source.get('category', ''),
                'text': ' | '.join((source['title'], passage.get('topic', ''), passage['text'], source.get('context', '')))[:4800],
            })
    return sorted(records, key=lambda r: (r['source_id'], r['passage_id']))


def _fingerprint(records: list[dict]) -> str:
    serial = json.dumps(records, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serial.encode('utf-8')).hexdigest()


def _request_embeddings(texts: list[str], *, key: str, model: str, client_factory=httpx.Client) -> list[list[float]]:
    if not texts:
        return []
    with client_factory(timeout=25.0) as client:
        response = client.post(
            'https://api.openai.com/v1/embeddings',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={'model': model, 'input': texts},
        )
        response.raise_for_status()
        payload = response.json()
    indexed = sorted(payload['data'], key=lambda item: item['index'])
    if len(indexed) != len(texts):
        raise ValueError('Invalid embedding response length')
    output = []
    for item in indexed:
        vector = item['embedding']
        if not vector or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in vector):
            raise ValueError('Invalid embedding vector')
        output.append([float(x) for x in vector])
    if len({len(x) for x in output}) != 1:
        raise ValueError('Inconsistent embedding dimensions')
    return output


def build_index(sources: tuple[dict, ...], *, key: str, output: Path = INDEX_PATH) -> dict:
    """Explicit CLI action: sends only curated evidence texts to embedding provider."""
    if os.getenv('AQUAVERSE_ALLOW_EXTERNAL_KNOWLEDGE_EMBEDDINGS') != '1':
        raise ValueError('External knowledge embedding consent is not enabled')
    if not key.strip():
        raise ValueError('OPENAI_API_KEY missing')
    records = _records(sources)
    if not records:
        raise ValueError('No curated passages available')
    vectors: list[list[float]] = []
    model = embedding_model()
    for i in range(0, len(records), 16):
        vectors.extend(_request_embeddings([r['text'] for r in records[i:i + 16]], key=key, model=model))
    payload = {
        'format_version': 1, 'model': model, 'fingerprint': _fingerprint(records),
        'records': [{**r, 'vector': vec} for r, vec in zip(records, vectors)],
        'privacy': 'curated_sources_only_no_user_pdfs_no_farm_records',
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replace and private permissions; index is generated data, not source code.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='.mentor_', suffix='.tmp',
                                     dir=output.parent, delete=False) as temp:
        temp_path = Path(temp.name)
        os.chmod(temp_path, 0o600)
        json.dump(payload, temp, ensure_ascii=False)
    os.replace(temp_path, output)
    return {'model': model, 'passages': len(records), 'index_file': str(output)}


def load_verified_index(sources: tuple[dict, ...], *, path: Path | None = None) -> dict | None:
    path = path or INDEX_PATH
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        records = _records(sources)
        if (data['format_version'] != 1 or data['model'] != embedding_model()
                or data['fingerprint'] != _fingerprint(records)):
            return None
        keys = {(r['source_id'], r['passage_id']) for r in records}
        saved = data['records']
        if len(saved) != len(records) or {(r['source_id'], r['passage_id']) for r in saved} != keys:
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def semantic_ready(sources: tuple[dict, ...]) -> bool:
    return bool(os.getenv('AQUAVERSE_ENABLE_SEMANTIC') == '1'
                and os.getenv('AQUAVERSE_ALLOW_EXTERNAL_QUERY_EMBEDDINGS') == '1'
                and os.getenv('OPENAI_API_KEY', '').strip()
                and load_verified_index(sources) is not None)


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return -1.0
    den = math.sqrt(sum(v * v for v in a) * sum(v * v for v in b))
    return sum(x * y for x, y in zip(a, b)) / den if den else -1.0


def _looks_private(question: str) -> bool:
    # Conservative: avoid transmitting apparent email, phone or account details.
    return bool(re.search(r'[\w.+-]+@[\w.-]+', question) or re.search(r'\b(?:\+?84|0)\d{9,10}\b', question)
                or re.search(r'\b(?:mật khẩu|password|api.key|địa chỉ nhà)\b', question, re.I))


def hybrid_retrieve(question: str, sources: tuple[dict, ...], lexical: list[dict],
                    *, species_id: str, intent: str, limit: int = 4) -> tuple[list[dict], bool]:
    """Return (ranked evidence, provider_used). Any provider/index issue => lexical fallback."""
    if species_id != 'monopterus_albus' or _looks_private(question) or not semantic_ready(sources):
        return lexical[:limit], False
    data = load_verified_index(sources)
    if data is None:
        return lexical[:limit], False
    try:
        query = _request_embeddings([question], key=os.environ['OPENAI_API_KEY'], model=embedding_model())[0]
    except (httpx.HTTPError, KeyError, ValueError, TypeError, IndexError):
        return lexical[:limit], False
    # Reuse metadata from the verified source registry, never the untrusted index's text.
    indexed = {}
    for source in _indexed_sources(sources):
        if intent == 'reproduction' and source.get('category') != 'reproduction':
            continue
        if intent == 'knowledge' and source.get('category') == 'reproduction':
            continue
        for part in source.get('passages', []):
            indexed[(source['id'], part['id'])] = {
                'passage_id': part['id'], 'source_id': source['id'], 'title': source['title'],
                'year': source['year'], 'url': source['url'], 'scope': source['context'],
                'excerpt': part['text'], 'page': part.get('page'),
                'source_type': source.get('source_type', 'curated_summary'),
            }
    candidates = []
    for r in data['records']:
        key = (r['source_id'], r['passage_id'])
        if key not in indexed:
            continue
        score = _cosine(query, r['vector'])
        # Conservative threshold; tune on expert-labeled questions rather than assuming all neighbors are relevant.
        if score >= 0.43:
            candidates.append((score, key))
    candidates.sort(key=lambda item: -item[0])
    # Reciprocal Rank Fusion (RRF) joins lexical and semantic evidence without assuming score scales match.
    fused: dict[tuple[str, str], float] = {}
    by_key = {k: v for k, v in indexed.items()}
    for i, item in enumerate(lexical):
        k = (item['source_id'], item['passage_id'])
        if k not in by_key and item.get('source_type') != 'user_pdf':
            continue
        by_key[k] = item
        fused[k] = fused.get(k, 0.0) + 1.0 / (60 + i + 1)
    for i, (_, k) in enumerate(candidates):
        fused[k] = fused.get(k, 0.0) + 1.0 / (60 + i + 1)
    ordered = sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))
    result = []
    for k, score in ordered[:limit]:
        result.append({**by_key[k], 'score': round(score, 6)})
    return result, True


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ('index', 'status'):
        raise SystemExit('Usage: python -m app.mentor_semantic index|status')
    from .mentor_engine import load_knowledge
    sources = load_knowledge()
    if sys.argv[1] == 'status':
        print(json.dumps({'ready': semantic_ready(sources), 'index_valid': load_verified_index(sources) is not None,
                          'external_query_opt_in': os.getenv('AQUAVERSE_ALLOW_EXTERNAL_QUERY_EMBEDDINGS') == '1',
                          'external_knowledge_opt_in': os.getenv('AQUAVERSE_ALLOW_EXTERNAL_KNOWLEDGE_EMBEDDINGS') == '1'},
                         ensure_ascii=False, indent=2))
    else:
        print(json.dumps(build_index(sources, key=os.getenv('OPENAI_API_KEY', '')), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
