"""Native Windows window with an embedded WebView2 interface."""
import asyncio
import logging
from pathlib import Path
import os
import socket
import threading
import time

import uvicorn
import webview
from app import app, prepare_download, Download
import yt_dlp


class DesktopAPI:
    def __init__(self):
        # Never expose the Window object through pywebview's recursive JS bridge.
        self._window = None
        self._lock = threading.Lock()
        self._state = {'state': 'idle', 'percent': None}
        self._active = False

    def get_progress(self):
        with self._lock:
            return dict(self._state)

    def _update(self, state):
        with self._lock:
            self._state = state

    def start_download(self, url, quality, container='mp4', title='video'):
        with self._lock:
            if self._active:
                return {'error': 'Já existe um download em andamento.'}
            self._active = True
            self._state = {'state': 'choosing', 'percent': None}
        try:
            body = Download(url=url, quality=quality, container=container)
            name = yt_dlp.utils.sanitize_filename(title or 'video', restricted=True)[:120]
            target = self._window.create_file_dialog(
                webview.FileDialog.SAVE, save_filename=f'{name}.{container}',
                file_types=(f'Vídeo {container.upper()} (*.{container})',),
            )
            if not target:
                self._update({'state': 'cancelled', 'percent': None})
                with self._lock:
                    self._active = False
                return {'cancelled': True}
            destination = Path(target[0] if isinstance(target, (tuple, list)) else target)
            if destination.suffix.lower() != '.' + container:
                destination = Path(str(destination) + '.' + container)
            self._update({'state': 'preparing', 'percent': None})
            threading.Thread(target=self._run, args=(body, destination), daemon=True).start()
            return {'started': True}
        except Exception:
            self._update({'state': 'error', 'percent': None, 'error': 'Não foi possível escolher o destino do vídeo.'})
            with self._lock:
                self._active = False
            return {'error': 'Não foi possível escolher o destino do vídeo.'}

    def _run(self, body, destination):
        response = None
        try:
            # Same filesystem: rename instead of copying gigabytes after download.
            response = prepare_download(body, progress=self._update, directory=str(destination.parent))
            self._update({'state': 'saving', 'percent': None})
            os.replace(response.path, destination)
            self._update({'state': 'complete', 'percent': 100, 'filename': destination.name})
        except Exception:
            self._update({'state': 'error', 'percent': None,
                          'error': 'O download falhou. Confira o link, o espaço livre ou tente outro formato.'})
        finally:
            if response is not None and response.background:
                asyncio.run(response.background())
            with self._lock:
                self._active = False


def main():
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    address = f'http://127.0.0.1:{listener.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
    worker = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 20
        while not server.started:
            if not worker.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Não foi possível iniciar o Kupotube.')
            time.sleep(.05)
        api = DesktopAPI()
        api._window = webview.create_window(
            'Kupotube', address, js_api=api, width=1080, height=900,
            min_size=(580, 650), background_color='#24273a',
        )
        webview.start(gui='edgechromium', debug=False, icon=str(Path(__file__).parent / 'static' / 'kupotube.ico'))
    finally:
        server.should_exit = True
        worker.join(timeout=5)
        listener.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    main()
