# Slimming While Winning

Webcam body tracking → keyboard input for games (first target: World of Warcraft).
Everything runs locally on the CPU. See `PROJECT_INSTRUCTIONS.md` and `docs/`.

**Current stage: roadmap step 1.** Put a hand on top of your head → tap `B`.

## Setup (Windows 10/11, once)

```powershell
winget install --id=astral-sh.uv -e      # if uv isn't installed yet; then reopen the terminal
cd C:\Users\vixie\projects\claude\slimming_while_winning
uv sync                                   # creates .venv with Python 3.14 + dependencies
uv run sww download-models                # fetches models\pose_landmarker_lite.task (~6 MB)
uv run pytest                             # webcam-free tests
```

## Step 1 test plan

1. **Tracking only, nothing sent** (dry run is the default):
   ```powershell
   uv run sww run --debug
   ```
   You'll see the mirrored preview with your skeleton, the `hand_on_head` score bar
   and, with `--debug`, the rule's live values. Put a hand on your head: the bar
   should fill, `ACTIVE` should appear and the terminal should print
   `[dry run] TAP 'b'` **once** per placement. Watch the `[perf]` lines (fps,
   tracking time, end-to-end latency). Press `q`/`Esc` to quit.

2. **Check key output alone in Notepad** (no camera):
   ```powershell
   uv run sww keytest --key b --send      # 3 s countdown: click into Notepad
   ```
   A single `b` should appear.

3. **Full pipeline into Notepad**, sending only while Notepad has focus:
   ```powershell
   uv run sww run --send --window Notepad
   ```
   Click into Notepad, put a hand on your head: one `b` per placement.

4. **WoW**: same as step 3 with `--window "World of Warcraft"`. Press B in game
   to confirm your bags bind, then use the gesture. Don't run WoW as administrator
   (Windows blocks injected input into elevated windows).

## Useful flags (`uv run sww run --help`)

| Flag | Meaning |
|---|---|
| `--send` | Really send keys (default is a dry run) |
| `--window TEXT` | Only send while the foreground window title contains TEXT |
| `--key KEY` | Key to tap (default `b`) |
| `--debug` | Show the rule's intermediate values for tuning |
| `--model lite/full/heavy` | Accuracy vs CPU (`download-models --variant full` first) |
| `--min-on-ms N` | How long the pose must hold before firing (latency trade-off) |
| `--tap-ms N` | How long the key is held for a tap (raise if the game misses taps) |
| `--no-preview` | Headless, terminal only |
| `--camera N`, `--width`, `--height`, `--fps` | Camera selection and mode |

## Layout

```
src/sww/
  capture.py      webcam thread, newest-frame-only
  tracking.py     MediaPipe PoseLandmarker (Tasks API, VIDEO mode)
  landmarks.py    landmark indices + PoseFrame (normalised image coords)
  features.py     body frame: origin mid-shoulders, y up, unit = shoulder width
  gestures/       detectors (score 0..1); hand_on_head.py is the first rule
  state.py        hysteresis + debounce → START/END events
  actions.py      gesture → key mapping (tap)
  engine.py       features → detectors → state → actions, per frame (replayable)
  output/         SendInput backend (scan codes), key names, focus gate
  preview.py      OpenCV overlay
  cli.py          `sww` command
tests/            webcam-free tests on synthetic landmark streams
```
