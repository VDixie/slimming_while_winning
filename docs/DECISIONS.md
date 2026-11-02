# Decision Log

Dated record of decisions and *why*. Add new entries at the top. Change a
decision by adding a new entry that supersedes the old one, rather than
editing history.

Format: **Decision** — Why — Alternatives considered

---

## 2026-11-02 — Running = arm swing AND body bounce; knees removed

- **Knees removed as an input** (out of frame at the play position; see below).
  `--forward knees` is gone; `--forward run` is the default, `--forward arms` stays
  for seated play.
- **Running in place = min(arm swing score, body bounce score).** Neither alone is
  enough: arms without bounce = gesturing or seated pumping; bounce without arms =
  bobbing, shifting weight, laughing. Same rule for both signals (moves both ways
  around a 3 s median baseline within 1 s, and still moving in the last 450 ms), so
  the old `AlternatingMotion` became a generic `oscillation()` over any per-frame
  signal (`gestures/oscillation.py`), and running lives in `gestures/running.py`.
  — Checking that bounce runs at twice the arm frequency: an even stronger running
  signature, but needs frequency estimation on 1 s of 15 fps data; kept for later if
  false triggers appear.
- **Bounce signal = shoulder midpoint height**, compared with hips and nose on the
  recordings: shoulders separate best (running swing p1 0.048 vs idle max 0.007,
  range p1 0.094 vs 0.019). Hips sit at the image edge and are noisier; the nose
  also moves when nodding.
- **No median filter for bounce.** At ~2.6 Hz and 15 fps a bounce cycle is ~6 samples
  and the filter clips the peaks (swing p1 0.048 → 0.039).
- **Bounce is measured in pixels and scaled by the median shoulder width over the
  window**, not frame by frame. Found by the "arms only must not trigger" test:
  dividing each frame by its own shoulder width turns ~1% width jitter into fake
  bounce, multiplied by the shoulders' distance from the image top in shoulder
  widths (~0.5 in the recordings, but 2.25 in the synthetic frames, and larger if
  you stand further back). Real-data margins unchanged after the fix.
- **Bounce thresholds:** swing 0.015–0.035, range 0.035–0.07 shoulder widths. On the
  running recording the bounce term stays ≥ 0.99 throughout; idle stays at 0.

## 2026-11-02 — Tuning on the first real recordings

Data: `recordings/running_20261102-141337` and `idle_20261102-141424` (15 s each, 15 fps).
- **The knees are not in the camera image** (normalised y ≈ 1.3; the hips are at the bottom
  edge, y ≈ 0.85). This supersedes "knees are visible" below. MediaPipe guessed their
  positions, with visibility 0.6–0.7 when standing. Guessed knees carry no running signal
  (1 s peak-to-peak 0.09 running vs 0.10 idle).
- **Landmarks outside the image now count as not visible** (`features.OFF_IMAGE_MARGIN`),
  whatever MediaPipe's visibility says. — Raising the visibility cutoff: would also
  reject real but partly occluded points, and 0.7 guesses would still pass.
- **Natural arm swing is a strong running signal:** wrist difference peak-to-peak 0.85
  running vs 0.06 idle, alternating at 1.33 Hz (stride rate). Body bounce is also clear
  (0.23 vs 0.01 at 2.6 Hz, one bounce per step); kept in reserve, not implemented.
- **`PUMPING_ARMS` retuned from a parameter sweep:** swing 0.08–0.18, range 0.15–0.35,
  picked from the middle of the region that gives exactly one key-down on the running
  recording and a zero score on idle. Before: swing 0.20–0.40 / range 0.30–0.60 gave
  6 starts (flicker).
- **`recent_ms` 350 → 450 ms (both presets).** At a real 1.33 Hz cadence a 350 ms window
  can sit inside one half-swing, so the range term dropped at every turning point.
  450 ms covers down to ~1.1 Hz. Cost: ~50–100 ms more stop latency (now ~0.55–0.75 s).
- **Recordings ran at 15 fps** (very regular 64 ms frames, so the camera was delivering
  15 fps, not processing falling behind), versus 30 fps in earlier live runs. Likely the
  camera's auto-exposure in lower light; to be checked with `sww bench`. The detector is
  now tested at 15 fps.
- **`tests/test_real_recordings.py`** replays any local recordings labelled `running` /
  `idle`; skipped when there are none, so private data stays out of git.

## 2026-11-02 — Roadmap step 2 implementation

- **Knees are visible, so running in place (#2) is the forward gesture.** One
  `AlternatingMotion` detector covers both #2 (knees) and #3 (wrists, `--forward arms`).
- **Signal = left.y − right.y in the body frame.** It's a difference of two points, so
  it ignores the whole body bobbing while running. 3-sample median filter against
  single-frame glitches.
- **Score = min(swing, recent range).** Swing: *both* sides rose above a 3 s median
  baseline within the last 1 s (rejects a single knee lift or a weight shift, and
  adapts to stance and camera angle). Recent range: peak-to-peak over the last
  350 ms (makes the gesture end quickly when you stop). — Frequency analysis (FFT):
  needs longer windows (more latency) and is harder to tune by eye. Velocity energy:
  expected to be noisy, since differentiating amplifies landmark jitter (not measured).
- **Accepted latency: ~0.3–0.5 s to start, ~0.5 s to stop** (synthetic). A rhythm
  can't be recognised from one frame. Off-debounce 200 ms bridges the top of each stride.
- **Detectors now receive a `FeatureWindow`** (time-bounded, 3 s, `None` for frames
  without a person) instead of one frame. Static detectors use `window.latest`. The
  same window will feed the step 4 classifiers. Detectors stay stateless, which keeps
  replay deterministic.
- **Safety releases and the pause hotkey moved from step 3 into step 2.** Holding W
  without them is unsafe. Releases: gesture end, pause, focus loss (gate checked every
  frame while holding), no person for 150 ms (independent of each gesture's
  off-debounce), camera stall, exit/exception/Ctrl+C (`finally`), console window
  closed (`SetConsoleCtrlHandler`). A hard kill can't be covered; documented.
- **Re-arm rule:** after a safety release (focus loss, pause), the key is not pressed
  again when focus or output returns. Only a new gesture START presses it. Keeps
  "one input = one action": every key-down follows a deliberate gesture.
- **Pause hotkey: `RegisterHotKey` on a dedicated message-loop thread, default
  Ctrl+Alt+P.** The game never sees the combination. The callback releases keys right
  away (thread-safe mapper with an `RLock`), so pause works even if the camera loop
  stalls. `--send` refuses to run without it. — Low-level keyboard hook
  (`SetWindowsHookEx`): heavier (a callback on every keystroke system-wide) for no gain.
  Polling `GetAsyncKeyState`: misses short presses at 30 fps.
- **Two hold mappings may not share a key** (one ending would release the other's).
- **Landmark recording moved forward from step 4** (`sww record` / `sww replay`):
  NumPy `.npz` (no new dependency), NaN rows for frames without a person, JSON
  metadata. Replay uses the exact engine built for `run`. — Parquet: needs pyarrow;
  can be added in step 4 if recordings grow.

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
