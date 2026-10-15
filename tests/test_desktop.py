from pathlib import Path
from unittest.mock import Mock, patch
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from desktop import DesktopAPI


def test_native_save_and_cleanup(tmp_path):
    source = tmp_path / 'download.mp4'
    source.write_bytes(b'video')
    destination = tmp_path / 'saved.mp4'
    cleanup = Mock()
    response = FileResponse(source, filename='video.mp4', background=BackgroundTask(cleanup))
    api = DesktopAPI()
    api.window = Mock()
    api.window.create_file_dialog.return_value = (str(destination),)
    with patch('desktop.download', return_value=response):
        assert api.save_video('https://youtu.be/example', 1080) == {'saved': True}
    assert destination.read_bytes() == b'video'
    cleanup.assert_called_once()


def test_native_cancel_cleans_up(tmp_path):
    source = tmp_path / 'video.mp4'
    cleanup = Mock()
    api = DesktopAPI()
    api.window = Mock()
    api.window.create_file_dialog.return_value = None
    with patch('desktop.download', return_value=FileResponse(source, filename='video.mp4', background=BackgroundTask(cleanup))):
        assert api.save_video('https://youtu.be/example', 720) == {'cancelled': True}
    cleanup.assert_called_once()


def test_native_download_failure():
    with patch('desktop.download', side_effect=RuntimeError('failure')):
        assert 'error' in DesktopAPI().save_video('https://youtu.be/example', 720)
