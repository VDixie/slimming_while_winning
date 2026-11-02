# Project Status

> Update at the end of each work session. Keep it short — this is a snapshot,
> not a history (history goes in DECISIONS.md, docs/sessions/ and Git).

**Last updated:** 2026-11-02
**Current roadmap step:** 1 — Live dry run works at ~30 fps; Notepad/WoW key tests pending

## Roadmap
| Step | Description | Status |
|---|---|---|
| 0 | Project instructions, context files, initial decisions | ✅ Done |
| 1 | CLI: webcam → landmarks → one rule-based static gesture → one key tap (test in Notepad, then WoW) | 🟡 Dry run verified live; `--send` into Notepad/WoW pending |
| 2 | Hold behaviour + one dynamic gesture (running in place → hold W) | ⬜ |
| 3 | YAML config, calibration, pause hotkey, safety releases | ⬜ |
| 4 | Landmark recording to file + trained classifier for custom gestures | ⬜ |
| 5 | Voice commands (Vosk) | ⬜ |
| 6 | PySide6 GUI: record, train, map, test | ⬜ |
| 7 | Package as standalone .exe | ⬜ |

## What works
- Repo scaffold: uv project (Python 3.14, MediaPipe 1.2.0), src/ layout, Ruff, pytest
- `sww run`: webcam thread → MediaPipe PoseLandmarker (lite) → body-frame features →
  "hand on head" rule → hysteresis/debounce → tap B. Dry run by default; `--send`,
  `--window` focus gate, live preview with `--debug` tuning values, perf stats.
  **Verified live (dry run):** skeleton, score and one tap per placement; ~30 fps
- `sww bench`: times camera modes and the pose model separately
- `sww keytest`: SendInput scan-code tap on its own (for the Notepad check)
- `sww download-models`: one-time model download (lite downloaded)
- 73 webcam-free tests pass (synthetic landmark streams, fake camera/tracker smoke test)

## Performance (Ryzen 9 5900X, Logitech Brio 100)
- Camera: 30 fps at 1280x720 MJPG (DirectShow default); 5 fps if it falls back to
  uncompressed YUY2 at 720p
- Pose lite: ~11 ms/frame (p95 ~12 ms) → model ceiling ~89 fps
- So the pipeline is camera-bound at 30 fps, with lots of CPU headroom

## What's broken / known issues
- SendInput (`--send`) not yet confirmed on real Windows / Notepad / WoW
- Hand-on-head thresholds are educated guesses; tune with `--debug` if it misfires
- Body-frame scale uses apparent shoulder width, so turning sideways inflates
  distances (calibration in step 3 fixes this)
- MediaPipe prints harmless startup warnings (`NORM_RECT without IMAGE_DIMENSIONS`,
  feedback-tensor notices)

## Next actions
1. `uv run sww keytest --key b --send` into Notepad (one `b` should appear)
2. `uv run sww run --send --window Notepad`, then `--window "World of Warcraft"`
3. Check whether knees are visible in the preview (decides gesture #2 vs #3)
4. Commit (docs; scaffold + step 1; camera fix + bench), then start step 2

## Open questions
- Are the knees visible in the webcam frame while standing at ~1.5 m?
  (decides whether "running in place" or "pumping arms" is the forward gesture)
- Push-to-talk or always-listening for voice?
