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
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from .driver import SnakeBrowser
from .jev import OPPOSITE, JevPlayer
from .video import finish
from .vision import SnakeTracker, find_board

RUNS = Path("runs")

# How long to wait before looking again, when the snake has not moved yet.
LOOK_AGAIN_MS = 30


def steer(heading: str, key: str) -> str:
    """The direction the snake travels after a key press.

    We do not have to read this off the screen: the snake goes whichever way we
    last steered it, and right if we have not steered it at all. The one press
    that changes nothing is a reversal, which the game refuses, so the snake
    carries on as it was.
    """
    return heading if key == OPPOSITE[heading] else key


def load_api_key() -> None:
    """Read TYPESAFE_API_KEY out of a local .env file if it is not already set."""
    env_file = Path(".env")
    if os.environ.get("TYPESAFE_API_KEY") or not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "TYPESAFE_API_KEY":
            os.environ["TYPESAFE_API_KEY"] = value.strip().strip("\"'")


def play_game(
    browser: SnakeBrowser, jev: JevPlayer, game: int, max_turns: int, log: TextIO
) -> dict:
    """Play one game, until the snake dies or runs out of turns."""
    browser.start_game()

    tracker = SnakeTracker()
    heading = "right"
    last_head: tuple[int, int] | None = None
    turns = 0
    longest = 0
    latencies: list[float] = []
    walked_into_own_warning = 0

    while turns < max_turns:
        frame = browser.look()
        try:
            grid = tracker.read(frame, find_board(frame))
        except LookupError:
            break  # the board is gone: the snake is dead

        if grid.head is None:
            browser.wait(LOOK_AGAIN_MS)  # mid-step between cells
            continue

        # We look several times per tick. Only spend a decision once the snake
        # has actually advanced, so every answer is about a fresh board.
        if grid.head == last_head:
            browser.wait(LOOK_AGAIN_MS)
            continue

        asked_at = time.monotonic()
        decision = jev.decide(grid, heading)
        latency = time.monotonic() - asked_at

        browser.press(decision.direction)
        heading = steer(heading, decision.direction)

        browser.show_decision(
            {"probabilities": decision.probabilities, "danger": decision.danger}
        )

        last_head = grid.head
        turns += 1
        longest = max(longest, len(grid.occupied()))
        latencies.append(latency)
        if decision.danger[decision.direction] > 0.5:
            walked_into_own_warning += 1

        log.write(
            json.dumps(
                {
                    "game": game,
                    "turn": turns,
                    "board": grid.render(),
                    "head": grid.head,
                    "apple": grid.apple,
                    "length": len(grid.occupied()),
                    "heading": heading,
                    "board": grid.render(),
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
            f"game {game}  turn {turns:3d}  len {len(grid.occupied()):2d}"
            f"  -> {decision.direction:<5}  confidence {decision.confidence:.2f}"
            f"  self-rated danger {decision.danger[decision.direction]:.2f}"
            f"  {latency * 1000:.0f}ms"
        )

    return {
        "game": game,
        "turns": turns,
        "longest_snake": longest,
        "apples": max(longest - 4, 0),  # the snake starts four cells long
        "median_latency_seconds": round(statistics.median(latencies), 3)
        if latencies
        else None,
        "moves_jev_itself_called_deadly": walked_into_own_warning,
    }


def play(
    games: int,
    max_turns: int,
    headless: bool,
    model: str,
    time_scale: float,
    record: bool = False,
) -> dict:
    """Play several games in one browser window, and summarise them."""
    started = datetime.now(timezone.utc)
    RUNS.mkdir(exist_ok=True)
    stem = RUNS / f"{started:%Y%m%d-%H%M%S}"

    jev = JevPlayer(model=model)
    played: list[dict] = []

    with SnakeBrowser(
        headless=headless,
        time_scale=time_scale,
        record_dir=RUNS / "video" if record else None,
    ) as browser:
        with Path(f"{stem}.jsonl").open("w") as log:
            for game in range(1, games + 1):
                played.append(play_game(browser, jev, game, max_turns, log))
                browser.look().save(f"{stem}-game{game}.png")
                print(f"  -> {json.dumps(played[-1])}")

    jev.close()

    if record and browser.video_path and browser.capture_region:
        summary_video = finish(
            raw=browser.video_path,
            region=browser.capture_region,
            start_at=browser.play_began_at or 0,
            time_scale=time_scale,
            destination=Path(f"{stem}.mp4"),
        )
        browser.video_path.unlink(missing_ok=True)
        print(f"\nvideo: {summary_video}")

    summary = {
        "games": played,
        "best_length": max(g["longest_snake"] for g in played),
        "median_length": statistics.median(g["longest_snake"] for g in played),
        "median_turns": statistics.median(g["turns"] for g in played),
        "transcript": f"{stem}.jsonl",
    }
    Path(f"{stem}-summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Let Jev play Google's Snake.")
    parser.add_argument("--games", type=int, default=1, help="games to play in one window")
    parser.add_argument("--max-turns", type=int, default=250)
    parser.add_argument("--headless", action="store_true", help="hide the browser window")
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument(
        "--speed",
        type=float,
        default=0.2,
        help="game speed: 1.0 is normal, 0.2 (the default) is five times slower",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="record an mp4 with a panel showing Jev's decisions (implies headless)",
    )
    args = parser.parse_args()

    load_api_key()
    summary = play(
        args.games, args.max_turns, args.headless, args.model, args.speed, args.record
    )
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
