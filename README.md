# fuck-around-w-jev

Letting **Jev**, [TypeSafe's](https://docs.typesafe.ai) System One model, play Google's Snake.

Jev doesn't generate text or explain itself — it returns typed answers constrained to
options you define. A snake turn is exactly that shape, so the whole decision is one
`Choice` question over `up / down / left / right`, and its answer goes straight to the
arrow keys.

## How it works

Jev is **text only** — it can't look at a screenshot. So code does the seeing and the
model does the deciding:

```
Playwright screenshot  ->  vision.py  ->  17x15 text grid  ->  Jev  ->  arrow key
```

```
.................
.................
.......A.........
.................
....ooooH........      "H is the head, A is the apple, o is deadly.
....o............       Which way should it move?"   -> "right"
....o............
.................
```

| Module | Job |
| --- | --- |
| `snake/vision.py` | Finds the board in a screenshot and labels all 255 cells by colour |
| `snake/driver.py` | Runs the real game in Chromium, screenshots it, presses arrow keys |
| `snake/jev.py` | Turns a grid into `state` + questions, asks Jev |
| `snake/play.py` | The loop, and the run transcript |

### No safety net

Jev's answer is sent to the keyboard unmodified. Nothing here checks whether the move
walks into a wall, so a bad call really does kill the snake. Every run also logs what
Jev *itself* thought the danger was (four `noul` questions, evaluated in the same
request, for free) — so the transcript shows how often it walked into a wall it had
already flagged as deadly.

### Slow motion

At full speed the snake moves a cell every **130 ms**, faster than a round trip to any
API. So the driver scales the clock the page reads (`performance.now`, `Date.now`,
`requestAnimationFrame`), and the game runs in slow motion — 0.2x by default, about
**670 ms per cell**. The game is otherwise untouched and enforces all its own rules.

## Running it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium

echo 'TYPESAFE_API_KEY=your-key-here' > .env   # from https://console.typesafe.ai/

.venv/bin/python -m snake.play                 # watch it play
.venv/bin/python -m snake.play --headless --max-turns 50
.venv/bin/python -m snake.play --speed 1.0     # full speed, for the carnage
```

Each run writes to `runs/`: a JSONL transcript with every board, move, probability
distribution and latency, a summary, and a final screenshot.
