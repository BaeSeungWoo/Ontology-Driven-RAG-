"""Add program metadata to a QA bundle, preserving its indexes and page numbers."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import pypdfium2

from backend.app.factories.machines import read_machine_info
from pipeline.ingestion.prepared_documents import document_key
from pipeline.ingestion.machine_resolver import machine_documents

ROOT = Path(__file__).resolve().parents[1]
INDEX_FILES = {'title_index.json': 'pages', 'parts_index2.json': 'parts',
               'io_index_merged.json': 'entries', 'io_index_rows_merged.json': 'entries',
               'explain_dict.json': 'entries'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_new(path, value):
    if path.exists():
        if read(path) != value:
            raise ValueError(f'기존 메타데이터와 다릅니다. 보존했습니다: {path}')
        return
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def prepare(bundle, data_root, machines_root):
    sources = read(bundle / 'source_pdfs.json')
    machines = {f: read_machine_info(machines_root / f'machine_info_{f}.json')
                for f in ('yunam', 'yulkok', 'poongsan')}
    with (bundle / 'MANIFEST.tsv').open(encoding='utf-8-sig', newline='') as stream:
        inventory = list(csv.DictReader(stream, delimiter='\t'))
    results = []
    for index in sorted((bundle / 'index').iterdir()):
        if not index.is_dir():
            continue
        source = sources[index.name]
        links = [(f, code, info['machine_name']) for f, entries in machines.items()
                 for code, info in entries.items()
                 if document_key(source['pdf']) in
                 {document_key(n) for n in machine_documents(info, 'electrical')}]
        if not links:
            results.append({'document': index.name, 'status': 'excluded_unmapped'})
            continue
        factories = {row[0] for row in links}
        if len(factories) != 1:
            raise ValueError(f'공장 간 문서 매핑 확인 필요: {index.name}')
        factory = next(iter(factories))
        pdfs = [p for p in (data_root / factory / 'inputs/originPDF/electrical').glob('*')
                if p.is_file() and document_key(p.name) == document_key(source['pdf'])]
        if len(pdfs) != 1:
            raise ValueError(f'원본 PDF를 하나로 확정할 수 없습니다: {index.name}')
        pdf = pdfs[0]
        # Validate the delivered files before deriving new metadata from them.
        entries = [row for row in inventory if row['doc'] == index.name]
        listed = {row['file'] for row in entries}
        for name in INDEX_FILES:
            if f'index/{index.name}/{name}' not in listed:
                raise ValueError(f'배포 목록에 없는 인덱스: {index.name}/{name}')
        for row in entries:
            path = (bundle / row['file']).resolve()
            if not path.is_relative_to(bundle.resolve()) or digest(path) != row['sha256']:
                raise ValueError(f'배포 파일 해시 불일치: {row["file"]}')
        for name, key in INDEX_FILES.items():
            if not isinstance(read(index / name).get(key), list):
                raise ValueError(f'인덱스 형식 오류: {index.name}/{name}')
        titles = read(index / 'title_index.json')['pages']
        title_pages = [row['page'] for row in titles]
        if len(title_pages) != len(set(title_pages)):
            raise ValueError(f'제목 인덱스의 중복 페이지: {index.name}')
        referenced = set(read(index / 'parts_index2.json').get('page_devices', {}))
        for name in ('io_index_merged.json', 'io_index_rows_merged.json'):
            referenced.update(str(row['page']) for row in read(index / name)['entries'] if row.get('page'))
        pages = list(set(title_pages) | referenced)
        title_by_page = {row['page']: row.get('title', '') for row in titles}
        ocr = {p: [] for p in pages}
        cells = bundle / 'work' / index.name / 'layout/cells.jsonl'
        if cells.exists():
            if cells.relative_to(bundle).as_posix() not in listed:
                raise ValueError(f'배포 목록에 없는 OCR 자료: {cells}')
            with cells.open(encoding='utf-8') as stream:
                for line in stream:
                    row = json.loads(line)
                    page = str(row['page'])
                    if page in ocr:
                        words = row.get('words', [])
                        if not isinstance(words, list) or any(not isinstance(w, str) for w in words):
                            raise ValueError(f'OCR 단어 형식 오류: {cells}')
                        ocr[page].append(' '.join(words))
        sha = digest(pdf)
        with pypdfium2.PdfDocument(str(pdf)) as document:
            count = len(document)
            if (not pages or len(pages) != len(set(pages))
                    or any(not isinstance(p, str) or not p.isdigit() or str(int(p)) != p
                           or not 1 <= int(p) <= count for p in pages)):
                raise ValueError(f'원본 PDF 페이지 범위와 맞지 않습니다: {index.name}')
            evidence = []
            for page in sorted(pages, key=int):
                pdf_page = document[int(page) - 1]
                try:
                    text_page = pdf_page.get_textpage()
                    try:
                        text = text_page.get_text_range()
                    finally:
                        text_page.close()
                finally:
                    pdf_page.close()
                evidence.append({'page': page, 'title': title_by_page.get(page, ''),
                                 'ocr_text': '\n'.join(dict.fromkeys(ocr[page])),
                                 'pdf_text': text, 'status': 'automatic_unverified',
                                 'ocr_source': 'work/layout/cells.jsonl' if ocr[page] else None})
        covered = sorted(pages, key=int)
        mapping = {'factory': factory, 'doc': index.name, 'pdf_filename': pdf.name,
                   'pdf_sha256': sha, 'pages': count,
                   'machines': [{'machine_code': code, 'machine_name': name}
                                for _, code, name in links]}
        write_new(index / 'machine_mapping.json', mapping)
        write_new(index / 'page_evidence.json', {'sha256': sha, 'pages': evidence})
        files = {p.name: digest(p) for p in sorted(index.iterdir())
                 if p.is_file() and p.name != 'manifest.json'}
        manifest = {'schema_version': 2, 'pdf_sha256': sha, 'pdf_page_count': count,
                    'covered_pages': covered,
                    'coverage': 'full' if len(covered) == count else 'partial',
                    'files': files, 'verification_status': 'automatic_unverified',
                    'pdf_binding': 'machine_info filename and original PDF page numbers; '
                                   'the bundle does not supply an original PDF hash',
                    'source_manifest_sha256': digest(bundle / 'MANIFEST.tsv')}
        write_new(index / 'manifest.json', manifest)
        results.append({'document': index.name, 'factory': factory, 'status': 'prepared',
                        'pdf_pages': count, 'indexed_pages': len(covered),
                        'coverage': manifest['coverage'],
                        'pages_without_ocr_or_pdf_text': [r['page'] for r in evidence
                                                       if not r['ocr_text'].strip() and not r['pdf_text'].strip()]})
        print(index.name, len(covered), '/', count, manifest['coverage'], flush=True)
    write_new(bundle / 'metadata_preparation_report.json', results)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, default=ROOT / 'pipeline/data')
    parser.add_argument('--machines-root', type=Path, default=ROOT / 'backend/app/factories')
    args = parser.parse_args()
    prepare(args.bundle, args.data_root, args.machines_root)
