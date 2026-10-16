"""Verify shipped code/data only; settings and generated results are excluded."""
import hashlib
import json
from pathlib import Path


def verify(root):
    root = Path(root).resolve()
    count = 0
    for name in ('manifest.json', 'data_manifest.json'):
        manifest = root / name
        if not manifest.exists():
            continue
        for relative, expected in json.loads(manifest.read_text(encoding='utf-8'))['files'].items():
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Invalid manifest path: ' + relative)
            with path.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != expected:
                raise ValueError('SHA-256 mismatch: ' + relative)
            count += 1
    if not count:
        raise ValueError('No distribution manifests found')
    return count


if __name__ == '__main__':
    print('Verified files:', verify(Path(__file__).resolve().parent))
