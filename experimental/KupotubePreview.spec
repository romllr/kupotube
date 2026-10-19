from pathlib import Path
from PyInstaller.utils.hooks import collect_all
webview_datas, webview_binaries, webview_hidden = collect_all("webview")
curl_datas, curl_binaries, curl_hidden = collect_all("curl_cffi")
root = Path(SPECPATH).parent
a = Analysis(
    [str(root / 'experimental' / 'ui_preview.py')], pathex=[str(root)],
    binaries=webview_binaries + curl_binaries + [(str(root / 'tools' / 'ffmpeg.exe'), 'tools'),
              (str(root / 'tools' / 'node.exe'), 'tools')],
    datas=webview_datas + curl_datas + [(str(root / 'static'), 'static')],
    hiddenimports=webview_hidden + curl_hidden + ['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.h11_impl',
                   'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on'],
    hookspath=[], runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name='Kupotube-UI-Preview',
          debug=False, strip=False, upx=False, console=False, icon=str(root / 'static' / 'kupotube.ico'))
