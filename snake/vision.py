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

# Below this much facial detail a cell is body, not head.
FACE_PIXEL_FLOOR = 25

# How much of a cell a thing must cover before the cell counts as its own.
OCCUPIED_FRACTION = 0.5


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

    The snake is blue and the apple is red against green, so counting clearly
    blue and clearly red pixels separates all three without any tuning.

    A cell only counts as taken when the colour fills most of it. The snake
    animates smoothly between cells, so at any instant it is part-way into the
    cell ahead; measured over a live game those part-entered cells cover about
    a quarter of a cell while a cell the snake really occupies covers at least
    three fifths. Counting the part-entered one would put a phantom body cell
    directly in front of the head, which is exactly where it matters.
    """
    red, green, blue = patch[..., 0], patch[..., 1], patch[..., 2]

    is_blue = (blue > 150) & (blue > red + 50)
    is_red = (red > 170) & (green < 130) & (blue < 110)

    if np.count_nonzero(is_blue) > red.size * OCCUPIED_FRACTION:
        return SNAKE
    if np.count_nonzero(is_red) > red.size * OCCUPIED_FRACTION:
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


def label(image: Image.Image, board: Board) -> tuple[list[list[str]], tuple[int, int] | None, dict[tuple[int, int], int]]:
    """Label every cell, and score how much facial detail each snake cell shows."""
    pixels = np.asarray(image.convert("RGB"), dtype=int)

    cells = [[EMPTY] * COLS for _ in range(ROWS)]
    apple: tuple[int, int] | None = None
    faces: dict[tuple[int, int], int] = {}

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

            cells[row][col] = _classify(patch)
            if cells[row][col] == APPLE:
                apple = (row, col)
            elif cells[row][col] == SNAKE:
                faces[(row, col)] = _face_pixels(whole)

    return cells, apple, faces


class SnakeTracker:
    """Follows the snake's head from one screenshot to the next.

    The head sprite alone is not enough to find it. Facing right its eyes are
    white, facing down they are dark slits, facing up there is barely a mark,
    and part-way through a step the face is drawn in the cell *behind* the one
    the snake is entering. Worse, a rule that only trusts the sprite can settle
    on a body cell and never recover.

    Motion is unambiguous: whichever cell the snake has just entered is where
    its head is. The sprite is only used to find the head on the first frame,
    and to recover if we ever lose the thread.
    """

    def __init__(self) -> None:
        self._occupied: set[tuple[int, int]] = set()
        self._head: tuple[int, int] | None = None

    def read(self, image: Image.Image, board: Board) -> Grid:
        cells, apple, faces = label(image, board)
        occupied = set(faces)

        self._head = self._follow(occupied, faces)
        self._occupied = occupied

        if self._head is not None:
            cells[self._head[0]][self._head[1]] = HEAD

        return Grid(cells=cells, head=self._head, apple=apple)

    def _follow(
        self, occupied: set[tuple[int, int]], faces: dict[tuple[int, int], int]
    ) -> tuple[int, int] | None:
        entered = occupied - self._occupied

        if self._head is None or self._head not in occupied:
            return self._seed(entered, faces)

        # The head can only step to a neighbouring cell. Anything else that
        # appeared is the tail flickering as it retracts between cells.
        stepped_into = [cell for cell in entered if _distance(cell, self._head) == 1]
        if stepped_into:
            return max(stepped_into, key=lambda cell: faces.get(cell, 0))

        if entered:
            # Cells appeared but none next to the head, so we have lost it.
            return self._seed(entered, faces)

        return self._head  # the snake has not advanced yet

    def _seed(
        self, entered: set[tuple[int, int]], faces: dict[tuple[int, int], int]
    ) -> tuple[int, int] | None:
        """Find the head from scratch, by its face."""
        if faces:
            cell, detail = max(faces.items(), key=lambda item: item[1])
            if detail >= FACE_PIXEL_FLOOR:
                return cell
        if len(entered) == 1:
            return entered.pop()
        return None


def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
