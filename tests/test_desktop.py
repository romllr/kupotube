import threading
from unittest.mock import Mock, patch
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from desktop import DesktopAPI
from app import Download


def test_native_save_atomic_and_cleanup(tmp_path):
    source = tmp_path / 'download.mp4'
    source.write_bytes(b'video')
    destination = tmp_path / 'saved.mp4'
    cleanup = Mock()
    response = FileResponse(source, filename='video.mp4', background=BackgroundTask(cleanup))
    api = DesktopAPI()
    with patch('desktop.prepare_download', return_value=response) as prepare:
        api._run(Download(url='https://youtu.be/example'), destination)
    assert destination.read_bytes() == b'video'
    assert not source.exists()
    assert api.get_progress()['state'] == 'complete'
    assert prepare.call_args.kwargs['directory'] == str(tmp_path)
    cleanup.assert_called_once()


def test_native_cancel_before_download():
    api = DesktopAPI()
    api._window = Mock()
    api._window.create_file_dialog.return_value = None
    with patch('desktop.prepare_download') as prepare:
        assert api.start_download('https://youtu.be/example', 720) == {'cancelled': True}
    prepare.assert_not_called()
    assert not api._active


def test_native_download_failure(tmp_path):
    api = DesktopAPI()
    with patch('desktop.prepare_download', side_effect=RuntimeError('failure')):
        api._run(Download(url='https://youtu.be/example'), tmp_path / 'video.mp4')
    assert api.get_progress()['state'] == 'error'
    assert not api._active


def test_download_returns_while_worker_is_busy(tmp_path):
    api = DesktopAPI()
    api._window = Mock()
    api._window.create_file_dialog.return_value = (str(tmp_path / 'video.webm'),)
    entered, release = threading.Event(), threading.Event()
    def prepare(body, progress, directory):
        progress({'state': 'downloading', 'percent': 42})
        entered.set()
        release.wait(3)
        raise RuntimeError('test finished')
    with patch('desktop.prepare_download', side_effect=prepare):
        try:
            assert api.start_download('https://youtu.be/example', 720, 'webm') == {'started': True}
            assert entered.wait(2)
            assert api.get_progress()['percent'] == 42
            assert 'error' in api.start_download('https://youtu.be/example', 720)
        finally:
            release.set()
    # The bridge must not expose the native window, locks or thread state to JS.
    assert all(key.startswith('_') for key in vars(api))
