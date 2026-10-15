import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest
import updater


def manifest(binary=b'MZexample', version='99.0.0'):
    return {'version': version,
            'url': f'https://github.com/romllr/kupotube/releases/download/v{version}/Kupotube.exe',
            'size': len(binary), 'sha256': hashlib.sha256(binary).hexdigest()}


def test_download_verified_before_install(tmp_path):
    target = tmp_path / 'update.exe'
    values = []
    with patch('updater.urlopen', return_value=io.BytesIO(b'MZexample')):
        updater.download_update(manifest(), target, values.append)
    assert target.read_bytes() == b'MZexample'
    assert values[-1] == 100


def test_checksum_failure_discards_binary(tmp_path):
    target = tmp_path / 'update.exe'
    with patch('updater.urlopen', return_value=io.BytesIO(b'MZchanged')):
        with pytest.raises(ValueError):
            updater.download_update(manifest(), target, lambda _: None)
    assert not target.exists()


@pytest.mark.parametrize('field,value', [('url','https://evil.test/Kupotube.exe'), ('size',True), ('size',-1), ('sha256','bad'), ('version','1.2;evil')])
def test_reject_untrusted_manifests(field, value):
    data = manifest()
    data[field] = value
    with pytest.raises(ValueError):
        updater.validate_manifest(data)


def test_no_downgrades():
    with patch('updater.fetch_json', return_value={'tag_name': 'v0.1.0'}):
        assert updater.check_update()['available'] is False


def test_new_release_and_matching_manifest():
    with patch('updater.fetch_json', side_effect=[{'tag_name':'v99.0.0'}, manifest()]):
        assert updater.check_update()['version'] == '99.0.0'
    with patch('updater.fetch_json', side_effect=[{'tag_name':'v99.0.0'}, manifest(version='98.0.0')]):
        with pytest.raises(ValueError):
            updater.check_update()


@pytest.mark.skipif(os.name != 'nt', reason='Installer runs only on Windows')
def test_windows_installer_replace_and_rollback(tmp_path):
    # Exercise the same PowerShell helper used by the packaged updater, with a
    # standalone harmless Windows executable instead of touching the running app.
    original = Path(os.environ['WINDIR']) / 'System32' / 'whoami.exe'
    for broken in (False, True):
        root = tmp_path / ('rollback' if broken else 'success')
        root.mkdir()
        stage = root / 'stage'
        stage.mkdir()
        target = root / 'Kupotube.exe'
        source = stage / 'new.exe'
        shutil.copyfile(original, target)
        if broken:
            source.write_bytes(b'MZinvalid executable')
        else:
            shutil.copyfile(original, source)
        command = updater.helper_command(2147483647, target, source, stage, hashlib.sha256(source.read_bytes()).hexdigest(), no_ui=True)
        run = subprocess.run(command, capture_output=True, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        error_log = (stage / 'error.txt').read_text(errors='replace') if (stage / 'error.txt').exists() else ''
        assert run.returncode == (1 if broken else 0), error_log + run.stderr.decode(errors='replace')
        assert target.read_bytes() == original.read_bytes()
        if not broken:
            assert not stage.exists()
        assert not list(root.glob('.kupotube-*.tmp'))


def test_handoff_waits_for_own_pid_and_confirms_helper(tmp_path):
    from types import SimpleNamespace
    appfile = tmp_path / 'Kupotube.exe'
    appfile.write_bytes(b'MZold')
    captured = []
    folder_capture = []
    fake_process = SimpleNamespace(poll=lambda: None)
    def launch(command, **kwargs):
        captured.append(command)
        folder = next((tmp_path / 'profile' / 'updates').glob('kupotube-update-*'))
        folder_capture.append(folder)
        (folder / 'ready').write_text('ready')
        return fake_process
    with patch('updater.os', SimpleNamespace(name='nt',getpid=lambda:1234)), \
         patch('updater.sys.frozen',True,create=True), patch('updater.sys.executable',str(appfile)), \
         patch('updater.data_dir', return_value=tmp_path / 'profile'), \
         patch('updater.download_update'), patch('updater.subprocess.Popen',side_effect=launch), \
         patch('updater.subprocess.CREATE_NO_WINDOW',0,create=True), patch('updater.subprocess.DETACHED_PROCESS',0,create=True):
        assert updater.stage_update(manifest(),lambda _:None) is fake_process
    command = captured[0]
    import base64
    script = base64.b64decode(command[-1]).decode('utf-16-le')
    assert '-AppId 1234' in script
    assert '-ParentId' not in script
    assert not (folder_capture[0] / 'install.ps1').exists()
    assert appfile.read_bytes() == b'MZold'
    assert not list(tmp_path.glob('kupotube-update-*'))


def test_helper_failure_does_not_handoff(tmp_path):
    from types import SimpleNamespace
    with patch('updater.os', SimpleNamespace(name='nt',getpid=lambda:1234)), \
         patch('updater.sys.frozen',True,create=True), patch('updater.data_dir',return_value=tmp_path), \
         patch('updater.download_update'), patch('updater.subprocess.Popen',return_value=SimpleNamespace(poll=lambda:1,returncode=1)), \
         patch('updater.subprocess.CREATE_NO_WINDOW',0,create=True), patch('updater.subprocess.DETACHED_PROCESS',0,create=True):
        with pytest.raises(RuntimeError,match='não iniciou'):
            updater.stage_update(manifest(),lambda _:None)
    assert not list((tmp_path / 'updates').glob('kupotube-update-*'))
