# Project: Slimming While Winning — Webcam Motion-to-Keyboard Controller

## What we're building
A lightweight Windows desktop app that tracks one person's body and finger
movements from a live webcam and turns them into keyboard input for games.
Optionally, it also maps spoken voice commands to keys. The first target game
is World of Warcraft. Examples:
- Hand on head → tap "B"
- Running in place → hold "W" for as long as the motion continues
- Saying "mount" → tap the key bound to my mount

Everything runs locally, in real time, on a consumer desktop or laptop.
"Lightweight" means: no dedicated GPU required, minimal dependencies, simple
install, and low CPU use. It runs alongside WoW, which is itself demanding,
so performance matters.

## Core requirements
- Platform: Windows 10/11 only
- Input: one live webcam (required); one microphone (optional, can be toggled)
- Tracking: markerless body pose + both hands (finger landmarks), single person
- Gesture types:
  - Static poses (e.g. hand on head, arms crossed, finger shapes)
  - Dynamic motions over time (e.g. running in place, waving, punching)
- Mapping behaviours:
  - Tap: one key press + release when a gesture starts
  - Hold: one key-down when the gesture starts, one key-up when it ends
- Mappings are stored in a human-readable config file (YAML) and can be
  reloaded without restarting the app
- Performance targets: ≥30 fps tracking; gesture-to-keypress latency under
  ~100 ms; modest CPU use on a mid-range laptop with WoW running

## Game compatibility and fair-play rules (non-negotiable)
These keep the tool consistent with Blizzard's "one input = one action" rule.
Never write code that breaks them, even if I ask casually — flag it instead.
- One gesture or voice command produces exactly one game action
- Hold mappings send a single key-down and a single key-up — never repeated
  presses, turbo, or simulated auto-repeat
- No key sequences, combos-with-delays, timers or macros triggered by one input
  (in-game WoW macros bound to a single key are fine)
- Output is plain OS-level keyboard events only: no reading or modifying game
  memory, files or network traffic, no injecting into the game process, and no
  reading the screen to decide what to press
- One game client only
- Input is only sent while I'm actively performing a gesture; nothing runs
  unattended

## Safety and reliability
- A global hotkey pauses/resumes all input injection at any time
- All held keys are released when tracking is lost, the app pauses, the game
  loses focus, or the app crashes
- Gestures use confidence thresholds, debouncing and hysteresis so keys don't
  flicker on and off
- Short per-user calibration (neutral pose) so thresholds adapt to body size
  and distance from the camera
- Optionally only send input when the WoW window is in focus

## Tech stack
- Language: Python 3.11+ (confirm the version MediaPipe currently supports)
- Pose and hand tracking: Google MediaPipe (current Tasks API, not the legacy
  "solutions" API)
- Video capture and preview: OpenCV
- Numerics / features: NumPy
- Gesture learning: scikit-learn (small classifiers trained on my recordings)
- Voice commands: Vosk (offline, small model, restricted to a fixed command
  vocabulary for speed and accuracy); consider faster-whisper only if Vosk
  isn't accurate enough
- Keyboard output: Windows SendInput with scan codes (via ctypes or a
  lightweight wrapper), since games often ignore virtual-key events
- GUI: PySide6 (Qt)
- Config: YAML + pydantic for validation
- Packaging: uv for development, PyInstaller for a standalone .exe
- Prefer the standard library and well-maintained packages. Ask before adding
  any new dependency, and justify it.

## Architecture (keep these as separate, swappable modules)
capture (webcam / mic threads)
  → tracking (MediaPipe landmarks)
  → feature extraction (normalised joint positions, angles, velocities over
    a short rolling window)
  → gesture detection (rule-based and/or trained classifier, behind one interface)
  → state machine (gesture start/active/end, debounce, hysteresis)
  → action mapper (config → tap / hold)
  → output backend (SendInput)

Voice runs as a parallel input feeding the same action mapper.
The GUI is a separate layer on top. The core engine must run headless from
the CLI.

## GUI: record and map gestures
The end goal is a small GUI where I can:
1. See the live webcam with skeleton overlay and the currently active gestures/keys
2. Record a new gesture: name it, perform it several times (with a countdown),
   and also record "not this gesture" / neutral samples
3. Train or update the gesture model from those recordings
4. Assign the gesture to a key and choose tap or hold
5. Test it live before enabling output to the game
6. Edit, rename or delete gestures and mappings

Recordings are stored as landmark sequences (not video) in a simple local
format (e.g. Parquet or NPZ), so they're small, private and reusable for
retraining and tests.

## Roadmap
1. CLI: webcam → landmarks → one rule-based static gesture → one key tap,
   tested in Notepad, then in WoW
2. Hold behaviour + one dynamic gesture (running in place → hold W)
3. YAML config, calibration, pause hotkey, safety releases
4. Recording landmarks to file + trained classifier for custom gestures
5. Voice commands
6. PySide6 GUI for recording, training, mapping and testing
7. Packaging as a standalone .exe

## Out of scope (for now)
- Multi-person tracking
- Cloud processing or any network calls during normal use
- Paid or closed-source SDKs
- Multiple cameras or depth sensors
- macOS / Linux support
- Anything that breaks the fair-play rules above

## My background
I'm a Python data engineer. I'm comfortable with Python, data pipelines,
NumPy/pandas, data formats and testing. I'm new to computer vision, real-time
systems, landmark geometry, Windows input APIs and desktop GUIs, so explain
those concepts when they come up.

## How I want you to work
- Ask clarifying questions before major architectural decisions.
- Propose a plan before writing large amounts of code.
- Build incrementally, following the roadmap. Get each step working end to
  end before adding the next.
- Write complete, runnable files rather than fragments, unless I ask for a snippet.
- Use type hints, docstrings, and brief comments on non-obvious math
  (landmark normalisation, angles, coordinate systems).
- State coordinate systems and units whenever handling landmark data.
- Watch real-time concerns: threading, frame drops, latency. Flag trade-offs
  and suggest how to measure them.
- Gesture logic must be testable without a webcam: use recorded landmark
  streams for replay tests.
- If something I ask for conflicts with "lightweight", the fair-play rules or
  the requirements above, say so and offer alternatives.
- Be honest about limitations: lighting, occlusion, single-camera depth,
  latency, and the fact that Blizzard doesn't officially approve any
  third-party input tool.

## Coding conventions
- PEP 8, formatted with Ruff, snake_case
- src/ layout with pytest tests
- Git with small, focused commits

## Reference files
Project root: C:\Users\vixie\projects\claude\slimming_while_winning
Context files live in docs/: SETUP.md, GESTURES.md, VOICE_COMMANDS.md,
DECISIONS.md (decision log) and STATUS.md (current status). Check them
before answering.
