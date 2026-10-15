"""Generate updater metadata independently of the runner's Python import path."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]


def generate_manifest(binary, output):
    release = runpy.run_path(str(ROOT / 'version.py'))
    version, repository = release['VERSION'], release['REPOSITORY']
    binary, output = Path(binary), Path(output)
    with binary.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('O arquivo não é um executável Windows.')
        stream.seek(0)
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = {
        'version': version,
        'url': f'https://github.com/{repository}/releases/download/v{version}/Kupotube.exe',
        'sha256': checksum,
        'size': binary.stat().st_size,
    }
    output.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, default=ROOT / 'dist' / 'Kupotube.exe')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'update.json')
    args = parser.parse_args()
    generate_manifest(args.binary, args.output)
