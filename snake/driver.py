"""Drive Google's Snake in a real browser: start it, look at it, press keys."""

from __future__ import annotations

import io
from types import TracebackType

from PIL import Image
from playwright.sync_api import Page, sync_playwright

GAME_URL = "https://www.google.com/fbx?fbx=snake_arcade"

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

# The arrow key each direction maps to.
ARROW_KEYS = {
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
}


class SnakeBrowser:
    """A browser window with a game of Snake running in it."""

    def __init__(self, headless: bool = False, time_scale: float = 0.2) -> None:
        """time_scale is how fast the game runs: 1.0 is normal, 0.2 is five times slower."""
        self.headless = headless
        self.time_scale = time_scale
        self._playwright = None
        self._browser = None
        self._page: Page | None = None
        self._clip: dict[str, float] | None = None

    def __enter__(self) -> "SnakeBrowser":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        if self.time_scale != 1.0:
            self._page.add_init_script(SLOW_CLOCK % self.time_scale)
        self._page.goto(GAME_URL, wait_until="domcontentloaded")
        self._page.wait_for_timeout(4000)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
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
        self._clip = self._game_canvas_box()

    def _game_canvas_box(self) -> dict[str, float]:
        """The game canvas, so screenshots capture the board and nothing else."""
        box = self.page.evaluate(
            """() => {
                const canvas = [...document.querySelectorAll('canvas')]
                    .sort((a, b) => b.width * b.height - a.width * a.height)[0];
                const r = canvas.getBoundingClientRect();
                return {x: r.x, y: r.y, width: r.width, height: r.height};
            }"""
        )
        return box

    def look(self) -> Image.Image:
        """Screenshot the board."""
        raw = self.page.screenshot(clip=self._clip) if self._clip else self.page.screenshot()
        return Image.open(io.BytesIO(raw)).convert("RGB")

    def press(self, direction: str) -> None:
        """Steer the snake."""
        self.page.keyboard.press(ARROW_KEYS[direction])

    def wait(self, milliseconds: int) -> None:
        self.page.wait_for_timeout(milliseconds)
