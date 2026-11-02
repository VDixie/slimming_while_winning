# Decision Log

Dated record of decisions and *why*. Add new entries at the top. Change a
decision by adding a new entry that supersedes the old one, rather than
editing history.

Format: **Decision** — Why — Alternatives considered

---

## 2026-11-02 — Initial project planning

### Scope
- **Windows 10/11 only.** — Simplest, most reliable path for simulated game
  input. — macOS needs Accessibility permissions; Linux/Wayland restricts input
  injection.
- **World of Warcraft is the first target game.** — Personal use case.
- **Single person, single webcam, local processing only.** — Keeps it
  lightweight and private. — Multi-person, multi-camera, depth sensors and
  cloud processing are out of scope.
- **No paid or closed-source SDKs.**

### Fair play
- **Strict "one input = one action" rule.** — Blizzard treats repeats, delays
  and multi-action inputs from third-party software as automation. — Hold
  mappings send exactly one key-down and one key-up; no turbo, sequences,
  macros, memory/screen reading or process injection.
- **Accepted risk:** Blizzard doesn't officially approve any third-party input
  tool, though comparable tools (e.g. VoiceAttack) have long been used.

### Language and libraries
- **Python 3.11+.** — My strongest language; heavy CV work runs in MediaPipe's
  optimised C++. — C++/Rust: faster, but slower to build and unnecessary at
  webcam frame rates.
- **MediaPipe (Tasks API) for pose + hand landmarks.** — Free, CPU-friendly,
  good accuracy, covers body and fingers. — OpenPose (heavier, licensing),
  legacy MediaPipe "solutions" API (deprecated).
- **OpenCV for capture and preview.** — Standard, well supported.
- **Windows SendInput with scan codes for keyboard output.** — Games often
  ignore virtual-key events. — pynput alone (may not register in some games).
- **Vosk for voice commands.** — Offline, small, supports a restricted
  vocabulary for speed and accuracy. — faster-whisper kept as a fallback if
  accuracy is poor.
- **PySide6 for the GUI.** — Mature Qt bindings, LGPL, good with live video.
  — Tkinter (dated), Dear PyGui, web UI.
- **YAML + pydantic for config.** — Human-editable and validated.
- **scikit-learn for trained gesture classifiers.** — Small, fast, familiar.
  — Deep learning models: overkill for now.

### Design
- **Modular pipeline:** capture → tracking → features → detection → state
  machine → action mapper → output. Voice feeds the same action mapper. Core
  engine runs headless; GUI sits on top.
- **Rule-based gestures first, trained classifiers next, behind one interface.**
  — Rules are quick for simple static poses; trained models handle dynamic
  motions like running better.
- **Record landmark sequences, not video (Parquet/NPZ).** — Small, private,
  reusable for retraining and replay tests.
- **Safety:** global pause hotkey; release all held keys on tracking loss,
  pause, focus loss or crash; debounce + hysteresis; per-user calibration.

### Tooling
- **uv** for environments, **Ruff** for lint/format, **pytest**, **src/ layout**,
  **Git** with small commits, **PyInstaller** for the .exe.
