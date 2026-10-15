import ipaddress
import socket
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

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


def validate_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise HTTPException(400, "Use um link HTTPS válido.")
    if not any(host == h or host.endswith("." + h) for h in HOSTS):
        raise HTTPException(400, "Cole um link do YouTube, TikTok, Pinterest ou Instagram.")
    try:
        addresses = socket.getaddrinfo(host, 443)
        if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise HTTPException(400, "Endereço não permitido.")
    except socket.gaierror:
        raise HTTPException(400, "Não foi possível encontrar esse site.")
    return url


def options():
    opts = {"noplaylist": True, "quiet": True, "no_warnings": True,
            "socket_timeout": 30, "retries": 2, "cachedir": False}
    if getattr(sys, "frozen", False):
        opts["ffmpeg_location"] = str(ROOT / "tools")
        opts["js_runtimes"] = {"node": {"path": str(ROOT / "tools" / "node.exe")}}
    return opts


@app.post("/api/info")
def info(body: Request):
    url = validate_url(body.url)
    try:
        with yt_dlp.YoutubeDL(options()) as downloader:
            data = downloader.extract_info(url, download=False)
        if not data or data.get("_type") in ("playlist", "multi_video"):
            raise HTTPException(400, "Use um link para um único vídeo.")
        heights = sorted({int(f["height"]) for f in data.get("formats", [])
                          if f.get("height") and f.get("vcodec") != "none"}, reverse=True)
        if not heights:
            raise HTTPException(400, "Nenhuma qualidade de vídeo disponível.")
        return {"title": data.get("title", "Vídeo"), "uploader": data.get("uploader") or "",
                "duration": data.get("duration"), "qualities": heights}
    except yt_dlp.utils.DownloadError:
        raise HTTPException(422, "Não foi possível acessar o vídeo. Ele pode estar privado, restrito ou bloqueado pela plataforma.")


@app.post("/api/download")
def download(body: Download):
    url = validate_url(body.url)
    folder = tempfile.TemporaryDirectory(prefix="kupotube-")
    try:
        opts = options() | {"outtmpl": str(Path(folder.name) / "video.%(ext)s"),
                            "format": f"bv*[height<={body.quality}]+ba/b[height<={body.quality}]",
                            "merge_output_format": "mp4", "restrictfilenames": True,
                            "max_filesize": 2 * 1024**3}
        with yt_dlp.YoutubeDL(opts) as downloader:
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
        raise HTTPException(422, "O download falhou. Tente outra qualidade ou verifique se o vídeo é público.") from exc


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
