"""Local-only PDF import CLI for AquaMentor Phase 3B.

Two-step import: draft extraction -> manual review -> approval. Never exposes
an unauthenticated file upload endpoint or pretends user PDFs are vetted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlsplit

from pypdf import PdfReader

DEFAULT_DIR = Path(__file__).resolve().parents[1] / 'knowledge' / 'imported_pdfs'
MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 80
MAX_CHARS = 220_000


def validate_source_url(value: str) -> str:
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not parts.netloc or parts.username or parts.password
            or any(ch.isspace() for ch in value)):
        raise ValueError('Source URL must be an HTTPS link to the original publication.')
    return value


def sanitize_text(text: str) -> str:
    cleaned = unicodedata.normalize('NFKC', text)
    cleaned = re.sub(r'[\u0000-\u0008\u000b\u000c\u000e-\u001f]', ' ', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()


def split_chunks(text: str, max_chars: int = 760, overlap_words: int = 22) -> list[str]:
    words = text.split()
    chunks = []
    pos = 0
    while pos < len(words):
        end = pos
        n = 0
        while end < len(words) and (n + len(words[end]) + 1 <= max_chars or end == pos):
            n += len(words[end]) + 1
            end += 1
        chunk = ' '.join(words[pos:end])
        if len(chunk) >= 80:
            chunks.append(chunk)
        if end == len(words):
            break
        pos = max(pos + 1, end - overlap_words)
    return chunks


def import_pdf(pdf_path: Path, *, title: str, authors: str, year: int, url: str,
               context: str, destination: Path = DEFAULT_DIR) -> dict:
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise ValueError(f'Cannot find PDF: {pdf_path}')
    if pdf_path.suffix.lower() != '.pdf' or pdf_path.stat().st_size > MAX_BYTES:
        raise ValueError('Please use a PDF file no larger than 15 MiB.')
    if pdf_path.read_bytes()[:5] != b'%PDF-':
        raise ValueError('File does not have a PDF header.')
    if not (len(title.strip()) >= 8 and len(authors.strip()) >= 2 and len(context.strip()) >= 12):
        raise ValueError('Title, authors and study context are required.')
    if not 1900 <= year <= 2100:
        raise ValueError('Publication year is invalid.')
    url = validate_source_url(url)
    raw_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    doc_id = f'PDF-{raw_sha256[:12].upper()}'
    path = destination / f'{doc_id}.json'
    if path.exists():
        raise ValueError(f'This PDF was already imported: {doc_id}')
    try:
        reader = PdfReader(str(pdf_path), strict=False)
        if reader.is_encrypted:
            raise ValueError('Encrypted PDFs are not supported.')
        n_pages = len(reader.pages)
        if n_pages < 1 or n_pages > MAX_PAGES:
            raise ValueError(f'PDF must have 1–{MAX_PAGES} pages.')
        passages = []
        chars = 0
        for index, page in enumerate(reader.pages, start=1):
            text = sanitize_text(page.extract_text() or '')
            chars += len(text)
            if chars > MAX_CHARS:
                raise ValueError('PDF contains too much extractable text for this MVP.')
            for chunk_no, chunk in enumerate(split_chunks(text), start=1):
                passages.append({'id': f'{doc_id}-P{index:03}-C{chunk_no:03}',
                                 'page': index, 'topic': '', 'text': chunk})
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f'Cannot read this PDF: {exc}') from exc
    if chars < 150 or not passages:
        raise ValueError('This PDF has too little selectable text. Scanned images need manual OCR and review before import.')
    payload = {
        'id': doc_id, 'species_id': 'monopterus_albus', 'source_type': 'user_pdf',
        'review_status': 'draft', 'sha256': raw_sha256, 'title': title.strip(),
        'authors': authors.strip(), 'year': year, 'url': url, 'context': context.strip(),
        'pages': n_pages, 'extractable_characters': chars, 'passages': passages,
    }
    destination.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return payload


def read_import(doc_id: str, destination: Path = DEFAULT_DIR) -> dict:
    if not re.fullmatch(r'PDF-[A-F0-9]{12}', doc_id):
        raise ValueError('Invalid PDF document ID.')
    path = destination / f'{doc_id}.json'
    if not path.is_file():
        raise ValueError('Document not found.')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('id') != doc_id or data.get('source_type') != 'user_pdf':
        raise ValueError('Document metadata is inconsistent.')
    return data


def approve_import(doc_id: str, destination: Path = DEFAULT_DIR) -> dict:
    payload = read_import(doc_id, destination)
    payload['review_status'] = 'reviewed'
    # Atomic replacement avoids a truncated JSON document on interruption.
    path = destination / f'{doc_id}.json'
    tmp = path.with_suffix('.tmp')
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description='AquaMentor local PDF knowledge importer (no server upload).')
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('import', help='Extract a local PDF into a draft, not yet searchable.')
    add.add_argument('pdf', type=Path)
    for flag in ('title', 'authors', 'url', 'context'):
        add.add_argument('--' + flag, required=True)
    add.add_argument('--year', type=int, required=True)
    inspect = sub.add_parser('review', help='Preview imported text before approving.')
    inspect.add_argument('doc_id')
    approve = sub.add_parser('approve', help='Activate document for retrieval after manual review.')
    approve.add_argument('doc_id')
    approve.add_argument('--confirm-reviewed', action='store_true', required=True,
                         help='Affirm you checked title, scope, publication URL, sample pages and extracted text.')
    sub.add_parser('list', help='List imported PDFs and current review status.')
    args = parser.parse_args()
    try:
        if args.command == 'import':
            record = import_pdf(args.pdf, title=args.title, authors=args.authors, year=args.year,
                                url=args.url, context=args.context)
            print(f'IMPORTED DRAFT {record["id"]}; {record["pages"]} pages; '
                  f'{len(record["passages"])} chunks. Not yet searchable.')
            print(f'Next: python -m app.mentor_pdf review {record["id"]}')
        elif args.command == 'review':
            record = read_import(args.doc_id)
            print(f'{record["title"]} | {record["year"]} | {record["url"]}')
            print(f'SCOPE: {record["context"]} | STATUS: {record["review_status"]}')
            for passage in record['passages'][:5]:
                print(f'\nPAGE {passage["page"]}: {passage["text"][:400]}')
            print('\nRead the actual PDF yourself; a text preview is not scientific verification.')
        elif args.command == 'approve':
            record = approve_import(args.doc_id)
            print(f'APPROVED {record["id"]} for local retrieval. Restart backend to clear cached sources.')
        elif args.command == 'list':
            for path in sorted(DEFAULT_DIR.glob('PDF-*.json')) if DEFAULT_DIR.exists() else []:
                data = json.loads(path.read_text(encoding='utf-8'))
                print(f'{data["id"]} | {data["review_status"]} | {data["title"]}')
    except ValueError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
