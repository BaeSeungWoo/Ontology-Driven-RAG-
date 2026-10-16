#!/usr/bin/env python3
"""Standalone, subprocess-isolated electrical QA. No ingestion or index builder."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import traceback
from urllib.parse import urlsplit
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent
INDEX_FILES = {
    'title_index.json': ('pages', list),
    'parts_index2.json': ('parts', list),
    'io_index_merged.json': ('entries', list),
    'io_index_rows_merged.json': ('entries', list),
    'explain_dict.json': ('entries', list),
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_config(path):
    path = Path(path).resolve()
    config = read_json(path)
    for key in ('profile', 'index_dir', 'pdf', 'output_dir'):
        if not config.get(key):
            raise ValueError(f'설정에 {key} 경로가 필요합니다.')
        config[key] = str((path.parent / config[key]).resolve())
    config.setdefault('provider', 'vllm')
    if config['provider'] not in ('vllm', 'ollama'):
        raise ValueError('provider는 vllm 또는 ollama여야 합니다.')
    config['base_url'] = str(config.get('base_url', '')).rstrip('/')
    url = urlsplit(config['base_url'])
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('base_url에는 인증정보 없는 http(s) 서버 주소를 지정하세요.')
    if not url.path.rstrip('/').endswith('/v1'):
        config['base_url'] += '/v1'
    if not isinstance(config.get('model'), str) or not config['model'].strip():
        raise ValueError('model에 서버의 실제 모델 ID가 필요합니다.')
    for key, default, low, high in (
        ('context_tokens', 8192, 4096, 1048576),
        ('max_tokens', 3000, 900, 32768),
        ('max_images', 1, 1, 32),
    ):
        value = config.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f'{key}는 {low}~{high} 정수여야 합니다.')
        config[key] = value
    timeout = float(config.get('timeout_seconds', 1800))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout_seconds는 양수여야 합니다.')
    config['timeout_seconds'] = timeout
    if config['max_tokens'] + 1024 >= config['context_tokens']:
        raise ValueError('context_tokens를 출력 토큰 예산보다 충분히 크게 지정하세요.')
    config.setdefault('api_key_env', 'OPENAI_API_KEY')
    config.setdefault('require_index_verified', False)
    if not isinstance(config['require_index_verified'], bool):
        raise ValueError('require_index_verified는 true 또는 false여야 합니다.')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', config['api_key_env']):
        raise ValueError('api_key_env는 환경변수 이름이어야 합니다.')
    config['_config_path'] = str(path)
    return config


def validate_inputs(config):
    profile = read_json(config['profile'])
    index = Path(config['index_dir'])
    for name, (key, kind) in INDEX_FILES.items():
        path = index / name
        if not path.is_file():
            raise ValueError(f'기존 인덱스 파일이 없습니다: {path}')
        payload = read_json(path)
        if not isinstance(payload.get(key), kind):
            raise ValueError(f'인덱스 형식이 호환되지 않습니다: {name} / {key}')
    titles = read_json(index / 'title_index.json')['pages']
    pdf = Path(config['pdf'])
    if not pdf.is_file():
        raise ValueError(f'원본 전기도면 PDF가 없습니다: {pdf}')
    import pypdfium2
    with pypdfium2.PdfDocument(str(pdf)) as document:
        page_count = len(document)
    page_numbers = [str(row.get('page', '')) for row in titles]
    if not page_numbers or len(set(page_numbers)) != len(page_numbers) or any(
        not p.isdigit() or not 1 <= int(p) <= page_count for p in page_numbers
    ):
        raise ValueError('페이지 인덱스에 중복 또는 PDF 범위 밖 페이지가 있습니다.')
    engine = profile['engine']
    if not all(key in engine for key in ('func_pages', 'rev_pages', 'flags')):
        raise ValueError('프로필 engine 설정이 호환되지 않습니다.')
    # Profiles are configuration, not arbitrary engine argument injection.
    flags = engine['flags']
    protected = ('--pdf', '--titles', '--parts', '--io', '--io-rows', '--explain',
                 '--cache', '--render-dir', '--tmp', '--qa', '--out', '--docid')
    if not isinstance(flags, list) or any(not isinstance(x, str) for x in flags) or any(
        flag.split('=')[0] in protected for flag in flags
    ):
        raise ValueError('프로필 flags에 입력·출력 경로를 덮어쓰는 옵션이 있습니다.')
    verified = None
    full_pages = None
    index_verified = index / 'verified_evidence.json'
    if config.get('require_index_verified') and not index_verified.is_file():
        raise ValueError('병합 인덱스의 verified_evidence.json이 없습니다. 최신 데이터 ZIP을 같은 폴더에 풀어주세요.')
    if index_verified.is_file() or profile.get('verified_evidence'):
        verified_path = index_verified if index_verified.is_file() else Path(config['profile']).parent.parent / profile['verified_evidence']
        verified = read_json(verified_path)
        if sha256(pdf) != verified['sha256']:
            raise ValueError('검증한 전기도면 판본과 PDF가 다릅니다.')
        from electrical.grounding import load_page_evidence
        full_pages = load_page_evidence(index, verified['sha256'])
        if verified.get('required_page_count') and len(full_pages or {}) != verified['required_page_count']:
            raise ValueError('병합 인덱스에 필요한 전체 페이지 근거가 없습니다.')
        if full_pages is not None and set(full_pages) != set(page_numbers):
            raise ValueError('전체 페이지 근거와 제목 인덱스의 페이지가 다릅니다.')
    return profile, verified, full_pages, page_count


def check(config, server=False):
    dependencies = {name: importlib.metadata.version(name) for name in ('numpy', 'Pillow', 'pypdfium2')}
    profile, verified, pages, page_count = validate_inputs(config)
    report = {'ok': True, 'python': sys.version.split()[0], 'dependencies': dependencies,
              'machine': profile['machine'], 'pdf_pages': page_count,
              'indexed_pages': len(read_json(Path(config['index_dir']) / 'title_index.json')['pages']),
              'verified_pdf': verified is not None, 'full_page_evidence': pages is not None,
              'index_local_verified': (Path(config['index_dir']) / 'verified_evidence.json').is_file(),
              'index_scope': (verified or {}).get('index_scope') or profile.get('full_scope' if pages is not None else 'scope', ''),
              'server_checked': False}
    if server:
        headers = {'Authorization': 'Bearer ' + (os.getenv(config['api_key_env']) or 'x')}
        req = urllib.request.Request(config['base_url'] + '/models', headers=headers)
        with urllib.request.urlopen(req, timeout=20) as response:
            models = json.load(response)
        ids = [item['id'] for item in models.get('data', [])]
        if config['model'] not in ids:
            raise ValueError(f'모델 ID가 서버에 없습니다. 사용 가능: {ids}')
        # Listing a model alone does not prove image support: send a real image.
        import base64
        import io
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB', (64, 64), 'white').save(buffer, format='PNG')
        data = {'model': config['model'], 'max_tokens': 32, 'temperature': 0,
                'messages': [{'role': 'user', 'content': [
                    {'type': 'text', 'text': 'Describe this image briefly.'},
                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()}}
                ]}]}
        if config['provider'] == 'vllm':
            data['chat_template_kwargs'] = {'enable_thinking': False}
        else:
            data['reasoning_effort'] = 'none'
        req = urllib.request.Request(config['base_url'] + '/chat/completions',
            data=json.dumps(data).encode(), headers={**headers, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as response:
            answer = json.load(response)['choices'][0]['message'].get('content')
        if not answer:
            raise ValueError('이미지 입력 확인에서 빈 답변을 받았습니다.')
        report.update(server_checked=True, model=config['model'], vision_checked=True)
    return report


def engine_command(config, profile, run):
    from electrical.options import BASE, CATALOG, V52
    idx = Path(config['index_dir'])
    eng = profile['engine']
    return [str(ROOT / 'electrical' / 'engine' / 'qa_engine.py'), *BASE,
        '--titles', str(idx / 'title_index.json'), '--parts', str(idx / 'parts_index2.json'),
        '--io', str(idx / 'io_index_merged.json'), '--io-rows', str(idx / 'io_index_rows_merged.json'),
        '--explain', str(idx / 'explain_dict.json'), '--pdf', config['pdf'],
        '--cache', str(run / 'cache'), '--render-dir', str(run / 'cache' / 'pages'), '--tmp', str(run / 'tmp'),
        '--qa', str(run / 'question.json'), '--docid', Path(config['profile']).stem,
        '--out', str(run / 'engine_result.json'), '--scale', str(eng.get('scale', 4.0)),
        '--func-pages', str(eng['func_pages']), '--rev-pages', str(eng['rev_pages']),
        *eng['flags'], *CATALOG, *V52]


def adapt_result(row, pdf, records=None):
    pages = list(dict.fromkeys(map(str, row.get('func_pages', []) + row.get('rev_pages', []))))
    if not pages:
        raise ValueError('답변을 연결할 근거 페이지가 없습니다.')
    chunks = []
    for n, page in enumerate(pages, 1):
        source = [r['text'] for r in (records or []) if str(r['page']) == page]
        chunks.append({'index': n, 'document': '\n'.join(source or row.get('evidence', [])),
            'metadata': {'source_kind': 'electrical', 'source_doc_name': Path(pdf).stem,
                         'pdf': str(pdf), 'page': int(page), 'page_range': page,
                         'pdf_uri': Path(pdf).resolve().as_uri() + '#page=' + page,
                         'picked_parts': row.get('picked_parts', []),
                         'picked_signals': row.get('picked_signals', [])}})
    by_page = {chunk['metadata']['page_range']: chunk['index'] for chunk in chunks}
    answer = row['answer']
    for citation in re.finditer(r'\(p\d+(?:, p\d+)*\)', answer):
        if set(re.findall(r'p(\d+)', citation.group(0))) - by_page.keys():
            raise ValueError('답변의 인용 페이지가 검색 근거에 없습니다.')
    # Human-reviewed answer already carries claim-level (pN) citations.
    answer = re.sub(r'\(p(\d+)((?:, p\d+)*)\)', lambda match: '(' + ', '.join(
        f'p{p} [chunk:{by_page[p]}]' for p in re.findall(r'p(\d+)', match.group(0)) if p in by_page
    ) + ')', answer)
    answer += '\n\n검토한 도면 페이지: ' + ' '.join(f'p{p} [chunk:{by_page[p]}]' for p in pages)
    return {'answer': answer, 'chunks': chunks, 'images': [], 'tables': [],
            'picked_parts': row.get('picked_parts', []), 'picked_signals': row.get('picked_signals', []),
            'grounding_reviewed': bool(row.get('grounding_reviewed'))}


def worker(request):
    config, question, run = request['config'], request['question'], Path(request['run_dir'])
    with (run / 'engine.log').open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            from runtime_support import report_progress
            report_progress("180쪽 도면 자료와 PDF 판본을 확인하는 중")
            profile, verified, full_pages, page_count = validate_inputs(config)
            report_progress("180쪽 도면 자료와 PDF 판본을 확인하는 중",
                            f"문서: {Path(config['pdf']).name}\n페이지 수: {page_count}쪽\n원본 대조 기록: {'있음' if verified else '없음'}")
            from runtime_support import answer_context
            from electrical.grounding import review, page_review_evidence, source_records, reread_evidence
            context = answer_context(request)
            if verified:
                context += '\n' + verified['generation_rules']
            scope = (verified or {}).get('index_scope') or profile.get('full_scope' if full_pages is not None else 'scope', '')
            context += '\n인덱스 범위: ' + scope
            os.environ['GRAPHRAG_ANSWER_CONTEXT'] = context
            write_json(run / 'question.json', {'qa_pairs': [{'id': 'query', 'question': question}]})
            previous = sys.argv
            try:
                sys.argv = engine_command(config, profile, run)
                report_progress("질문과 관련된 부품·신호·도면을 찾는 중")
                runpy.run_path(sys.argv[0], run_name='__main__')
            finally:
                sys.argv = previous
            row = read_json(run / 'engine_result.json')['rows'][0]
            write_json(run / 'trace.json', row)
            records = None
            if verified:
                report_progress("답변의 부품·신호와 도면 근거를 검토하는 중")
                evidence = page_review_evidence(
                    verified, full_pages, row.get('func_pages', []) + row.get('rev_pages', []), question,
                    index=config['index_dir'], picked_parts=row.get('picked_parts', []),
                    picked_signals=row.get('picked_signals', []))
                review_records = source_records(evidence)
                report_progress("답변의 부품·신호와 도면 근거를 검토하는 중",
                                f"검토 후보 페이지: {', '.join('p' + p for p in sorted({r['page'] for r in review_records}, key=int))}\n"
                                f"원본 대조 기록 {sum(not r['id'].startswith(('ocr:', 'vision:', 'index:')) for r in review_records)}개, "
                                f"자동 판독 기록 {sum(r['id'].startswith(('ocr:', 'vision:', 'index:')) for r in review_records)}개를 준비했습니다.")
                answer, pages, reviewed = review({'model': config['model'], 'base_url': config['base_url']}, question, row['answer'], evidence,
                    reread=lambda client, current: reread_evidence(client, question, current, config['pdf'], run))
                row['v52_answer_before_review'] = row['answer']
                row['answer'] = answer
                row['rev_pages'] = list(dict.fromkeys(row.get('rev_pages', []) + pages))
                row['grounding_reviewed'] = reviewed
                records = source_records(evidence)
            if not row.get('answer', '').strip():
                raise ValueError('전기도면 답변이 비어 있습니다.')
            write_json(run / 'trace.json', row)
            result = adapt_result(row, config['pdf'], records)
            result.update(question=question, machine=profile['machine'], scope=scope,
                model=config['model'], run_dir=str(run), trace_file=str(run / 'trace.json'),
                log_file=str(run / 'engine.log'))
            write_json(run / 'result.json', result)
            return {'ok': True, 'result': result}
        except Exception as error:
            traceback.print_exc()
            return {'ok': False, 'error': f'{type(error).__name__}: {error}', 'log_file': str(run / 'engine.log')}


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # This worker runs the engine in-process (runpy), so there is no nested
        # engine process. Use its owned process handle; taskkill can need WMI
        # privileges even when the child belongs to this client.
        process.kill()
    else:
        import signal
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


def ask(config_path, question, *, persona_type='operator', user_prompt='', history=None):
    """One synchronous question. Returns JSON-compatible result, raises on failure.

    Every call uses an isolated worker environment and a unique output directory.
    Concurrent calls from this installation are rejected to avoid duplicate costly work.
    """
    config = load_config(config_path)
    if not isinstance(question, str) or not question.strip() or len(question) > 6000:
        raise ValueError('질문은 1~6000자로 입력하세요.')
    validate_inputs(config)  # Fail before creating a job or contacting the server.
    output = Path(config['output_dir'])
    output.mkdir(parents=True, exist_ok=True)
    lock = output / '.qa.lock'
    try:
        lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise RuntimeError(f'이미 QA 실행 중이거나 이전 실행 잠금이 남았습니다: {lock}') from None
    process = None
    try:
        with os.fdopen(lock_fd, 'w') as stream:
            stream.write(str(os.getpid()))
        run = output / uuid.uuid4().hex
        run.mkdir()
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(('GRAPHRAG_', 'VLLM_')) and key not in ('LLM_NAME', 'PYTHONPATH', 'OPENAI_API_KEY')}
        environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
            VLLM_API_BASE=config['base_url'], VLLM_API_MODEL=config['model'], LLM_NAME=config['model'],
            GRAPHRAG_PROVIDER=config['provider'], GRAPHRAG_CONTEXT_TOKENS=str(config['context_tokens']),
            GRAPHRAG_MAX_TOKENS=str(config['max_tokens']), GRAPHRAG_MAX_IMAGES=str(config['max_images']),
            OPENAI_API_KEY=os.getenv(config['api_key_env'], ''))
        process = subprocess.Popen([sys.executable, str(ROOT / 'qa_portable.py'), '--worker'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', env=environment, cwd=ROOT,
            start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        request = {'config': config, 'question': question, 'run_dir': str(run),
                   'persona_type': persona_type, 'user_prompt': user_prompt, 'history': history or []}
        try:
            stdout, stderr = process.communicate(json.dumps(request, ensure_ascii=False), timeout=config['timeout_seconds'])
        except subprocess.TimeoutExpired:
            stop_process(process)
            raise TimeoutError(f'QA 전체 제한시간을 초과했습니다. 자동 재시도하지 않습니다. 로그: {run / "engine.log"}') from None
        if process.returncode:
            raise RuntimeError(f'QA worker가 종료되었습니다: {stderr[:1200]}')
        payload = json.loads(stdout)
        if not payload.get('ok'):
            raise RuntimeError(payload.get('error', 'QA 실행 실패') + '\n로그: ' + payload.get('log_file', str(run)))
        return payload['result']
    finally:
        try:
            if process is not None:
                stop_process(process)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
        finally:
            lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='기존 전기도면 인덱스와 PDF를 사용하는 QA 전용 실행기')
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    parser.add_argument('--check', action='store_true', help='파일·판본·의존성 확인 (서버 요청 없음)')
    parser.add_argument('--check-server', action='store_true', help='설정 검사 및 모델·이미지 입력 실제 확인')
    parser.add_argument('--question', help='한국어 질문')
    parser.add_argument('--json', action='store_true', help='답변과 근거를 JSON으로 출력')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(json.load(sys.stdin)), ensure_ascii=False))
        return 0
    try:
        if args.check or args.check_server:
            print(json.dumps(check(load_config(args.config), server=args.check_server), ensure_ascii=False, indent=2))
            return 0
        if not args.question:
            parser.error('--question 또는 --check를 지정하세요.')
        print('전기도면 QA 실행 중입니다. 완료까지 수 분 걸릴 수 있습니다. 취소: Ctrl+C', file=sys.stderr)
        result = ask(args.config, args.question)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result['answer'])
        if not args.json:
            print('\n결과: ' + str(Path(result['run_dir']) / 'result.json'), file=sys.stderr)
        return 0
    except KeyboardInterrupt:
        print('QA를 취소했습니다. 자동 재시도하지 않습니다.', file=sys.stderr)
        return 130
    except Exception as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
