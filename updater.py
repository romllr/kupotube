"""GitHub Releases updater. Only installs a verified asset from our repository."""
import hashlib
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from settings import data_dir
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


# The helper confirms readiness BEFORE the app closes. Wait for this exact app
# process, never its parent (which can be Explorer or a persistent launcher).
INSTALL_SCRIPT = r'''
param([int]$AppId, [string]$Target, [string]$Source, [string]$Folder, [string]$Checksum, [switch]$NoUI)
$ErrorActionPreference = 'Stop'
$Backup = "$Target.previous"
$Incoming = Join-Path (Split-Path -Parent $Target) ('.kupotube-' + [guid]::NewGuid().ToString('N') + '.tmp')
$MovedOriginal = $false
try {
    # Staging may be on another disk: finish and verify the copy before touching the old app.
    Copy-Item -LiteralPath $Source -Destination $Incoming
    if ((Get-FileHash -LiteralPath $Incoming -Algorithm SHA256).Hash.ToLower() -ne $Checksum) {
        throw 'A cópia da atualização falhou na verificação.'
    }
    Set-Content -LiteralPath (Join-Path $Folder 'ready') -Value 'ready'
    $App = Get-Process -Id $AppId -ErrorAction SilentlyContinue
    if ($App) { Wait-Process -Id $AppId -Timeout 120 -ErrorAction Stop }
    $Installed = $false
    for ($i = 0; $i -lt 120; $i++) {
        try {
            if (-not $MovedOriginal -and (Test-Path -LiteralPath $Target)) {
                Move-Item -LiteralPath $Target -Destination $Backup -Force
                $MovedOriginal = $true
            }
            Move-Item -LiteralPath $Incoming -Destination $Target -Force
            $Installed = $true
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $Installed) { throw 'O Windows não liberou o executável para atualização.' }
    $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
    Start-Process -FilePath $Target -WorkingDirectory (Split-Path -Parent $Target)
    Remove-Item -LiteralPath $Backup -Force -ErrorAction SilentlyContinue
    # Retry cleanup in case antivirus still holds a temporary file.
    for ($i = 0; $i -lt 10; $i++) {
        Remove-Item -LiteralPath $Folder -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $Folder)) { break }
        Start-Sleep -Milliseconds 500
    }
} catch {
    $Failure = $_.Exception.Message
    [Console]::Error.WriteLine($Failure)
    if ($MovedOriginal -and (Test-Path -LiteralPath $Backup)) {
        Move-Item -LiteralPath $Backup -Destination $Target -Force
        $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
        Start-Process -FilePath $Target -WorkingDirectory (Split-Path -Parent $Target)
    }
    Remove-Item -LiteralPath $Incoming -Force -ErrorAction SilentlyContinue
    Set-Content -LiteralPath (Join-Path $Folder 'error.txt') -Value $Failure
    if (-not $NoUI) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(('A atualização não foi instalada. A versão anterior foi preservada.' + [Environment]::NewLine + $Failure), 'Kupotube') | Out-Null
    }
    exit 1
}
'''


def helper_command(app_id, executable, source, folder, checksum, no_ui=False):
    # Single-quoted PowerShell literals escape apostrophes by doubling them.
    # Encoding avoids command-line quoting ambiguity and a locked .ps1 in staging.
    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"
    invocation = (f"& {{ {INSTALL_SCRIPT} }} -AppId {int(app_id)} "
                  f"-Target {literal(executable)} -Source {literal(source)} "
                  f"-Folder {literal(folder)} -Checksum {literal(checksum)}")
    if no_ui:
        invocation += ' -NoUI'
    encoded = base64.b64encode(invocation.encode('utf-16-le')).decode('ascii')
    return ['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded]


def stage_update(manifest, progress, no_ui=False):
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        raise RuntimeError('Atualizações automáticas estão disponíveis no executável Windows.')
    executable = Path(sys.executable).resolve()
    updates = data_dir() / 'updates'
    updates.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='kupotube-update-', dir=updates))
    try:
        target = folder / 'Kupotube.exe'
        download_update(manifest, target, progress)
        command = helper_command(os.getpid(), executable, target, folder, manifest['sha256'], no_ui)
        process = subprocess.Popen(command, cwd=str(updates), creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
        deadline = time.monotonic() + 60
        while not (folder / 'ready').exists():
            if process.poll() is not None:
                raise RuntimeError('O instalador não iniciou. O app continuará aberto.')
            if time.monotonic() >= deadline:
                process.terminate()
                process.wait(timeout=5)
                raise RuntimeError('O instalador não confirmou que está pronto. O app continuará aberto.')
            time.sleep(.1)
        if process.poll() is not None:
            raise RuntimeError('O instalador encerrou antes de receber a atualização.')
        return process
    except Exception:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise
