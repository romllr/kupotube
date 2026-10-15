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
    assert 'height<=?720' in opts['format']
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


@patch('app.validate_url', side_effect=lambda value: value)
@patch('app.yt_dlp.YoutubeDL')
def test_unknown_resolution_and_single_reel_entry(downloader, validate):
    downloader.return_value.__enter__.return_value.extract_info.return_value = {
        '_type': 'playlist', 'entries': [{'title':'Reel', 'formats':[{'vcodec':'h264','url':'https://example.test/video'}]}]}
    response = client.post('/api/info', json={'url':'https://www.instagram.com/reels/example/'})
    assert response.status_code == 200
    assert response.json()['qualities'] == []
    assert response.json()['unknown_quality'] is True


@patch('app.validate_url', side_effect=lambda value: value)
@patch('app.yt_dlp.YoutubeDL')
def test_login_error_preserves_actionable_detail(downloader, validate):
    import yt_dlp
    downloader.return_value.__enter__.return_value.extract_info.side_effect = yt_dlp.utils.DownloadError('Login required')
    response = client.post('/api/info', json={'url':'https://www.instagram.com/reel/example/'})
    assert response.status_code == 422
    assert 'Importar sessão' in response.json()['detail']


@patch('app.validate_url', side_effect=lambda value: value)
@patch('app.yt_dlp.YoutubeDL')
def test_mp3_audio_conversion(downloader, validate):
    def extract(url, download):
        opts = downloader.call_args.args[0]
        Path(opts['outtmpl'].replace('%(ext)s','mp3')).write_bytes(b'mp3')
        return {'title':'Audio'}
    downloader.return_value.__enter__.return_value.extract_info.side_effect = extract
    response = client.post('/api/download',json={'url':'https://youtu.be/example','container':'mp3'})
    assert response.status_code == 200
    opts = downloader.call_args.args[0]
    assert opts['format'] == 'bestaudio/best'
    assert opts['postprocessors'][0]['preferredcodec'] == 'mp3'
    assert 'merge_output_format' not in opts
    assert '.mp3' in response.headers['content-disposition']


def test_tiktok_prefers_unwatermarked_formats():
    # Evaluate the actual yt-dlp selector against marked playback/download streams.
    import yt_dlp
    from app import Download, prepare_download
    captured = []
    class FakeDownloader:
        def __init__(self, opts): captured.append(opts)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            Path(captured[-1]['outtmpl'].replace('%(ext)s','mp4')).write_bytes(b'video')
            return {'title':'TikTok'}
    import asyncio
    with patch('app.validate_url',side_effect=lambda url:url), patch('app.yt_dlp.YoutubeDL',FakeDownloader):
        response=prepare_download(Download(url='https://www.tiktok.com/@user/video/123',quality=720))
        asyncio.run(response.background())
    formats = [
        {'format_id':'clean','url':'https://example.test/clean','ext':'mp4','height':480,'vcodec':'h264','acodec':'aac','format_note':'Direct video'},
        {'format_id':'marked','url':'https://example.test/marked','ext':'mp4','height':720,'vcodec':'h264','acodec':'aac','format_note':'watermarked'},
    ]
    with yt_dlp.YoutubeDL({'quiet':True}) as downloader:
        selector=downloader.build_format_selector(captured[0]['format'])
        chosen=list(selector({'formats':formats,'has_merged_format':True,'incomplete_formats':False}))
        assert chosen[0]['format_id'] == 'clean'
        # Still works if only the watermarked variant is available.
        fallback=list(selector({'formats':formats[1:],'has_merged_format':True,'incomplete_formats':False}))
        assert fallback[0]['format_id'] == 'marked'
