"""Turn the raw capture into something worth posting."""

from __future__ import annotations

import subprocess
from pathlib import Path


def finish(
    raw: Path,
    region: dict[str, int],
    start_at: float,
    time_scale: float,
    destination: Path,
) -> Path:
    """Crop to the game, restore natural speed, and encode for sharing.

    The game is played in slow motion so Jev has time to answer, which makes the
    raw capture crawl. Speeding the video back up by the same factor puts the
    snake at its normal pace again - the thinking time is real, it just is not
    what anyone wants to watch.
    """
    speed_up = 1 / time_scale
    crop = f"crop={region['width']}:{region['height']}:{region['x']}:{region['y']}"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            # Seek before the input so the trimmed clip starts at a clean zero;
            # PTS-STARTPTS then rebases what is left before it is sped up.
            "-ss", f"{start_at:.2f}",
            "-i", str(raw),
            "-vf", f"{crop},setpts=(PTS-STARTPTS)/{speed_up:g},fps=30",
            "-an",
            "-c:v", "libx264",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",  # required for playback on X and most players
            "-crf", "20",
            "-movflags", "+faststart",
            str(destination),
        ],
        check=True,
    )
    return destination
