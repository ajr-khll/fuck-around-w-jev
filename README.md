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

### Knowing which way it is going

The heading is never read off the screen. The snake travels whichever way it was
last steered — and right, before it has been steered at all. The single press that
changes nothing is a reversal: the game refuses it and the snake carries on as it
was (verified, not assumed). So the heading is exact, and each request tells Jev
which of the four options the game is going to refuse.

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

.venv/bin/python -m snake.play                 # one game, in a window you can watch
.venv/bin/python -m snake.play --games 8        # eight games, same window
.venv/bin/python -m snake.play --headless       # no window, runs faster
.venv/bin/python -m snake.play --speed 1.0      # full speed, for the carnage
.venv/bin/python -m snake.play --record         # write an mp4 of the game
```

Games run back to back in a single window, because the menu after a death has the
same Play button the first one did.

Each run writes to `runs/`: a JSONL transcript with every board, move, probability
distribution, heading and latency, a summary, and a screenshot of each game's end.

## Recording it

`--record` writes an mp4 next to the transcript, with a panel beside the board
showing the text grid Jev is actually reading, its probability across the four
directions, and how long each decision took. Directions it flagged as fatal turn
red.

The game is played in slow motion so Jev has time to answer, and the video is sped
back up by the same factor — so the snake moves at its normal pace while every
decision on screen is one Jev really made. Output is H.264 / yuv420p with the moov
atom up front, which is what X and most players want.

[`jev-plays-snake.mp4`](jev-plays-snake.mp4) — 157 turns, 13 apples.

## How well does it play?

Over eight games, with no safety net and nothing but the text grid to go on:

| | |
| --- | --- |
| Best snake | **16** (12 apples) |
| Median snake | 7.5 |
| Median turns survived | 49.5 |
| Median decision latency | 160 ms |

Two perception bugs cost far more than the model ever did. A cell the snake was only
*animating into* counted as its body, which put a phantom obstacle directly in front
of the head on every frame; and tracking the head by its sprite drifted onto body
cells with no way back. Fixing those roughly doubled the median.

What kills it now is not walls but **enclosure** — it coils and runs out of room.
Jev is answering one question about one tick, with no memory of the shape it has
been building.
