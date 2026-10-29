from unittest.mock import patch
from pathlib import Path
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_home():
    response = client.get('/')
    assert response.status_code == 200
    assert 'Kupotube' in response.text


@patch('app.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))])
def test_accept_public_sites_without_platform_allowlist(resolve):
    from app import validate_url
    for url in ['https://www.reddit.com/r/videos/comments/abc/title/', 'https://v.redd.it/example',
                'https://youtu.be/example', 'https://vimeo.com/123', 'https://www.twitch.tv/videos/123',
                'https://example.com/video.mp4', 'http://example.com/video', 'https://example.com:8443/video']:
        assert validate_url(url) == url


def test_reject_unsafe_and_invalid_urls():
    for url in ['file:///etc/passwd', 'ftp://example.com/video', 'https://user:pass@example.com/',
                'https://127.0.0.1/', 'http://[::1]/', 'https://localhost/', 'https://server.local/',
                'https://192.168.1.2/', 'http://169.254.169.254/', 'https:///video',
                'https://example.com:99999/', 'https://example.com:0/', 'https://exa mple.com/']:
        assert client.post('/api/info', json={'url': url}).status_code == 400


@patch('app.socket.getaddrinfo')
def test_reject_private_dns_answers_and_unresolved_hosts(resolve):
    import socket
    from app import validate_url
    from fastapi import HTTPException
    import pytest
    for addresses in [[], [(2,1,6,'',('10.0.0.1',443))],
                      [(2,1,6,'',('93.184.216.34',443)), (10,1,6,'',('::1',443,0,0))]]:
        resolve.return_value = addresses
        with pytest.raises(HTTPException): validate_url('https://public-looking.example/video')
    resolve.side_effect = socket.gaierror()
    with patch.dict('os.environ', {'HTTPS_PROXY':'https://proxy.example'}):
        with pytest.raises(HTTPException): validate_url('https://unresolved.example/video')


@patch('app.socket.getaddrinfo', return_value=[(2,1,6,'',('93.184.216.34',443))])
@patch('app.yt_dlp.YoutubeDL')
def test_reddit_info_and_download_use_normal_pipeline(downloader, resolve):
    url = 'https://www.reddit.com/r/videos/comments/abc/title/'
    downloader.return_value.__enter__.return_value.extract_info.return_value = {
        'title':'Reddit video', 'formats':[{'height':720,'vcodec':'h264'}]}
    response = client.post('/api/info', json={'url':url})
    assert response.status_code == 200
    assert response.json()['qualities'] == [720]
    downloader.return_value.__enter__.return_value.extract_info.assert_called_with(url, download=False)
    def extract(link, download):
        assert link == url and download is True
        Path(downloader.call_args.args[0]['outtmpl'].replace('%(ext)s','mp4')).write_bytes(b'reddit video')
        return {'title':'Reddit video'}
    downloader.return_value.__enter__.return_value.extract_info.side_effect = extract
    response = client.post('/api/download', json={'url':url, 'quality':720})
    assert response.status_code == 200 and response.content == b'reddit video'


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


def test_invalid_clip_ranges():
    for values in [{'start_time': 1}, {'end_time': 2}, {'start_time': -1, 'end_time': 2},
                   {'start_time': 2, 'end_time': 2}, {'start_time': 5, 'end_time': 2},
                   {'start_time': 'NaN', 'end_time': 2}, {'start_time': 0, 'end_time': 'Infinity'}]:
        assert client.post('/api/download', json={'url':'https://youtu.be/example', **values}).status_code == 422


@patch('app.validate_url', side_effect=lambda value: value)
@patch('app.yt_dlp.YoutubeDL')
def test_clip_checks_duration_and_uses_local_cut(downloader, validate):
    from fastapi import HTTPException
    import pytest
    def extract(url, download):
        opts = downloader.call_args.args[0]
        assert 'download_ranges' not in opts
        check = opts['match_filter']
        assert check({'duration':100}) is None
        for info in [{'duration': 10}, {'is_live': True}]:
            with pytest.raises(HTTPException):
                check(info)
        assert 'force_keyframes_at_cuts' not in opts
        Path(opts['outtmpl'].replace('%(ext)s', 'mp4')).write_bytes(b'clip')
        return {'title':'Clip'}
    downloader.return_value.__enter__.return_value.extract_info.side_effect = extract
    with patch('app.cut_clip', side_effect=lambda source, target, *args: target.write_bytes(b'clip')):
        response = client.post('/api/download', json={'url':'https://youtu.be/example', 'start_time':7, 'end_time':19})
    assert response.status_code == 200
    assert response.content == b'clip'


def test_real_ffmpeg_clip(tmp_path):
    """Exercise yt-dlp ranges and actual FFmpeg output against a local video."""
    import functools
    import http.server
    import json
    import shutil
    import subprocess
    import threading
    import pytest
    from app import Download, prepare_download
    import asyncio
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Requires local FFmpeg and ffprobe')
    source = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24',
                    '-f','lavfi','-i','sine=frequency=440','-t','6','-c:v','libx264','-c:a','aac','-movflags','+faststart',str(source)],check=True)
    for filename, args in [
        ('video.mp4',['-an','-c:v','copy','-movflags','+faststart']),
        ('audio.m4a',['-vn','-c:a','copy','-movflags','+faststart']),
        ('video.webm',['-an','-c:v','libvpx-vp9']),
        ('audio.webm',['-vn','-c:a','libopus'])]:
        subprocess.run(['ffmpeg','-v','error','-i',str(source),*args,str(tmp_path / filename)],check=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0), handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        for extension in ['mp4', 'mkv', 'mp3']:
            with patch('app.validate_url',side_effect=lambda value:value):
                response = prepare_download(Download(url=f'http://127.0.0.1:{server.server_port}/source.mp4',
                                                     container=extension,start_time=1,end_time=3))
            try:
                probe = subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(response.path)],check=True,capture_output=True,text=True)
                data = json.loads(probe.stdout)
                assert abs(float(data['format']['duration']) - 2) < .2
                assert any(stream['codec_type'] == 'audio' for stream in data['streams'])
                assert any(stream['codec_type'] == 'video' for stream in data['streams']) == (extension != 'mp3')
            finally:
                asyncio.run(response.background())
        from media import cut_clip
        from fastapi import HTTPException
        with pytest.raises(HTTPException, match='não salvará áudio como vídeo'):
            cut_clip(tmp_path / 'audio.m4a', tmp_path / 'invalid.mp4', 1, 3, 'mp4')
        # Exercise the real yt-dlp merge path, not just a combined MP4 source.
        from yt_dlp.extractor.generic import GenericIE
        root = f'http://127.0.0.1:{server.server_port}'
        formats = [
            {'format_id':'v','url':root+'/video.mp4','ext':'mp4','vcodec':'h264','acodec':'none','height':90},
            {'format_id':'a','url':root+'/audio.m4a','ext':'m4a','vcodec':'none','acodec':'aac'},
            {'format_id':'vw','url':root+'/video.webm','ext':'webm','vcodec':'vp9','acodec':'none','height':90},
            {'format_id':'aw','url':root+'/audio.webm','ext':'webm','vcodec':'none','acodec':'opus'}]
        for extension in ['mp4','mkv','webm','mp3']:
            with patch('app.validate_url',side_effect=lambda value:value), patch.object(GenericIE,'_real_extract',return_value={'id':'separate','title':'Separate streams','duration':6,'formats':formats}):
                response = prepare_download(Download(url=root+'/watch',container=extension,start_time=1,end_time=3))
            try:
                data = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(response.path)]))
                assert abs(float(data['format']['duration']) - 2) < .2
                assert any(stream['codec_type'] == 'audio' for stream in data['streams'])
                videos = [stream for stream in data['streams'] if stream['codec_type'] == 'video']
                assert bool(videos) == (extension != 'mp3')
                if videos: assert videos[0]['codec_name'] == ('vp9' if extension == 'webm' else 'h264')
            finally:
                asyncio.run(response.background())
    finally:
        server.shutdown()
        server.server_close()


def test_error_identifies_youtube_and_preserves_cause_without_media_urls():
    from app import extraction_message
    import yt_dlp
    detail = extraction_message(yt_dlp.utils.DownloadError('Unexpected failure: https://media.example/video?token=secret'), 'https://youtu.be/example')
    assert 'YouTube' in detail and 'Unexpected failure' in detail
    assert 'secret' not in detail and 'media.example' not in detail
    detail = extraction_message(yt_dlp.utils.DownloadError('ffmpeg exited with code 1'), 'https://youtube.com/watch?v=example')
    assert 'FFmpeg' in detail and 'importar' not in detail
