"""Validate the exact FFmpeg binary shipped to Windows, without requiring ffprobe."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from media import cut_clip


def main():
    executable = str(Path(sys.argv[1]).resolve())
    def run(*args):
        return subprocess.run([executable, '-nostdin', '-hide_banner', '-loglevel', 'error', *args],
                              check=True, capture_output=True, text=True).stdout
    with tempfile.TemporaryDirectory(prefix='kupo-media-') as temporary:
        root = Path(temporary)
        original = root / 'original.mp4'
        run('-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=24', '-f', 'lavfi', '-i',
            'sine=frequency=440', '-t', '6', '-c:v', 'libx264', '-c:a', 'aac', str(original))
        with patch('media.ffmpeg_executable', return_value=executable):
            for extension in ['mp4', 'mkv', 'webm', 'mp3']:
                target = root / f'clip.{extension}'
                cut_clip(original, target, 1, 3, extension)
                args = ['-i', str(target), '-map', '0:a:0', '-progress', 'pipe:1', '-f', 'null', '-']
                progress = run(*args)
                times = [int(line.split('=',1)[1]) for line in progress.splitlines() if line.startswith('out_time_us=')]
                assert times and 1800000 <= max(times) <= 2300000, (extension, times)
                if extension != 'mp3':
                    run('-i', str(target), '-map', '0:v:0', '-frames:v', '1', '-f', 'null', '-')
            audio = root / 'audio.m4a'
            run('-i', str(original), '-vn', '-c:a', 'copy', str(audio))
            try:
                cut_clip(audio, root / 'invalid.mp4', 1, 3, 'mp4')
            except HTTPException as exc:
                assert 'não salvará áudio como vídeo' in exc.detail
            else:
                raise AssertionError('Audio-only input was accepted as video')
    print('Bundled FFmpeg passed: MP4/MKV/WebM image and audio, MP3, durations, audio-only rejection')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        if os.environ.get('GITHUB_ACTIONS'):
            detail = traceback.format_exc().encode('ascii','backslashreplace').decode('ascii').replace('%','%25').replace('\r','%0D').replace('\n','%0A')
            print(f'::error title=Falha no FFmpeg incluido::{detail}', flush=True)
        raise
