# Project Status

> Update at the end of each work session. Keep it short — this is a snapshot,
> not a history (history goes in DECISIONS.md, docs/sessions/ and Git).

**Last updated:** 2026-11-02
**Current roadmap step:** 2 — Built; running (arm swing + bounce) tuned on real recordings; live tests pending

## Roadmap
| Step | Description | Status |
|---|---|---|
| 0 | Project instructions, context files, initial decisions | ✅ Done |
| 1 | CLI: webcam → landmarks → one rule-based static gesture → one key tap (test in Notepad, then WoW) | ✅ Done (verified in Notepad and WoW) |
| 2 | Hold behaviour + one dynamic gesture (running in place → hold W) | 🟡 Built; tuned on recordings (arm swing + bounce); live, Notepad and WoW tests pending |
| 3 | YAML config, calibration, ~~pause hotkey, safety releases~~ (moved to step 2) | ⬜ |
| 4 | Landmark recording to file + trained classifier for custom gestures | ⬜ (recording done early, in step 2) |
| 5 | Voice commands (Vosk) | ⬜ |
| 6 | PySide6 GUI: record, train, map, test | ⬜ |
| 7 | Package as standalone .exe | ⬜ |

## What works
- Step 1: hand on head → tap B, verified with `--send` in Notepad and WoW
- Step 2 (synthetic tests only so far):
  - **Hold mode**: one key-down on gesture start, one key-up on end; never a second key-down
  - **Running in place → hold W** = arm swing AND upper-body bounce (`RunningInPlace`,
    `--forward run`, default); `--forward arms` = arm swing only (seated)
  - **Global pause hotkey** Ctrl+Alt+P (`RegisterHotKey` on its own thread), also `p`
    in the preview
  - **Safety releases**: gesture end, pause, focus loss (checked every frame), person
    lost for 150 ms, camera stall, exit/exception/Ctrl+C, console window closed.
    Re-arm rule: no automatic re-press after a safety release
  - `sww record` (landmarks → .npz, then automatically replayed into a per-frame .csv)
    and `sww replay` (same engine, dry run, `--csv` to refresh the CSV)
  - `sww keytest --hold-s N` to test a single injected hold
  - `--debug` rolling graphs of the score, arm-swing and bounce signals
- **First real recordings** (running + idle): knees turned out to be out of frame and
  were removed. Arm swing and bounce were tuned on them: one key-down for the whole
  running recording, nothing on idle, in both `run` and `arms` modes
- Off-screen landmarks are now ignored (MediaPipe guesses them with high visibility)
- 135 tests pass (incl. replay of local recordings when present); Ruff clean

## Performance
- Ryzen 9 5900X, Logitech Brio 100: camera-bound at 30 fps (720p MJPG); pose lite ~11 ms/frame
- Recordings ran at **15 fps** (camera-delivered; likely auto-exposure). Check with `sww bench`
- Running detector latency (synthetic, at your real 1.33 Hz cadence): **start ~0.5 s**,
  **stop ~0.55–0.6 s** (up to 0.75 s at 2 Hz / 15 fps). Slower than the 100 ms target by
  design (a rhythm needs about one stride)

## What's broken / known issues
- Idle recording was standing still; natural play movements are untested for false W
- Only one running recording (one person, one pace, the whole 15 s running); stop
  latency on real data not measured yet
- Force-killing the process can leave W "down" in Windows (press W once to clear)
- Body-frame scale uses apparent shoulder width, so turning sideways inflates
  distances (calibration in step 3 fixes this)
- MediaPipe prints harmless startup warnings

## Next actions
1. `uv run sww run --debug`: run in place, stop, play normally; watch the arm-swing and
   bounce graphs; try Ctrl+Alt+P
2. Record a livelier idle (`--label idle`: gesturing, hand on head, reaching for the
   mouse) and a run with standing at both ends, to check false triggers and stop latency
3. `uv run sww bench` in the same lighting as the recordings (15 vs 30 fps)
4. `uv run sww keytest --key w --hold-s 2 --send` into Notepad (expect a single `w`)
5. `uv run sww run --send --window Notepad`, then `--window "World of Warcraft"`
6. Then step 3: YAML config + hot reload, neutral-pose calibration

## Open questions
- Is ~0.5 s stop latency acceptable in WoW, or should we trade some false-stop
  robustness for speed (shorter `recent_ms` / `--forward-off-ms`)?
- Push-to-talk or always-listening for voice?
