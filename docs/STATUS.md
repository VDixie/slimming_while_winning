# Project Status

> Update at the end of each work session. Keep it short — this is a snapshot,
> not a history (history goes in DECISIONS.md, docs/sessions/ and Git).

**Last updated:** 2026-11-02
**Current roadmap step:** 2 — Built and tested on synthetic data; live tests and tuning pending

## Roadmap
| Step | Description | Status |
|---|---|---|
| 0 | Project instructions, context files, initial decisions | ✅ Done |
| 1 | CLI: webcam → landmarks → one rule-based static gesture → one key tap (test in Notepad, then WoW) | ✅ Done (verified in Notepad and WoW) |
| 2 | Hold behaviour + one dynamic gesture (running in place → hold W) | 🟡 Built; live dry run, Notepad and WoW tests pending |
| 3 | YAML config, calibration, ~~pause hotkey, safety releases~~ (moved to step 2) | ⬜ |
| 4 | Landmark recording to file + trained classifier for custom gestures | ⬜ (recording done early, in step 2) |
| 5 | Voice commands (Vosk) | ⬜ |
| 6 | PySide6 GUI: record, train, map, test | ⬜ |
| 7 | Package as standalone .exe | ⬜ |

## What works
- Step 1: hand on head → tap B, verified with `--send` in Notepad and WoW
- Step 2 (synthetic tests only so far):
  - **Hold mode**: one key-down on gesture start, one key-up on end; never a second key-down
  - **Running in place → hold W** (`AlternatingMotion` on the knees); `--forward arms`
    uses the wrists (pumping arms, seated)
  - **Global pause hotkey** Ctrl+Alt+P (`RegisterHotKey` on its own thread), also `p`
    in the preview
  - **Safety releases**: gesture end, pause, focus loss (checked every frame), person
    lost for 150 ms, camera stall, exit/exception/Ctrl+C, console window closed.
    Re-arm rule: no automatic re-press after a safety release
  - `sww record` (landmarks → .npz) and `sww replay` (same engine, dry run, CSV export)
  - `sww keytest --hold-s N` to test a single injected hold
  - `--debug` rolling graphs of score and knee signal
- 118 webcam-free tests pass; Ruff clean

## Performance
- Ryzen 9 5900X, Logitech Brio 100: camera-bound at 30 fps (720p MJPG); pose lite ~11 ms/frame
- Running detector latency on synthetic data: **start 280–510 ms** after the first
  stride (faster at higher cadence), **stop ~500–570 ms** after you stop. Slower than
  the 100 ms target by design (a rhythm needs about one stride); tune on real recordings

## What's broken / known issues
- Running thresholds are educated guesses until tuned on real recordings
- Force-killing the process can leave W "down" in Windows (press W once to clear)
- Body-frame scale uses apparent shoulder width, so turning sideways inflates
  distances (calibration in step 3 fixes this)
- MediaPipe prints harmless startup warnings

## Next actions
1. `uv run sww run --debug`: run in place; check one DOWN/UP per run, no triggers
   when standing, shifting weight or lifting one knee; try Ctrl+Alt+P
2. `uv run sww record --label running` and `--label idle`; `sww replay ... --csv`; tune
3. `uv run sww keytest --key w --hold-s 2 --send` into Notepad (expect a single `w`)
4. `uv run sww run --send --window Notepad`, then `--window "World of Warcraft"`
5. Then step 3: YAML config + hot reload, neutral-pose calibration

## Open questions
- Is ~0.5 s stop latency acceptable in WoW, or should we trade some false-stop
  robustness for speed (shorter `recent_ms` / `--forward-off-ms`)?
- Push-to-talk or always-listening for voice?
