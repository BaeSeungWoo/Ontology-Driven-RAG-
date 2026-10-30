"""Import external electrical indexes without running bundled code or OCR."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

from pipeline.ingestion.prepared_documents import document_key

DATA_ROOT = Path(__file__).resolve().parent / "data"


def save(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"기존 파일과 내용이 다릅니다. 원본을 보존했습니다: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def prepare_manual_index(root, index, document_names):
    """Create missing QA settings for a directly copied, matching document."""
    mapping_path = index / 'machine_mapping.json'
    if not mapping_path.is_file():
        return
    mapping = json.loads(mapping_path.read_text(encoding='utf-8-sig'))
    pdf_name = mapping['pdf_filename']
    if Path(pdf_name).name != pdf_name or '\\' in pdf_name or ':' in pdf_name:
        raise ValueError('PDF 이름에는 경로를 넣을 수 없습니다.')
    if document_key(pdf_name) not in document_names:
        return
    profile_path = index / 'qa_profile.json'
    config_path = index / 'qa_config.json'
    if config_path.is_file():
        existing = json.loads(config_path.read_text(encoding='utf-8-sig'))
        # Custom profiles and existing QA settings are never replaced.
        if (index / existing['profile']).is_file():
            return
        if existing['profile'] != 'qa_profile.json':
            raise ValueError('기존 QA 설정이 참조하는 프로필이 없습니다.')
    manifest = json.loads((index / 'manifest.json').read_text(encoding='utf-8-sig'))
    pdf = root / 'inputs/electricals' / pdf_name
    with pdf.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != manifest['pdf_sha256']:
            raise ValueError('원본 PDF와 인덱스 지문이 다릅니다.')
    for filename, expected in manifest['files'].items():
        target = (index / filename).resolve()
        if not target.is_relative_to(index.resolve()):
            raise ValueError('인덱스 파일은 문서 폴더 안에 있어야 합니다.')
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError(f'인덱스 지문 불일치: {filename}')
    profile = {'machine': Path(pdf_name).stem, 'pdf': pdf_name,
               'engine': {'func_pages': 2, 'rev_pages': 2, 'flags': []}}
    config = {'profile': 'qa_profile.json', 'index_dir': '.',
              'pdf': '../../../inputs/electricals/' + pdf_name,
              'output_dir': '../../results', 'require_index_verified': False,
              'require_index_manifest': True, 'provider': 'vllm',
              'base_url': 'http://127.0.0.1:8100/v1', 'model': 'Qwen3-VL',
              'max_tokens': 3000, 'context_tokens': 8192, 'max_images': 1,
              'timeout_seconds': 1800}
    for path, value in [(profile_path, profile), (config_path, config)]:
        if not path.exists():
            # Exclusive creation also preserves files created by concurrent requests.
            try:
                with path.open('x', encoding='utf-8') as stream:
                    json.dump(value, stream, ensure_ascii=False, indent=2)
            except FileExistsError:
                pass


def import_zip(factory, archive):
    from backend.app.factories.machines import load_machine_info

    machines = load_machine_info(factory_id=factory)
    root = DATA_ROOT / factory
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        for name in names:
            parts = PurePosixPath(name)
            if parts.is_absolute() or '..' in parts.parts or '\\' in name or ':' in name:
                raise ValueError(f"허용하지 않는 ZIP 경로: {name}")
        manifests = [n for n in names if n.startswith('index/') and n.endswith('/manifest.json')]
        if not manifests:
            raise ValueError("index/{문서}/manifest.json이 없습니다.")
        pending = {}
        reports = []
        for name in manifests:
            prefix = str(PurePosixPath(name).parent)
            manifest = json.loads(z.read(name))
            mapping = json.loads(z.read(prefix + '/machine_mapping.json'))
            pdf_name = mapping['pdf_filename']
            if Path(pdf_name).name != pdf_name:
                raise ValueError("PDF 이름에는 경로를 넣을 수 없습니다.")
            linked = [code for code, info in machines.items()
                      if document_key(pdf_name) in {document_key(n) for n in info.get('document', {}).get('electrical', [])}]
            if not linked:
                raise ValueError(f"{factory} machine_info의 electrical에 없는 문서: {pdf_name}")
            pdf_path = root / 'inputs/electricals' / pdf_name
            pdf = pdf_path.read_bytes() if pdf_path.exists() else z.read('originals/' + pdf_name)
            if hashlib.sha256(pdf).hexdigest() != manifest['pdf_sha256']:
                raise ValueError("원본 PDF와 인덱스 지문이 다릅니다.")
            for filename, expected in manifest['files'].items():
                data = z.read(prefix + '/' + filename)
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError(f"인덱스 지문 불일치: {filename}")
            profiles = [json.loads(z.read(n)) for n in names
                        if n.startswith('profile_') and n.endswith('.json')]
            profile = next((p for p in profiles if document_key(p.get('pdf', '')) == document_key(pdf_name)), None)
            if profile is None:
                raise ValueError(f"PDF에 대응하는 profile_*.json이 없습니다: {pdf_name}")
            # This is a QA profile, not the extraction script/config from the ZIP.
            qa_profile = {'machine': profile['machine'], 'style': profile['style'], 'pdf': pdf_name,
                          'engine': {'func_pages': 2, 'rev_pages': 2, 'flags': []}}
            index = root / 'electrical' / prefix
            config = {'profile': 'qa_profile.json', 'index_dir': '.',
                      'pdf': '../../../inputs/electricals/' + pdf_name,
                      'output_dir': '../../results', 'require_index_verified': False, 'require_index_manifest': True,
                      'provider': 'vllm', 'base_url': 'http://127.0.0.1:8100/v1',
                      'model': 'Qwen3-VL', 'max_tokens': 3000, 'context_tokens': 8192,
                      'max_images': 1, 'timeout_seconds': 1800}
            pending[pdf_path] = pdf
            for n in names:
                if n.startswith(prefix + '/') and not n.endswith('/'):
                    pending[root / 'electrical' / n] = z.read(n)
            for filename, value in [('qa_profile.json', qa_profile), ('qa_config.json', config)]:
                pending[index / filename] = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
            reports.append({'document': pdf_name, 'machines': linked, 'index': str(index)})
        # Reject conflicts before writing any imported file.
        for path, data in pending.items():
            if path.exists() and path.read_bytes() != data:
                raise ValueError(f"기존 파일과 내용이 다릅니다: {path}")
        for path, data in pending.items():
            save(path, data)
    return reports


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--factory', required=True, choices=['yunam', 'yulkok', 'poongsan'])
    parser.add_argument('--zip', required=True)
    args = parser.parse_args()
    print(json.dumps(import_zip(args.factory, args.zip), ensure_ascii=False, indent=2))
