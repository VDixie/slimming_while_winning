# Decision Log

Dated record of decisions and *why*. Add new entries at the top. Change a
decision by adding a new entry that supersedes the old one, rather than
editing history.

Format: **Decision** — Why — Alternatives considered

---

## 2026-11-02 — Camera frame-rate fix

- **Request MJPG both before and after setting the frame size.** — First live run
  got 4.9 fps. `sww bench` showed the pose model takes ~11 ms (not the bottleneck)
  and that 720p uncompressed YUY2 is capped at 5 fps on this camera; the driver had
  ignored the MJPG request when it was sent only before the size. Sending it both
  times gives 30 fps. — Giving the model more threads/GPU (wouldn't help: the
  camera was the limit; MediaPipe's Python GPU delegate isn't available on Windows).
- **Keep DirectShow as the default backend.** — Same 30 fps as Media Foundation in
  the benchmark (30.2 vs 29.9 is noise), and DirectShow reports the negotiated
  format, so a silent fallback to YUY2 is visible at startup. `--api msmf` stays
  available.
- **Added `sww bench`** to measure camera and model separately before tuning
  anything. Rule: the loop can't beat min(camera fps, 1000 / tracking ms).

## 2026-11-02 — Roadmap step 1 implementation

- **Python 3.14 + MediaPipe 1.2.0.** — MediaPipe 1.x (Jul–Oct 2026) ships a
  Python-version-independent wheel (py3-none-win_amd64) and lists 3.9–3.14; the
  full planned stack (PySide6, Vosk, scikit-learn, PyInstaller, pyarrow, pydantic)
  resolves to binary wheels on Windows 3.14. The legacy `mp.solutions` API is gone in
  1.x; the Tasks API is unchanged from 0.10.x. — Pinning 3.12 (unnecessary).
- **uv instead of pip** for the dev environment (as planned); SETUP.md updated.
- **opencv-contrib-python, not opencv-python.** — MediaPipe depends on the contrib
  build; installing both gives two conflicting `cv2` packages.
- **Pose only for step 1 (no HandLandmarker).** — "Hand on head" only needs pose
  wrist/knuckle points; skipping the hand model halves inference cost. Hands come back
  with finger gestures.
- **`pose_landmarker_lite` by default.** — Lowest CPU; `--model full/heavy` available.
- **MediaPipe VIDEO mode + capture thread keeping only the newest frame.** — VIDEO mode
  tracks between frames (faster, steadier); newest-frame-only drops frames instead of
  adding latency. — LIVE_STREAM async mode (more moving parts for no gain yet).
- **Body frame for features:** origin mid-shoulders, y up, unit = shoulder width,
  computed in pixels to avoid 16:9 aspect distortion. — Raw normalised coords
  (distance- and aspect-dependent).
- **Detectors output a 0..1 score; the state machine applies hysteresis (enter 0.6 /
  exit 0.4) and time-based debounce (on 50 ms, off 150 ms).** — Same interface will fit
  classifier probabilities in step 4. Rule conditions are linear ramps combined with
  min() (fuzzy AND) so scores are smooth.
- **Hand-on-head rule:** hand above nose, not far overhead, horizontally near the head,
  elbow bent (< ~100–135°). The elbow-angle term separates it from "arms raised".
- **Safe defaults:** dry run unless `--send`; optional `--window` focus gate (reads only
  the foreground window title). Taps hold the key 15 ms (`--tap-ms`) because some games
  miss zero-length taps; still exactly one press + one release.
- **Tap only in step 1;** hold arrives in step 2 with its safety releases.

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
