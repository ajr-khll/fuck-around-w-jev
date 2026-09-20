"""Let Jev play Google's Snake.

The loop is deliberately plain: look at the board, turn it into text, ask Jev
which way to go, press that arrow key. Jev's answer goes straight to the
keyboard - nothing here second-guesses it, so a bad call really does kill the
snake. That is the point of the experiment.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .driver import SnakeBrowser
from .jev import JevPlayer
from .vision import find_board, read_grid

RUNS = Path("runs")


def load_api_key() -> None:
    """Read TYPESAFE_API_KEY out of a local .env file if it is not already set."""
    env_file = Path(".env")
    if os.environ.get("TYPESAFE_API_KEY") or not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "TYPESAFE_API_KEY":
            os.environ["TYPESAFE_API_KEY"] = value.strip().strip("\"'")


def play(max_turns: int, headless: bool, model: str, time_scale: float) -> dict:
    """Play one game and return a summary of it."""
    started = datetime.now(timezone.utc)
    transcript_path = RUNS / f"{started:%Y%m%d-%H%M%S}.jsonl"
    RUNS.mkdir(exist_ok=True)

    jev = JevPlayer(model=model)
    heading = "right"  # the snake always spawns heading right
    turns = 0
    longest = 0
    latencies: list[float] = []
    warned_of_death: list[bool] = []

    with SnakeBrowser(headless=headless, time_scale=time_scale) as browser, transcript_path.open(
        "w"
    ) as log:
        browser.start_game()

        while turns < max_turns:
            frame = browser.look()
            try:
                grid = read_grid(frame, find_board(frame))
            except LookupError:
                break  # the board is gone: the game is over

            if grid.head is None:
                # Mid-animation between cells; look again in a moment.
                browser.wait(30)
                continue

            longest = max(longest, len(grid.occupied()))

            asked_at = time.monotonic()
            decision = jev.decide(grid, heading)
            latency = time.monotonic() - asked_at
            latencies.append(latency)

            browser.press(decision.direction)
            heading = decision.direction
            turns += 1

            warned_of_death.append(decision.danger[decision.direction] > 0.5)

            log.write(
                json.dumps(
                    {
                        "turn": turns,
                        "board": grid.render(),
                        "head": grid.head,
                        "apple": grid.apple,
                        "length": len(grid.occupied()),
                        "move": decision.direction,
                        "confidence": decision.confidence,
                        "probabilities": decision.probabilities,
                        "danger": decision.danger,
                        "latency_seconds": round(latency, 3),
                    }
                )
                + "\n"
            )
            print(
                f"turn {turns:3d}  len {len(grid.occupied()):2d}  -> {decision.direction:<5}"
                f"  confidence {decision.confidence:.2f}"
                f"  self-rated danger {decision.danger[decision.direction]:.2f}"
                f"  {latency * 1000:.0f}ms"
            )

        browser.look().save(RUNS / f"{started:%Y%m%d-%H%M%S}-final.png")

    jev.close()

    summary = {
        "turns": turns,
        "longest_snake": longest,
        "median_latency_seconds": round(sorted(latencies)[len(latencies) // 2], 3)
        if latencies
        else None,
        "moves_jev_itself_called_deadly": sum(warned_of_death),
        "transcript": str(transcript_path),
    }
    (RUNS / f"{started:%Y%m%d-%H%M%S}-summary.json").write_text(
        json.dumps(summary, indent=2)
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Let Jev play Google's Snake.")
    parser.add_argument("--max-turns", type=int, default=200)
    parser.add_argument("--headless", action="store_true", help="hide the browser window")
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument(
        "--speed",
        type=float,
        default=0.2,
        help="game speed: 1.0 is normal, 0.2 (the default) is five times slower",
    )
    args = parser.parse_args()

    load_api_key()

    summary = play(args.max_turns, args.headless, args.model, args.speed)
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
