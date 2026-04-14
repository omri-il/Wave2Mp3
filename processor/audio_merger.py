"""
processor/audio_merger.py — FFmpeg concat + WAV→MP3 conversion.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


def merge_session(wav_paths: list[Path], session_id: str, bitrate: str = "128k") -> Path:
    """
    Merge multiple .wav files into a single .mp3.

    Uses FFmpeg's concat demuxer for lossless concatenation, then encodes to MP3.
    Returns the path to the output .mp3 file.
    """
    mp3_path = settings.temp_dir / f"{session_id}.mp3"

    if len(wav_paths) == 1:
        # Single file — just convert
        _convert_to_mp3(wav_paths[0], mp3_path, bitrate)
    else:
        # Multiple files — concat then convert
        concat_path = settings.temp_dir / f"{session_id}_concat.wav"
        try:
            _concat_wav(wav_paths, concat_path)
            _convert_to_mp3(concat_path, mp3_path, bitrate)
        finally:
            concat_path.unlink(missing_ok=True)

    size_mb = mp3_path.stat().st_size / (1024 * 1024)
    logger.info("Created %s (%.1f MB)", mp3_path.name, size_mb)
    return mp3_path


def _concat_wav(wav_paths: list[Path], output: Path) -> None:
    """Concatenate multiple .wav files using FFmpeg concat demuxer."""
    # Write concat file list
    list_file = output.with_suffix(".txt")
    try:
        with list_file.open("w") as f:
            for p in wav_paths:
                # FFmpeg requires forward slashes and escaping
                escaped = str(p).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output),
        ]
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")
    finally:
        list_file.unlink(missing_ok=True)


def _convert_to_mp3(input_path: Path, output_path: Path, bitrate: str) -> None:
    """Convert a .wav file to .mp3 using FFmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-codec:a", "libmp3lame",
        "-b:a", bitrate,
        str(output_path),
    ]
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg convert failed: {result.stderr}")
