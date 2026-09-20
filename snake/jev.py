"""Ask Jev which way to steer.

Jev is a System One model: it does not write code or explain itself, it returns
a typed answer constrained to options we defined. A snake turn is exactly that
shape, so one Choice question carries the whole decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from typesafe_sdk import Choice, Noul, TypeSafeClient

from .vision import COLS, ROWS, Grid

DIRECTIONS = ("up", "down", "left", "right")

# Which way each direction moves the head on the grid.
STEPS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}

OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}

MOVE_CRITERIA = {
    "up": "Move the head one row up, from row r to row r-1. Row 0 is the top.",
    "down": f"Move the head one row down, from row r to row r+1. Row {ROWS - 1} is the bottom.",
    "left": "Move the head one column left, from column c to column c-1. Column 0 is the left edge.",
    "right": f"Move the head one column right, from column c to column c+1. Column {COLS - 1} is the right edge.",
}

RULES = (
    f"The board is {COLS} columns wide and {ROWS} rows tall. Rows are numbered 0 at the "
    f"top to {ROWS - 1} at the bottom, columns 0 at the left to {COLS - 1} at the right. "
    "The snake moves one cell every tick and never stops. Steering into the wall kills "
    "it. Steering into any cell its own body occupies kills it. Reaching the apple makes "
    "it one cell longer and a new apple appears. Continuing in the current direction is "
    "always allowed; reversing straight back into its own neck is not."
)


@dataclass(frozen=True)
class Decision:
    """What Jev decided, and how sure it was."""

    direction: str
    probabilities: dict[str, float]
    confidence: float
    danger: dict[str, float]  # per-direction "this move kills me" probability


def describe(grid: Grid, heading: str) -> dict:
    """Render the frame as the text state Jev evaluates."""
    head_row, head_col = grid.head if grid.head else (None, None)
    apple_row, apple_col = grid.apple if grid.apple else (None, None)

    return {
        "board": grid.render(),
        "legend": {
            ".": "empty cell, safe to enter",
            "o": "the snake's own body, deadly to enter",
            "H": "the snake's head, where it is right now",
            "A": "the apple the snake is trying to reach",
        },
        "head": {"row": head_row, "column": head_col},
        "apple": {"row": apple_row, "column": apple_col},
        "current_heading": heading,
        "move_the_game_will_refuse": OPPOSITE[heading],
        "snake_length": len(grid.occupied()),
        "rules": RULES,
    }


def _move_criteria(heading: str) -> dict[str, str]:
    """The four options, with the one the game will refuse marked as such.

    Turning back on itself is the one move Snake ignores: the key press is
    dropped and the snake carries on the way it was already going. Jev can
    still choose it - nothing here overrides the answer - but it should know
    that choosing it means not steering at all.
    """
    criteria = dict(MOVE_CRITERIA)
    reverse = OPPOSITE[heading]
    criteria[reverse] += (
        f" The snake is currently heading {heading}, so this reverses it. The game "
        f"refuses this: the snake keeps going {heading} and the turn is wasted."
    )
    return criteria


def _questions(heading: str) -> dict:
    """One question that steers, plus four that only get logged.

    Jev evaluates every question in a request in parallel against the same
    state, so the danger readings cost almost nothing and tell us afterwards
    whether Jev saw a crash coming.
    """
    questions = {
        "move": Choice(
            instructions=(
                "You are playing Snake. Look at `board` and steer the snake marked H. "
                "Which direction should it move on this tick? Stay alive first: never "
                "steer into a wall or into the snake's own body. While you are safe, "
                "move so the head gets closer to the apple marked A."
            ),
            criteria=_move_criteria(heading),
        )
    }
    for direction in DIRECTIONS:
        questions[f"danger_{direction}"] = Noul(
            instructions=(
                f"If the snake in `board` moves {direction} on this tick, does it die "
                "by leaving the board or by entering a cell its own body occupies?"
            ),
            criteria={
                "true": "The move kills the snake.",
                "false": "The move is survivable.",
            },
        )
    return questions


class JevPlayer:
    """Wraps the TypeSafe client with the one question we ask it."""

    def __init__(self, model: str = "jev-latest", timeout: float = 10.0) -> None:
        self.client = TypeSafeClient(model=model, timeout=timeout)

    def decide(self, grid: Grid, heading: str) -> Decision:
        response = self.client.system_one(
            state=describe(grid, heading),
            questions=_questions(heading),
        )
        move = response.answers["move"]
        return Decision(
            direction=move.choice,
            probabilities=dict(move.probabilities),
            confidence=move.confidence,
            danger={d: response.answers[f"danger_{d}"].noul for d in DIRECTIONS},
        )

    def close(self) -> None:
        self.client.close()
