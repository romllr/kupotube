"""Cut a fully downloaded file, never seek directly in a remote video stream."""
from pathlib import Path
import subprocess
import sys

from fastapi import HTTPException
from yt_dlp.utils import Popen


def ffmpeg_executable():
    return str(Path(__file__).parent / 'tools' / 'ffmpeg.exe') if getattr(sys, 'frozen', False) else 'ffmpeg'


def cut_clip(source, destination, start, end, container):
    command = [ffmpeg_executable(), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
               '-ss', str(start), '-i', str(source), '-t', str(end - start)]
    if container == 'mp3':
        command += ['-map', '0:a:0', '-vn', '-c:a', 'libmp3lame', '-b:a', '192k']
    else:
        # Mandatory video mapping fails explicitly if the source is audio-only.
        command += ['-map', '0:v:0', '-map', '0:a:0?']
        command += (['-c:v', 'libvpx-vp9', '-c:a', 'libopus'] if container == 'webm' else
                    ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac'])
        if container == 'mp4':
            command += ['-movflags', '+faststart']
    command += [str(destination)]
    try:
        _, stderr, code = Popen.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
    except OSError as exc:
        raise HTTPException(422, 'O FFmpeg não pôde ser iniciado para recortar o arquivo. Reinstale a versão mais recente do Kupotube.') from exc
    if code:
        if 'matches no streams' in stderr or 'does not contain any stream' in stderr:
            raise HTTPException(422, 'O arquivo recebido não contém a faixa solicitada. O app não salvará áudio como vídeo. Tente outra qualidade ou outro link.')
        # No remote URL/cookies are passed to this command; do not expose local paths.
        raise HTTPException(422, 'O download terminou, mas o recorte falhou no FFmpeg. Tente um intervalo menor ou outro formato.')
    if not destination.is_file() or destination.stat().st_size == 0:
        raise HTTPException(422, 'O recorte não gerou um arquivo válido. Confira o início e o fim do trecho.')

    if container != 'mp3':
        # A successful FFmpeg exit alone does not guarantee decoded video frames.
        frame, _, code = Popen.run([ffmpeg_executable(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                                   '-i', str(destination), '-map', '0:v:0', '-frames:v', '1',
                                   '-vf', 'scale=1:1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if code or len(frame) < 3:
            raise HTTPException(422, 'O recorte não contém imagem válida. O app não salvará áudio como vídeo. Tente outra qualidade.')
