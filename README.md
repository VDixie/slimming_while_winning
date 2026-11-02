# Slimming While Winning

Webcam body tracking → keyboard input for games (first target: World of Warcraft).
Everything runs locally on the CPU. See `PROJECT_INSTRUCTIONS.md` and `docs/`.

**Current stage: roadmap step 2.**

| Gesture | Key | Mode |
|---|---|---|
| Hand on top of your head | `B` | tap (one press + release) |
| Running in place (arm swing + upper-body bounce) | `W` | hold (one key-down while running, one key-up when you stop) |

Pause/resume all output anywhere with **Ctrl+Alt+P** (all held keys are released).

## Setup (Windows 10/11, once)

```powershell
winget install --id=astral-sh.uv -e      # if uv isn't installed yet; then reopen the terminal
cd C:\Users\vixie\projects\claude\slimming_while_winning
uv sync                                   # creates .venv with Python 3.14 + dependencies
uv run sww download-models                # fetches models\pose_landmarker_lite.task (~6 MB)
uv run pytest                             # webcam-free tests
```

## Step 2 test plan

1. **Dry run with tuning view** (nothing is sent):
   ```powershell
   uv run sww run --debug
   ```
   Stand where you play and run in place, swinging your arms naturally. Expect
   `[dry run] DOWN 'w'` about 0.5 s after you start and `[dry run] UP 'w'` about
   0.6 s after you stop, **once each** per run. The graphs (bottom right) show the
   `running_in_place` score, the arm-swing signal (left minus right wrist height)
   and the bounce signal (shoulder height); both should swing evenly while running.
   The score needs **both**. Also try:
   - standing still, gesturing with your arms, bobbing or shifting weight without
     swinging your arms: no `DOWN`
   - **Ctrl+Alt+P** while running: `RELEASE 'w' (paused)`, then `PAUSED`; again to resume.
     It works while another window has focus. You must stop and start running again
     after resuming (a resume never presses keys by itself).
   - walking out of view while running: `UP 'w'` within ~0.2 s

2. **Record yourself** (landmarks only, no video, saved under `recordings/`, which is
   git-ignored):
   ```powershell
   uv run sww record --label running --seconds 20   # stand ~5 s, run ~10 s, stand ~5 s
   uv run sww record --label idle --seconds 30      # normal play movements, no running
   ```
   Each recording is replayed straight away through the same engine as `run`
   (nothing is sent). It prints every action, how long each gesture was active and
   its peak score, and writes `recordings\<label>_<time>.csv` next to the `.npz`:
   one row per frame with every rule value, ready for pandas. `--no-csv` skips this.
   After changing detectors, refresh a CSV with `uv run sww replay <file>.npz --csv`.
   Send me the output (or the files) and I'll tune the thresholds on your real data.

   **Label when you really ran** (needed when a recording mixes standing and
   running). Next to `running_<time>.npz`, create `running_<time>.labels.json`:
   ```json
   {"running": [[4.0, 13.4]]}
   ```
   Times are seconds from the start of the recording, the same times `sww replay`
   prints; `null` as the end means "until the recording ends", `[]` means "never".
   ~0.2 s precision is enough. Then:
   - `uv run pytest tests/test_real_recordings.py` checks every recording: one W per
     labelled run, started within ~1 s, released within ~1 s of stopping, never
     outside a run. Without a labels file, a `running` recording counts as running
     the whole time and `idle` as never.
   - `sww replay` prints the start and stop delay per run and adds a
     `label.running` column (0/1 per frame) to the CSV: the training target for a
     learned model later (step 4).

3. **Hold a key on its own, in Notepad** (no camera):
   ```powershell
   uv run sww keytest --key w --hold-s 2 --send     # 3 s countdown: click into Notepad
   ```
   Expect a **single** `w`. A physical key held for 2 s would type `wwwww...`
   (Windows auto-repeat), but an injected key-down is one event. Games read
   whether the key is down, not the repeats.

4. **Full pipeline into Notepad**:
   ```powershell
   uv run sww run --send --window Notepad
   ```
   Run in place: one `w`. While running, press Ctrl+Alt+P, or click another window:
   the console prints `RELEASE 'w'`.

5. **WoW**: `uv run sww run --send --window "World of Warcraft"`. Your character should
   run forward while you run in place and stop about half a second after you stop.
   If it doesn't stop: press Ctrl+Alt+P, or tap W on the keyboard.

Seated? `--forward arms` uses the arm swing alone (no bounce needed).

## Safety

- Dry run unless `--send`. `--send` refuses to start without the pause hotkey.
- Every held key is released when: the gesture ends, you pause, the `--window`
  target loses focus, the person is lost for 150 ms, the camera stalls, or the app
  exits (q/Esc, Ctrl+C, an error, or closing the console window).
- **Not covered:** force-killing the process (Task Manager / `taskkill /f`).
  Windows then keeps W "down" until you press W on the real keyboard once.

## Useful flags (`uv run sww run --help`)

| Flag | Meaning |
|---|---|
| `--send` | Really send keys (default is a dry run) |
| `--window TEXT` | Only send while the foreground window title contains TEXT |
| `--head-key KEY` | Key tapped by hand on head (default `b`; `--key` still works) |
| `--forward run/arms/off` | Forward gesture: running in place (arms + bounce), pumping arms only (seated), or none |
| `--forward-key KEY` | Key held while running (default `w`) |
| `--forward-off-ms N` | How long you must stop before the key is released (default 200) |
| `--pause-hotkey SPEC` | Global pause hotkey, e.g. `ctrl+alt+p` (default), `pause`, `ctrl+shift+f9` |
| `--start-paused` | Start with output paused |
| `--debug` | Show rule values and rolling graphs for tuning |
| `--model lite/full/heavy` | Accuracy vs CPU (`download-models --variant full` first) |
| `--min-on-ms N` | How long hand-on-head must hold before firing |
| `--tap-ms N` | How long a tap holds the key (raise if the game misses taps) |
| `--no-preview` | Headless, terminal only |
| `--camera N`, `--width`, `--height`, `--fps` | Camera selection and mode |
| `--api dshow/msmf` | Windows capture backend (try the other one if fps is low) |
| `--no-mjpg` | Don't request compressed MJPG frames |

## Low frame rate?

```powershell
uv run sww bench
```
Times the camera (each backend x MJPG on/off x 720p/480p) and the pose model
separately, then prints the fastest camera settings. The run loop can't beat
the slower of the two.

## Layout

```
src/sww/
  capture.py      webcam thread, newest-frame-only
  tracking.py     MediaPipe PoseLandmarker (Tasks API, VIDEO mode)
  landmarks.py    landmark indices + PoseFrame (normalised image coords)
  features.py     body frame: origin mid-shoulders, y up, unit = shoulder width
  window.py       rolling window of recent body frames (time-bounded)
  gestures/       detectors (score 0..1): hand_on_head.py (static),
                  oscillation.py (generic rhythmic-signal rule),
                  running.py (arm swing + body bounce)
  state.py        hysteresis + debounce → START/END events
  actions.py      gesture → key mapping (tap / hold), pause, safety releases
  engine.py       window → detectors → state → actions, per frame (replayable)
  recording.py    landmark recordings (.npz) for replay, tuning and tests
  labels.py       hand-written ground truth (<name>.labels.json) and checks
  output/         SendInput backend (scan codes), key names, focus gate,
                  global pause hotkey, console-close handler
  preview.py      OpenCV overlay + debug graphs
  bench.py        camera vs model timing (`sww bench`)
  cli.py          `sww` command: run, record, replay, keytest, bench, download-models
tests/            webcam-free tests on synthetic landmark streams
```
