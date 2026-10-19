"""Native Windows window with an embedded WebView2 interface."""
import asyncio
import logging
import subprocess
from pathlib import Path
import os
from fastapi import HTTPException
from settings import cookie_path, get_preferences, set_sound
import updater
from version import VERSION
from window_theme import apply_window_theme
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
        self._destination = None
        self._completed_path = None
        self._update_status = {'state': 'idle'}

    def get_progress(self):
        with self._lock:
            return {**self._state, **({'folder': str(self._destination.parent)} if self._destination else {})}

    def _update(self, state):
        with self._lock:
            self._state = state

    def start_download(self, url, quality, container='mp4', title='video', start_time=None, end_time=None):
        with self._lock:
            if self._active:
                return {'error': 'Já existe um download em andamento.'}
            self._active = True
            self._destination = None
            self._completed_path = None
            self._state = {'state': 'choosing', 'percent': None}
        try:
            body = Download(url=url, quality=quality, container=container, start_time=start_time, end_time=end_time)
            name = yt_dlp.utils.sanitize_filename(title or 'video', restricted=True)[:120]
            target = self._window.create_file_dialog(
                webview.FileDialog.SAVE, save_filename=f'{name}.{container}',
                file_types=(f'{"Áudio" if container == "mp3" else "Vídeo"} {container.upper()} (*.{container})',),
            )
            if not target:
                self._update({'state': 'cancelled', 'percent': None})
                with self._lock:
                    self._active = False
                return {'cancelled': True}
            destination = Path(target[0] if isinstance(target, (tuple, list)) else target)
            if destination.suffix.lower() != '.' + container:
                destination = Path(str(destination) + '.' + container)
            with self._lock:
                self._destination = destination
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
            with self._lock:
                self._completed_path = destination
            self._update({'state': 'complete', 'percent': 100, 'filename': destination.name})
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else 'O download falhou. Confira o link, o espaço livre ou tente outro formato.'
            self._update({'state': 'error', 'percent': None, 'error': detail})
        finally:
            try:
                if response is not None and response.background:
                    asyncio.run(response.background())
            finally:
                with self._lock:
                    self._active = False


    def reveal_download(self):
        with self._lock:
            path = self._completed_path
        if path is None or not path.is_file():
            return {'error': 'O arquivo não está mais na pasta onde foi salvo.'}
        try:
            # Pass the exact path as an argument; never execute it through a shell.
            subprocess.Popen(['explorer.exe', '/select,', str(path)])
            return {'opened': True}
        except OSError:
            return {'error': 'Não foi possível abrir o local do arquivo.'}

    def get_preferences(self):
        return get_preferences()

    def set_sound_enabled(self, enabled):
        if type(enabled) is not bool:
            return {'error': 'Preferência inválida.'}
        try:
            with self._lock:
                set_sound(enabled)
            return {'saved': True}
        except OSError:
            return {'error': 'Não foi possível salvar a preferência.'}

    def import_session(self):
        with self._lock:
            if self._active:
                return {'error': 'Aguarde o download ou a atualização terminar.'}
        files = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                                file_types=('Cookies Netscape (*.txt)',))
        if not files:
            return {'cancelled': True}
        try:
            source = Path(files[0] if isinstance(files, (tuple, list)) else files)
            if source.stat().st_size > 5 * 1024 * 1024:
                raise ValueError('Arquivo muito grande.')
            jar = yt_dlp.cookies.YoutubeDLCookieJar(str(source))
            jar.load(ignore_discard=True, ignore_expires=False)
            supported = ('instagram.com', 'tiktok.com', 'youtube.com')
            selected = [cookie for cookie in jar if any(cookie.domain.lstrip('.') == host or cookie.domain.endswith('.' + host) for host in supported)]
            if not selected:
                raise ValueError('Não contém sessão de uma plataforma compatível.')
            target = cookie_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.tmp')
            try:
                temporary.touch(mode=0o600, exist_ok=True)
                output = yt_dlp.cookies.YoutubeDLCookieJar(str(temporary))
                for cookie in selected:
                    output.set_cookie(cookie)
                output.save(ignore_discard=True, ignore_expires=False)
                os.chmod(temporary, 0o600)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            return {'imported': True}
        except Exception:
            return {'error': 'Não foi possível importar. Escolha um arquivo de cookies no formato Netscape (.txt) com uma sessão válida.'}

    def remove_session(self):
        with self._lock:
            if self._active:
                return {'error': 'Aguarde o download ou a atualização terminar.'}
            cookie_path().unlink(missing_ok=True)
        return {'removed': True}

    def check_update(self):
        try:
            result = updater.check_update()
            result.pop('manifest', None)
            return result
        except Exception:
            return {'error': 'Não foi possível consultar atualizações. Verifique a conexão e se o GitHub Releases está acessível.', 'current': VERSION}

    def get_update_progress(self):
        with self._lock:
            return dict(self._update_status)

    def install_update(self):
        with self._lock:
            if self._active:
                return {'error': 'Aguarde o download terminar antes de atualizar.'}
            self._active = True
            self._update_status = {'state': 'downloading', 'percent': 0}
        threading.Thread(target=self._install_update, daemon=True).start()
        return {'started': True}

    def _install_update(self):
        try:
            result = updater.check_update()
            if not result.get('available'):
                raise RuntimeError('Você já tem a versão mais recente.')
            def progress(percent):
                with self._lock:
                    self._update_status = {'state': 'downloading', 'percent': percent}
            updater.stage_update(result['manifest'], progress)
            with self._lock:
                self._update_status = {'state': 'restarting', 'percent': 100}
            self._window.destroy()
        except Exception:
            with self._lock:
                self._update_status = {'state': 'error', 'error': 'Não foi possível instalar a atualização. A versão atual foi mantida. Tente novamente ou baixe a release pelo GitHub.'}
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
            'Kupotube · Prévia UI', address, js_api=api, width=1080, height=900,
            min_size=(580, 650), background_color='#181926',
        )
        api._window.events.shown += lambda: apply_window_theme(api._window)
        webview.start(gui='edgechromium', debug=False, icon=str(Path(__file__).parent / 'static' / 'kupotube.ico'))
    finally:
        server.should_exit = True
        worker.join(timeout=5)
        listener.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    main()
