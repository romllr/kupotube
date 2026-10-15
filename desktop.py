"""Native Windows window with an embedded WebView2 interface."""
import asyncio
import logging
from pathlib import Path
import shutil
import socket
import threading
import time

import uvicorn
import webview
from app import app, download, Download


class DesktopAPI:
    window = None

    def save_video(self, url, quality):
        response = None
        try:
            response = download(Download(url=url, quality=quality))
            target = self.window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=response.filename,
                file_types=('Vídeo (*' + Path(response.path).suffix + ')',),
            )
            if not target:
                return {'cancelled': True}
            destination = target[0] if isinstance(target, (tuple, list)) else target
            shutil.copy2(response.path, destination)
            return {'saved': True}
        except Exception:
            return {'error': 'Não foi possível baixar ou salvar o vídeo. Confira o link e tente outra qualidade.'}
        finally:
            if response is not None and response.background:
                asyncio.run(response.background())


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
        api.window = webview.create_window(
            'Kupotube', address, js_api=api, width=1080, height=900,
            min_size=(580, 650), background_color='#24273a',
        )
        webview.start(gui='edgechromium', debug=False)
    finally:
        server.should_exit = True
        worker.join(timeout=5)
        listener.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    main()
