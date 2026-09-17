"""Offline qualification using existing FFmpeg; generates only temporary synthetic media."""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from threading import Event

from backend.filesystem.paths import RootBinding
from backend.filesystem.publication import Publication
from backend.runtime import find_ffmpeg, find_ffprobe


def main():
    ffmpeg, ffprobe = find_ffmpeg(), find_ffprobe()
    if not ffmpeg or not ffprobe:
        raise RuntimeError('Qualification requires already installed FFmpeg and FFprobe; nothing is downloaded')
    with tempfile.TemporaryDirectory(prefix='media-publication-') as temporary:
        root = RootBinding.capture(Path(temporary))
        destination = root.configured / 'synthetic.mkv'

        def encode(stage):
            subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=64x64:d=1',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:v', 'ffv1',
                            '-c:a', 'pcm_s16le', '-shortest', str(stage)], check=True, timeout=30)

        def verify(stage):
            result = subprocess.run([ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(stage)],
                                    capture_output=True, text=True, check=True, timeout=15)
            streams = json.loads(result.stdout)['streams']
            if not {'audio', 'video'} <= {stream['codec_type'] for stream in streams}:
                raise RuntimeError('Missing required synthetic streams')

        with Publication(root, destination) as output:
            encode(output.stage)
            output.publish(verify)
        original = hashlib.sha256(destination.read_bytes()).digest()
        cancelled = Event()
        try:
            with Publication(root, destination, overwrite=True, cancellation=cancelled) as output:
                encode(output.stage)
                def cancel_after_verification(stage):
                    verify(stage)
                    cancelled.set()
                output.publish(cancel_after_verification)
        except InterruptedError:
            pass
        else:
            raise AssertionError('Cancelled replacement was published')
        assert hashlib.sha256(destination.read_bytes()).digest() == original
        assert list(root.configured.iterdir()) == [destination]
    print('Real FFmpeg qualification passed: readable audio/video, cancelled replacement, unchanged prior output, clean staging.')


if __name__ == '__main__':
    main()
