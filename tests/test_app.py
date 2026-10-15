from unittest.mock import patch
from pathlib import Path
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_home():
    response = client.get('/')
    assert response.status_code == 200
    assert 'Kupotube' in response.text


def test_reject_external_and_local_urls():
    for url in ['https://example.com/video', 'http://youtube.com/watch?v=x', 'https://youtube.com.evil.test/x', 'https://127.0.0.1/']:
        assert client.post('/api/info', json={'url': url}).status_code == 400


@patch('app.validate_url', side_effect=lambda value: value)
@patch('app.yt_dlp.YoutubeDL')
def test_qualities(downloader, validate):
    downloader.return_value.__enter__.return_value.extract_info.return_value = {
        'title': 'Sample', 'formats': [{'height': 720, 'vcodec': 'h264'}, {'height': 2160, 'vcodec': 'vp9'}, {'height': 720, 'vcodec': 'h264'}]}
    response = client.post('/api/info', json={'url': 'https://youtu.be/example'})
    assert response.status_code == 200
    assert response.json()['qualities'] == [2160, 720]


@patch('app.validate_url', side_effect=lambda value: value)
@patch('app.yt_dlp.YoutubeDL')
def test_download_and_cleanup(downloader, validate):
    def extract(url, download):
        opts = downloader.call_args.args[0]
        Path(opts['outtmpl'].replace('%(ext)s', 'mp4')).write_bytes(b'sample-video')
        return {'title': 'Sample'}
    downloader.return_value.__enter__.return_value.extract_info.side_effect = extract
    response = client.post('/api/download', json={'url': 'https://youtu.be/example', 'quality': 720})
    assert response.status_code == 200
    assert response.content == b'sample-video'
    opts = downloader.call_args.args[0]
    assert 'height<=720' in opts['format']
    assert not Path(opts['outtmpl']).parent.exists()
