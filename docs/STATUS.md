# Project Status

> Update at the end of each work session. Keep it short — this is a snapshot,
> not a history (history goes in DECISIONS.md and Git).

**Last updated:** 2026-11-02
**Current roadmap step:** 0 — Planning complete, ready to start step 1

## Roadmap
| Step | Description | Status |
|---|---|---|
| 0 | Project instructions, context files, initial decisions | ✅ Done |
| 1 | CLI: webcam → landmarks → one rule-based static gesture → one key tap (test in Notepad, then WoW) | ⬜ Next |
| 2 | Hold behaviour + one dynamic gesture (running in place → hold W) | ⬜ |
| 3 | YAML config, calibration, pause hotkey, safety releases | ⬜ |
| 4 | Landmark recording to file + trained classifier for custom gestures | ⬜ |
| 5 | Voice commands (Vosk) | ⬜ |
| 6 | PySide6 GUI: record, train, map, test | ⬜ |
| 7 | Package as standalone .exe | ⬜ |

## What works
- Nothing yet — no code written.

## What's broken / known issues
- None yet.

## Next actions
1. Fill in SETUP.md (hardware, play space, dev environment)
2. Confirm or edit the priority-1 rows in GESTURES.md
3. Set up repo: uv project, src/ layout, Ruff, pytest, Git
4. Start roadmap step 1 in a new chat

## Open questions
- Seated or standing while playing? (affects which gestures are feasible)
- Measured webcam fps in normal play lighting?
- Push-to-talk or always-listening for voice?
