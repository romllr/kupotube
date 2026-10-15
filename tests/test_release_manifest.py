import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from updater import validate_manifest


def test_release_script_works_outside_checkout_without_pythonpath(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'release_manifest.py'
    binary = tmp_path / 'Kupotube.exe'
    output = tmp_path / 'update.json'
    content = b'MZsample executable for testing'
    binary.write_bytes(content)
    task_env = dict(os.environ)
    task_env.pop('PYTHONPATH', None)
    subprocess.run([sys.executable, str(script), '--binary', str(binary), '--output', str(output)],
                   cwd=tmp_path, env=task_env, check=True, capture_output=True)
    manifest = validate_manifest(json.loads(output.read_text(encoding='utf-8')))
    assert manifest['size'] == len(content)
    assert manifest['sha256'] == hashlib.sha256(content).hexdigest()
