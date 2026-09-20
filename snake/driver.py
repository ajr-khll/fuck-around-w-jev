"""Drive Google's Snake in a real browser: start it, look at it, press keys."""

from __future__ import annotations

import io
import time
from pathlib import Path
from types import TracebackType

from PIL import Image
from playwright.sync_api import Page, sync_playwright

from .overlay import INSTALL_OVERLAY, PANEL_WIDTH

GAME_URL = "https://www.google.com/fbx?fbx=snake_arcade"

WINDOW_WIDTH, WINDOW_HEIGHT = 1280, 900
# Recording needs room for the board and the decision panel beside it.
RECORDING_WIDTH, RECORDING_HEIGHT = 1400, 900

# The arrow key each direction maps to.
ARROW_KEYS = {
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
}

# The snake moves a cell every ~130ms at full speed, which is faster than a
# round trip to Jev. Rather than play with stale boards, we scale the clock the
# game reads so it runs in slow motion. The game itself is untouched: it still
# thinks it is running at normal speed, and every rule it enforces is the same.
SLOW_CLOCK = """
(() => {
  const SCALE = %s;
  const realPerformanceNow = performance.now.bind(performance);
  const performanceOrigin = realPerformanceNow();
  performance.now = () =>
    performanceOrigin + (realPerformanceNow() - performanceOrigin) * SCALE;

  const realDateNow = Date.now.bind(Date);
  const dateOrigin = realDateNow();
  Date.now = () => dateOrigin + (realDateNow() - dateOrigin) * SCALE;

  // Animation callbacks are handed a timestamp; give them the scaled one.
  const realRequestAnimationFrame = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (callback) =>
    realRequestAnimationFrame(() => callback(performance.now()));
})();
"""

BIGGEST_CANVAS = """() => [...document.querySelectorAll('canvas')]
    .sort((a, b) => b.width * b.height - a.width * a.height)[0]"""


class SnakeBrowser:
    """A browser window with a game of Snake running in it."""

    def __init__(
        self,
        headless: bool = False,
        time_scale: float = 0.2,
        record_dir: Path | None = None,
    ) -> None:
        """time_scale is how fast the game runs: 1.0 is normal, 0.2 is five times slower."""
        self.time_scale = time_scale
        self.record_dir = record_dir
        # A recording must hold still and be a known size, so it is always made
        # headless - a visible window would put its own flicker in the video.
        self.headless = True if record_dir else headless

        self._playwright = None
        self._browser = None
        self._context = None
        self._page: Page | None = None
        self._clip: dict[str, float] | None = None
        self._recording_started: float | None = None
        self.video_path: Path | None = None
        self.capture_region: dict[str, int] | None = None
        self.play_began_at: float | None = None

    def __enter__(self) -> "SnakeBrowser":
        self._playwright = sync_playwright().start()
        width = RECORDING_WIDTH if self.record_dir else WINDOW_WIDTH
        height = RECORDING_HEIGHT if self.record_dir else WINDOW_HEIGHT

        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                f"--window-size={width},{height}",
                # Pin the window so repeated runs do not walk across the screen.
                "--window-position=80,60",
            ],
        )

        options: dict = {}
        if self.record_dir:
            self.record_dir.mkdir(parents=True, exist_ok=True)
            options["record_video_dir"] = str(self.record_dir)
            options["record_video_size"] = {"width": width, "height": height}

        # A window you can watch gets its size from the real window. Playwright's
        # emulated viewport resizes the window around every screenshot, and we
        # screenshot several times a second, so the game visibly jumps and
        # flickers the whole way through. Headless has no window to disturb.
        if self.headless:
            options["viewport"] = {"width": width, "height": height}
        else:
            options["no_viewport"] = True

        self._context = self._browser.new_context(**options)
        if self.time_scale != 1.0:
            self._context.add_init_script(SLOW_CLOCK % self.time_scale)

        self._page = self._context.new_page()
        self._recording_started = time.monotonic()
        self._page.goto(GAME_URL, wait_until="domcontentloaded")
        self._page.wait_for_timeout(4000)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        video = self._page.video if (self._page and self.record_dir) else None
        if self._context is not None:
            self._context.close()  # the video is only written out on close
        if video is not None:
            self.video_path = Path(video.path())
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("use SnakeBrowser as a context manager")
        return self._page

    def start_game(self) -> None:
        """Click Play and wait for the snake to appear."""
        self.page.get_by_text("Play", exact=True).first.click()
        self.page.wait_for_timeout(2000)

        canvas = self.page.query_selector("canvas")
        box = self.page.evaluate(
            f"() => {{ const c = ({BIGGEST_CANVAS})(); const r = c.getBoundingClientRect();"
            "return {x: r.x, y: r.y, width: r.width, height: r.height}; }"
        )
        self._clip = box

        if self.record_dir and self.capture_region is None:
            self._install_overlay(box)
            self.play_began_at = time.monotonic() - (self._recording_started or 0)

    def _install_overlay(self, box: dict) -> None:
        """Put the decision panel on the page and note what the video should show."""
        self.page.evaluate(INSTALL_OVERLAY, self.page.evaluate_handle(BIGGEST_CANVAS))
        self.capture_region = {
            "x": int(box["x"]),
            "y": int(box["y"]),
            "width": int(box["width"]) + PANEL_WIDTH,
            "height": int(box["height"]),
        }

    def show_decision(self, payload: dict) -> None:
        """Update the on-page panel. Presentation only."""
        if self.record_dir:
            self.page.evaluate("(data) => window.__jev && window.__jev(data)", payload)

    def look(self) -> Image.Image:
        """Screenshot the board.

        The whole viewport is captured and cropped here, rather than asking the
        browser for a clipped screenshot. A clipped capture makes the page
        re-lay-out for an instant - the game shrinks into the corner - and since
        we capture several times a second that shows up as a constant flicker,
        both on screen and in a recording.
        """
        image = Image.open(io.BytesIO(self.page.screenshot())).convert("RGB")
        if self._clip is None:
            return image

        left, top = int(self._clip["x"]), int(self._clip["y"])
        return image.crop(
            (left, top, left + int(self._clip["width"]), top + int(self._clip["height"]))
        )

    def press(self, direction: str) -> None:
        """Steer the snake."""
        self.page.keyboard.press(ARROW_KEYS[direction])

    def wait(self, milliseconds: int) -> None:
        self.page.wait_for_timeout(milliseconds)
