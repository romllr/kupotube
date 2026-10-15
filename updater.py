"""GitHub Releases updater. Only installs a verified asset from our repository."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

from version import REPOSITORY, VERSION

MAX_SIZE = 1024 ** 3


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Versão inválida.')
    return tuple(map(int, value.split('.')))


def fetch_json(url):
    request = Request(url, headers={'User-Agent': 'Kupotube/' + VERSION, 'Accept': 'application/json'})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read(1024 * 1024))


def validate_manifest(manifest):
    version_tuple(manifest.get('version'))
    expected = f'https://github.com/{REPOSITORY}/releases/download/v{manifest["version"]}/Kupotube.exe'
    if manifest.get('url') != expected:
        raise ValueError('Origem da atualização inválida.')
    if not re.fullmatch(r'[0-9a-f]{64}', str(manifest.get('sha256', ''))):
        raise ValueError('Verificação da atualização ausente.')
    size = manifest.get('size')
    if type(size) is not int or not 0 < size <= MAX_SIZE:
        raise ValueError('Tamanho de atualização inválido.')
    return manifest


def check_update():
    release = fetch_json(f'https://api.github.com/repos/{REPOSITORY}/releases/latest')
    tag = release.get('tag_name', '')
    if not tag.startswith('v') or version_tuple(tag[1:]) <= version_tuple(VERSION):
        return {'available': False, 'current': VERSION}
    manifest_url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/update.json'
    manifest = validate_manifest(fetch_json(manifest_url))
    if manifest['version'] != tag[1:]:
        raise ValueError('Versão do pacote não corresponde à release.')
    return {'available': True, 'current': VERSION, 'version': manifest['version'], 'manifest': manifest}


def download_update(manifest, target, progress):
    validate_manifest(manifest)
    digest = hashlib.sha256()
    count = 0
    request = Request(manifest['url'], headers={'User-Agent': 'Kupotube/' + VERSION})
    try:
        with urlopen(request, timeout=30) as response, open(target, 'wb') as output:
            while chunk := response.read(1024 * 512):
                count += len(chunk)
                if count > manifest['size']:
                    raise ValueError('Tamanho inesperado na atualização.')
                digest.update(chunk)
                output.write(chunk)
                progress(round(count / manifest['size'] * 100))
        if count != manifest['size'] or digest.hexdigest() != manifest['sha256']:
            raise ValueError('A verificação da atualização falhou. O arquivo foi descartado.')
        with open(target, 'rb') as executable:
            if executable.read(2) != b'MZ':
                raise ValueError('O arquivo recebido não é um executável Windows.')
    except Exception:
        Path(target).unlink(missing_ok=True)
        raise


# Arguments are passed separately, never interpolated into PowerShell source.
# Wait for the parent, preserve a backup, and retry transient antivirus/file locks.
INSTALL_SCRIPT = r'''
param([int]$ParentId, [string]$Target, [string]$Source, [string]$Folder)
$ErrorActionPreference = 'Stop'
Wait-Process -Id $ParentId -ErrorAction SilentlyContinue
$Backup = "$Target.previous"
$Installed = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        if (Test-Path -LiteralPath $Target) {
            Move-Item -LiteralPath $Target -Destination $Backup -Force
        }
        Move-Item -LiteralPath $Source -Destination $Target -Force
        $Installed = $true
        break
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $Installed) {
    if (Test-Path -LiteralPath $Backup) {
        Move-Item -LiteralPath $Backup -Destination $Target -Force
    }
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show('Não foi possível instalar a atualização. A versão anterior foi preservada.', 'Kupotube')
    exit 1
}
# A restarted PyInstaller onefile must extract its own files, not reuse the parent bundle.
$env:PYINSTALLER_RESET_ENVIRONMENT = '1'
try {
    Start-Process -FilePath $Target -WorkingDirectory (Split-Path -Parent $Target)
} catch {
    Move-Item -LiteralPath $Backup -Destination $Target -Force
    Start-Process -FilePath $Target
    exit 1
}
Remove-Item -LiteralPath $Backup -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Folder -Recurse -Force -ErrorAction SilentlyContinue
'''


def stage_update(manifest, progress):
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        raise RuntimeError('Atualizações automáticas estão disponíveis no executável Windows.')
    executable = Path(sys.executable).resolve()
    folder = Path(tempfile.mkdtemp(prefix='kupotube-update-', dir=executable.parent))
    try:
        target = folder / 'Kupotube.exe'
        download_update(manifest, target, progress)
        script = folder / 'install.ps1'
        script.write_text(INSTALL_SCRIPT, encoding='utf-8-sig')
        # Account for the PyInstaller bootloader, which also holds the executable open.
        parent_id = os.getppid()
        process = subprocess.Popen([
            'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(script), '-ParentId', str(parent_id), '-Target', str(executable),
            '-Source', str(target), '-Folder', str(folder),
        ], creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
        return process
    except Exception:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise
