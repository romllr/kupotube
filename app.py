import ipaddress
import os
import socket
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from typing import Literal
from settings import cookie_path

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

ROOT = Path(__file__).parent
app = FastAPI(title="Kupotube")
HOSTS = {"youtube.com", "youtu.be", "tiktok.com", "pinterest.com", "pin.it", "instagram.com"}


class Request(BaseModel):
    url: str = Field(max_length=2048)


class Download(Request):
    quality: int = Field(default=1080, ge=144, le=4320)
    container: Literal['mp4', 'mkv', 'webm', 'mp3'] = 'mp4'


def validate_url(url):
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise HTTPException(400, 'Use um link HTTPS válido.')
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in (None, 443):
        raise HTTPException(400, "Use um link HTTPS válido.")
    if not any(host == h or host.endswith("." + h) for h in HOSTS):
        raise HTTPException(400, "Cole um link do YouTube, TikTok, Pinterest ou Instagram.")
    try:
        addresses = socket.getaddrinfo(host, 443)
        if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise HTTPException(400, "Endereço não permitido.")
    except socket.gaierror:
        # In proxy-backed environments DNS may be resolved only by the HTTPS proxy.
        # Only fixed, already-allowlisted platform hostnames can reach this branch.
        if not (os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')):
            raise HTTPException(400, "Não foi possível encontrar esse site.")
    return url


def options():
    opts = {"noplaylist": True, "quiet": True, "no_warnings": True, "noprogress": True,
            "socket_timeout": 20, "retries": 2, "cachedir": False,
            "concurrent_fragment_downloads": 4,
            "compat_opts": ["no-certifi"] if os.environ.get("SSL_CERT_FILE") else []}
    if getattr(sys, "frozen", False):
        opts["ffmpeg_location"] = str(ROOT / "tools")
        opts["js_runtimes"] = {"node": {"path": str(ROOT / "tools" / "node.exe")}}
    if cookie_path().is_file():
        # A separate jar per operation prevents concurrent yt-dlp calls rewriting credentials.
        jar = yt_dlp.cookies.YoutubeDLCookieJar(str(cookie_path()))
        try:
            jar.load(ignore_discard=True, ignore_expires=False)
        except Exception:
            raise HTTPException(422, 'A sessão salva não pôde ser lida. Remova ou importe novamente a sessão.')
        opts['cookiefile'] = None
        opts['_session_cookiejar'] = jar
    return opts


def make_downloader(opts):
    jar = opts.pop('_session_cookiejar', None)
    downloader = yt_dlp.YoutubeDL(opts)
    if jar is not None:
        # cached_property is writable. No cookiefile means yt-dlp does not save it on close.
        downloader.cookiejar = jar
    return downloader


def extraction_message(error, url):
    text = str(error).lower()
    site = 'Instagram' if 'instagram.com' in urlsplit(url).netloc else ('TikTok' if 'tiktok.com' in urlsplit(url).netloc else 'plataforma')
    if any(word in text for word in ['login', 'sign in', 'cookies', 'authentication']):
        return f'O {site} está exigindo uma sessão. Use “Importar sessão” com um arquivo de cookies da sua conta e tente novamente.'
    if any(word in text for word in ['429', 'rate limit', 'too many requests']):
        return f'O {site} limitou temporariamente as solicitações. Aguarde alguns minutos e tente novamente.'
    if any(word in text for word in ['403', 'forbidden', 'blocked', 'captcha', 'impersonat']):
        return f'O {site} bloqueou o acesso automatizado. Tente importar uma sessão. Isso não significa que o vídeo esteja privado.'
    if 'requested format' in text:
        return 'Esse formato/qualidade não está disponível para este vídeo. Tente MP4 ou MKV e outra qualidade.'
    if any(word in text for word in ['private', 'removed', 'not available', 'unavailable']):
        return f'O vídeo está indisponível para esta sessão no {site}. Confira se ele abre na sua conta e importe a sessão se necessário.'
    return f'Não foi possível obter o vídeo do {site}. Confira o link, tente importar uma sessão ou procure uma atualização do app.'


@app.post("/api/info")
def info(body: Request):
    url = validate_url(body.url)
    try:
        with make_downloader(options()) as downloader:
            data = downloader.extract_info(url, download=False)
        if data and data.get('_type') == 'playlist' and len(data.get('entries') or []) == 1:
            data = data['entries'][0]
        if not data or data.get("_type") in ("playlist", "multi_video"):
            raise HTTPException(400, "Use um link para um único vídeo.")
        heights = sorted({int(f["height"]) for f in data.get("formats", [])
                          if f.get("height") and f.get("vcodec") != "none"}, reverse=True)
        has_video = any(f.get('vcodec') != 'none' for f in data.get('formats', []))
        if not heights and not has_video:
            raise HTTPException(400, 'Nenhuma faixa de vídeo disponível neste link.')
        return {"title": data.get("title", "Vídeo"), "uploader": data.get("uploader") or "",
                "duration": data.get("duration"), "qualities": heights, "unknown_quality": not bool(heights)}
    except yt_dlp.utils.DownloadError as exc:
        raise HTTPException(422, extraction_message(exc, url))


@app.post("/api/download")
def download(body: Download):
    return prepare_download(body)


def prepare_download(body: Download, progress=None, directory=None):
    url = validate_url(body.url)
    folder = tempfile.TemporaryDirectory(prefix="kupotube-", dir=directory)
    try:
        # Remux only: never silently transcode a large video on the user's CPU.
        video_filter = '[ext=webm]' if body.container == 'webm' else ''
        audio_filter = '[ext=webm]' if body.container == 'webm' else ''
        opts = options() | {"outtmpl": str(Path(folder.name) / "video.%(ext)s"),
                            "format": f"bv*{video_filter}[height<=?{body.quality}]+ba{audio_filter}/b{video_filter}[height<=?{body.quality}]",
                            "merge_output_format": body.container, "restrictfilenames": True,
                            "postprocessors": [{'key': 'FFmpegVideoRemuxer', 'preferedformat': body.container}],
                            "max_filesize": 2 * 1024**3}
        if body.container == 'mp3':
            opts['format'] = 'bestaudio/best'
            opts.pop('merge_output_format', None)
            opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
        if 'tiktok.com' in urlsplit(url).netloc and body.container != 'mp3':
            # Prefer playback streams without a marked watermark; fall back when unavailable.
            base = opts['format']
            clean = base.replace('[height<=?', '[format_note!*=watermarked][height<=?')
            opts['format'] = clean + '/' + base
        if progress:
            def hook(data):
                total = data.get('total_bytes') or data.get('total_bytes_estimate')
                downloaded = data.get('downloaded_bytes') or 0
                percent = min(100, downloaded / total * 100) if total else None
                progress({'state': 'downloading' if data['status'] == 'downloading' else 'processing',
                          'percent': percent if data['status'] == 'downloading' else None,
                          'estimated': not bool(data.get('total_bytes')),
                          'track': 'Áudio' if data.get('info_dict', {}).get('vcodec') == 'none' else 'Vídeo',
                          'speed': data.get('speed'), 'eta': data.get('eta')})
            opts['progress_hooks'] = [hook]
            opts['postprocessor_hooks'] = [lambda _: progress({'state': 'processing', 'percent': None})]
        with make_downloader(opts) as downloader:
            data = downloader.extract_info(url, download=True)
        files = [p for p in Path(folder.name).iterdir() if p.suffix not in (".part", ".ytdl")]
        if len(files) != 1:
            raise HTTPException(422, "Não foi possível preparar o arquivo.")
        path = files[0]
        title = yt_dlp.utils.sanitize_filename(data.get("title") or "video", restricted=True)[:120]
        return FileResponse(path, filename=f"{title}{path.suffix}",
                            background=BackgroundTask(folder.cleanup))
    except Exception as exc:
        folder.cleanup()
        if isinstance(exc, HTTPException):
            raise
        detail = extraction_message(exc, url) if isinstance(exc, yt_dlp.utils.DownloadError) else 'O download falhou. Confira o espaço livre e tente outro formato.'
        raise HTTPException(422, detail) from exc


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
