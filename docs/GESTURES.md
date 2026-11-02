# Gesture Wishlist

The single source of truth for what the app should recognise and which key it
sends. Rows marked **(suggested)** are ideas to confirm, edit or delete.

## Rules for every mapping
- One gesture → exactly one game action (Blizzard's "one input = one action")
- **Tap** = one press + release when the gesture starts
- **Hold** = one key-down when the gesture starts, one key-up when it ends
  (never repeated presses)
- Prefer movement, utility and menu actions. Fast combat rotations need more
  speed and precision than a webcam reliably gives.

## Legend
- **Type:** Static (a pose held still) or Dynamic (a motion over time)
- **Body part:** Body, Left hand, Right hand, Both hands
- **Priority:** 1 = build first, 2 = next, 3 = nice to have
- **Seated OK?:** can it be done while sitting?

## Gesture → key mappings
| # | Gesture (how I perform it) | Type | Body part | WoW action | Key | Mode | Priority | Seated OK? | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Hand on top of head | Static | Either hand | Open all bags | B | Tap | 1 | Yes | Working (Notepad + WoW) |
| 2 | Running in place (knees alternating up/down) | Dynamic | Body | Move forward | W | Hold | 1 | No (see #3) | Built, but knees are out of frame: needs camera reframing |
| 3 | Pumping arms as if running | Dynamic | Both hands | Move forward (also natural arm swing while running in place) | W | Hold | 1 | Yes | Tuned on recordings (`--forward arms`); live test pending |
| 4 | (suggested) Lean torso left | Static | Body | Strafe left | Q | Hold | 2 | Yes | Idea |
| 5 | (suggested) Lean torso right | Static | Body | Strafe right | E | Hold | 2 | Yes | Idea |
| 6 | (suggested) Both arms raised overhead | Static | Both hands | Jump | Space | Tap | 2 | Yes | Idea |
| 7 | (suggested) Point forward with index finger | Static | Right hand | Target nearest enemy | Tab | Tap | 3 | Yes | Idea |
| 8 | (suggested) Open palm facing camera ("stop") | Static | Either hand | Stop moving / release movement holds | — | — | 2 | Yes | Idea |
| 9 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| 10 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

> Keys above are WoW defaults (W forward, Q/E strafe, Space jump, B bags,
> Tab target). Change them to match your own keybinds.

## App-control gestures (do not send game keys)
| Gesture | App action | Notes |
|---|---|---|
| (keyboard) Ctrl+Alt+P, global | Pause / resume input; releases held keys | Built. Change with `--pause-hotkey` |
| [e.g. both hands crossed in an X] | Pause / resume input | Keyboard hotkey remains the main kill switch |

## Camera framing
- "Running in place" (#2) is detected from the knees. The 2026-11-02 recordings
  show the knees are **below the image** at the current play position (the hips
  sit at the bottom edge). The preview's skeleton lines running off the bottom
  can look like visible legs, but they're MediaPipe's guesses. To use #2: tilt
  the camera down or step back until the knee dots are inside the picture.
  Meanwhile `--forward arms` (#3) works, because you swing your arms when you
  run in place.

## Conflicts to watch
- Gestures that look alike to the camera (e.g. #1 vs #6 mid-motion) need
  distinct enough features or a short hold time before triggering.
- Natural movements while playing (scratching head, reaching for a drink)
  can cause false triggers. Note any you notice here:
  - [ ]

## My WoW setup
| Item | Value |
|---|---|
| Version | [Retail / Classic / Classic Era] |
| Class / spec | [ ] |
| Custom keybinds that matter | [e.g. mount on Shift+M] |
