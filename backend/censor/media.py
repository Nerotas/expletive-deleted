"""Audio stream inspection shared by transcription and cached-transcript checks."""

import json
import subprocess


def probe_audio_stream(ffprobe_bin: str, input_file: str) -> tuple[int, str]:
    """Return the channel count and layout of the first audio stream."""
    try:
        result = subprocess.run(
            [ffprobe_bin, '-v', 'error', '-select_streams', 'a:0',
             '-show_entries', 'stream=channels,channel_layout', '-of', 'json',
             input_file],
            capture_output=True, text=True, timeout=5
        )
        streams = json.loads(result.stdout).get('streams', [])
        if not streams:
            return 0, ''
        return int(streams[0].get('channels', 0)), streams[0].get('channel_layout', '')
    except Exception:
        return 0, ''


def is_5_1_stream(channels: int, layout: str) -> bool:
    """Return whether audio metadata identifies a supported 5.1 layout."""
    return channels == 6 and layout in ('5.1', '5.1(side)')


def is_7_1_stream(channels: int, layout: str) -> bool:
    """Return whether audio metadata identifies a supported 7.1 layout."""
    return channels == 8 and layout in ('7.1', '7.1(wide)', '7.1(wide-side)')


def has_discrete_center_channel(channels: int, layout: str) -> bool:
    """Return whether audio has a supported discrete front-center channel."""
    return is_5_1_stream(channels, layout) or is_7_1_stream(channels, layout)
