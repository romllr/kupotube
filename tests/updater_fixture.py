"""Compiled separately in CI to test onefile handoff, replacement and restart."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import updater

root = Path(os.environ['KUPOTUBE_UPDATE_SMOKE_ROOT'])
if os.environ.get('KUPOTUBE_UPDATE_SMOKE_RESTARTED') == '1':
    (root / 'restarted').write_text(json.dumps({'pid':os.getpid(), 'parent_pid':os.getppid()}), encoding='utf-8')
else:
    executable = Path(sys.executable)
    with executable.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = {'version': '99.0.0', 'url': 'https://github.com/romllr/kupotube/releases/download/v99.0.0/Kupotube.exe',
                'sha256': digest, 'size': executable.stat().st_size}
    # Offline test: use the running onefile executable as the verified new payload.
    updater.download_update = lambda manifest, target, progress: shutil.copyfile(executable, target)
    os.environ['KUPOTUBE_UPDATE_SMOKE_RESTARTED'] = '1'
    helper = updater.stage_update(manifest, lambda _: None, no_ui=True)
    (root / 'helper.pid').write_text(str(helper.pid), encoding='utf-8')
