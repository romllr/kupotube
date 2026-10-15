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


def test_reject_unknown_container():
    response = client.post('/api/download', json={'url': 'https://youtu.be/example', 'container': 'exe'})
    assert response.status_code == 422


@patch('app.validate_url', side_effect=lambda value: value)
@patch('app.yt_dlp.YoutubeDL')
def test_progress_and_webm_selection(downloader, validate):
    from app import prepare_download, Download
    import asyncio
    events = []
    def extract(url, download):
        opts = downloader.call_args.args[0]
        hook = opts['progress_hooks'][0]
        hook({'status': 'downloading', 'downloaded_bytes': 25, 'total_bytes': 100,
              'speed': 10, 'eta': 8, 'info_dict': {'vcodec': 'vp9'}})
        hook({'status': 'downloading', 'downloaded_bytes': 1, 'info_dict': {'vcodec': 'none'}})
        opts['postprocessor_hooks'][0]({'status': 'started'})
        Path(opts['outtmpl'].replace('%(ext)s', 'webm')).write_bytes(b'video')
        return {'title': 'Sample'}
    downloader.return_value.__enter__.return_value.extract_info.side_effect = extract
    response = prepare_download(Download(url='https://youtu.be/example', container='webm'), progress=events.append)
    try:
        assert events[0]['percent'] == 25
        assert events[1]['percent'] is None
        assert events[1]['track'] == 'Áudio'
        assert events[2]['state'] == 'processing'
        opts = downloader.call_args.args[0]
        assert '[ext=webm]' in opts['format']
        assert opts['merge_output_format'] == 'webm'
        assert opts['postprocessors'][0]['preferedformat'] == 'webm'
    finally:
        asyncio.run(response.background())
