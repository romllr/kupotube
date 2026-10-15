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
        script = stage / 'install.ps1'
        script.write_text(updater.INSTALL_SCRIPT, encoding='utf-8-sig')
        run = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                              '-File',str(script),'-ParentId','2147483647','-Target',str(target),
                              '-Source',str(source),'-Folder',str(stage)], capture_output=True, timeout=45)
        assert run.returncode == (1 if broken else 0), run.stderr.decode(errors='replace')
        assert target.read_bytes() == original.read_bytes()
