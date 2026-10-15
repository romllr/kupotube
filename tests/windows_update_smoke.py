"""Run against the CI-built onefile fixture, with a persistent parent process."""
from pathlib import Path
import os
import json
import subprocess
import sys
import tempfile
import time
import traceback


def wait_for_exit(pid):
    # Do not tear down the test directory while the helper still owns its cwd.
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, int(pid))
    if not handle:
        assert ctypes.get_last_error() in (87, 1168), 'Cannot inspect test process'
        return
    try:
        assert kernel.WaitForSingleObject(handle, 30000) == 0, 'Test process did not finish'
    finally:
        kernel.CloseHandle(handle)


def main():
    with tempfile.TemporaryDirectory(prefix='kupo-smoke-') as temporary:
        root = Path(temporary)
        import shutil
        target = root / 'KupoFixture.exe'
        shutil.copyfile(sys.argv[1], target)
        task_env = dict(os.environ, KUPOTUBE_UPDATE_SMOKE_ROOT=str(root), LOCALAPPDATA=str(root / 'profile'))
        parent = subprocess.Popen([str(target)], env=task_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output, _ = parent.communicate(timeout=90)
        log = root / 'profile' / 'Kupotube' / 'updater.log'
        log_text = log.read_text(encoding='utf-8', errors='replace')[-5000:] if log.exists() else '(no installer log)'
        assert parent.returncode == 0, 'Old app could not hand off to installer: ' + output.decode(errors='replace')[-5000:] + log_text
        deadline = time.monotonic() + 90
        while not (root / 'restarted').exists() and time.monotonic() < deadline:
            failures = list(root.rglob('error.txt'))
            if failures:
                raise AssertionError(failures[0].read_text(errors='replace'))
            time.sleep(.2)
        assert (root / 'restarted').exists(), 'New executable did not restart while its launcher remained alive'
        restarted = json.loads((root / 'restarted').read_text(encoding='utf-8'))
        for pid in {int((root / 'helper.pid').read_text()), restarted['pid'], restarted['parent_pid']} - {os.getpid()}:
            wait_for_exit(pid)
        deadline = time.monotonic() + 40
        while (list((root / 'profile').rglob('kupotube-update-*')) or list(root.glob('*.previous'))) and time.monotonic() < deadline:
            time.sleep(.2)
        assert not list((root / 'profile').rglob('kupotube-update-*')), 'Staging was not cleaned'
        assert not list(root.glob('.kupotube-*.tmp')), 'Incoming copy was not cleaned'
        assert not list(root.glob('*.previous')), 'Backup was not cleaned'
        print('Onefile update verified: handoff, replacement, restart and cleanup with persistent parent')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        detail = traceback.format_exc().replace('\x00', '').encode('ascii', 'backslashreplace').decode('ascii').replace('%','%25').replace('\r','%0D').replace('\n','%0A')
        print(f'::error title=Packaged updater failed::{detail}', flush=True)
        raise
