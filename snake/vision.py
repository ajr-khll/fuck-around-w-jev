"""Turn a screenshot of Google's Snake into a grid of cells.

Jev accepts text only, so this module is the eyes: it finds the board in the
screenshot, slices it into cells, and labels each one by colour. Everything
downstream works on the labelled grid, never on pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

# The two greens of the board's checkerboard, sampled from a live game.
CHECKER_LIGHT = (170, 215, 81)
CHECKER_DARK = (162, 209, 73)

# Google's board is always 17 cells wide and 15 tall.
COLS, ROWS = 17, 15

EMPTY, SNAKE, HEAD, APPLE = ".", "o", "H", "A"

# Below this much facial detail we are looking at the nose spilling into the
# next cell, not at the head itself.
FACE_PIXEL_FLOOR = 25


@dataclass(frozen=True)
class Board:
    """Where the playing field sits inside the screenshot, in pixels."""

    left: int
    top: int
    width: int
    height: int

    @property
    def cell_width(self) -> float:
        return self.width / COLS

    @property
    def cell_height(self) -> float:
        return self.height / ROWS


@dataclass(frozen=True)
class Grid:
    """One frame of the game, as labelled cells."""

    cells: list[list[str]]  # cells[row][col], one of EMPTY/SNAKE/HEAD/APPLE
    head: tuple[int, int] | None  # (row, col)
    apple: tuple[int, int] | None  # (row, col)

    def render(self) -> str:
        """The grid as text, which is what Jev actually reads."""
        return "\n".join("".join(row) for row in self.cells)

    def occupied(self) -> set[tuple[int, int]]:
        """Cells the snake's own body fills, head included."""
        return {
            (r, c)
            for r, row in enumerate(self.cells)
            for c, cell in enumerate(row)
            if cell in (SNAKE, HEAD)
        }


def find_board(image: Image.Image) -> Board:
    """Locate the playing field by finding every checkerboard pixel.

    Calibrating from the picture rather than hardcoding coordinates keeps this
    working when the window is a different size.
    """
    pixels = np.asarray(image.convert("RGB"), dtype=int)
    is_checker = np.all(pixels == CHECKER_LIGHT, axis=-1) | np.all(
        pixels == CHECKER_DARK, axis=-1
    )
    rows, cols = np.nonzero(is_checker)
    if rows.size == 0:
        raise LookupError("no checkerboard in this screenshot - is a game running?")

    left, top = int(cols.min()), int(rows.min())
    return Board(
        left=left,
        top=top,
        width=int(cols.max()) + 1 - left,
        height=int(rows.max()) + 1 - top,
    )


def _classify(patch: np.ndarray) -> str:
    """Label one cell from the colours inside it.

    The snake is blue and the apple is red against green, so a count of clearly
    blue and clearly red pixels separates all three without any tuning.
    """
    red, green, blue = patch[..., 0], patch[..., 1], patch[..., 2]

    blue_pixels = int(np.count_nonzero((blue > 150) & (blue > red + 50)))
    red_pixels = int(np.count_nonzero((red > 170) & (green < 130) & (blue < 110)))

    # A cell is only claimed when a decent share of it carries the colour, which
    # ignores the anti-aliased fringe bleeding in from a neighbour.
    threshold = patch[..., 0].size * 0.15
    if blue_pixels > threshold:
        return SNAKE
    if red_pixels > threshold:
        return APPLE
    return EMPTY


def _face_pixels(patch: np.ndarray) -> int:
    """Count pixels belonging to the snake's face, which only the head has.

    The body is flat blue. The head carries eyes, and they read as white when
    the snake faces left, right or up, and as dark closed slits when it faces
    away from us going down. Counting both kinds of detail finds the head in
    every direction; body cells score zero.
    """
    red, green, blue = patch[..., 0], patch[..., 1], patch[..., 2]
    is_blue = (blue > 150) & (blue > red + 50)

    dark_markings = np.count_nonzero(is_blue & (patch.sum(axis=-1) < 380))
    white_eyes = np.count_nonzero(np.all(patch > 200, axis=-1))
    return int(dark_markings + white_eyes)


def read_grid(image: Image.Image, board: Board) -> Grid:
    """Read one screenshot into a labelled grid."""
    pixels = np.asarray(image.convert("RGB"), dtype=int)

    cells = [[EMPTY] * COLS for _ in range(ROWS)]
    apple: tuple[int, int] | None = None
    best_head: tuple[int, int] | None = None
    most_face = 0

    for row in range(ROWS):
        for col in range(COLS):
            top = board.top + board.cell_height * row
            left = board.left + board.cell_width * col
            whole = pixels[
                int(top) : int(top + board.cell_height),
                int(left) : int(left + board.cell_width),
            ]
            # Classify from the middle of the cell, where the edges cannot blend
            # in colour from a neighbouring cell.
            inset_y = int(board.cell_height * 0.2)
            inset_x = int(board.cell_width * 0.2)
            patch = whole[inset_y:-inset_y, inset_x:-inset_x]

            label = _classify(patch)
            cells[row][col] = label

            if label == APPLE:
                apple = (row, col)
            elif label == SNAKE:
                face = _face_pixels(whole)
                if face > most_face:
                    most_face, best_head = face, (row, col)

    if most_face >= FACE_PIXEL_FLOOR and best_head is not None:
        cells[best_head[0]][best_head[1]] = HEAD
    else:
        best_head = None

    return Grid(cells=cells, head=best_head, apple=apple)
