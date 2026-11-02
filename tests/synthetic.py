"""Hand-built pose frames for webcam-free tests.

Poses are laid out in *pixels* on a 1280x720 image (origin top-left, y down),
then converted to MediaPipe's normalised coordinates. Proportions are in
shoulder widths (``SW`` px) so we can reason about them in the body frame.
The camera is unmirrored, so the person's LEFT side is on the image's RIGHT.
"""

from __future__ import annotations

import numpy as np

from sww.landmarks import NUM_POSE_LANDMARKS, Pose, PoseFrame

IMAGE_SIZE = (1280, 720)
CX, SHOULDER_Y, SW = 640.0, 360.0, 160.0  # body centre x, shoulder line y, shoulder width
NOSE_Y = SHOULDER_Y - 0.65 * SW  # nose ~0.65 SW above the shoulders


def _neutral_pixels() -> tuple[np.ndarray, np.ndarray]:
    """Standing, arms hanging down. Returns (33x2 pixel coords, 33 visibility)."""
    px = np.zeros((NUM_POSE_LANDMARKS, 2), dtype=np.float32)
    vis = np.full(NUM_POSE_LANDMARKS, 0.99, dtype=np.float32)

    def put(idx: Pose, x: float, y: float) -> None:
        px[idx] = (x, y)

    half = SW / 2
    put(Pose.NOSE, CX, NOSE_Y)
    for idx, dx in ((Pose.LEFT_EYE_INNER, 8), (Pose.LEFT_EYE, 16), (Pose.LEFT_EYE_OUTER, 24)):
        put(idx, CX + dx, NOSE_Y - 12)
    for idx, dx in ((Pose.RIGHT_EYE_INNER, 8), (Pose.RIGHT_EYE, 16), (Pose.RIGHT_EYE_OUTER, 24)):
        put(idx, CX - dx, NOSE_Y - 12)
    put(Pose.LEFT_EAR, CX + 40, NOSE_Y - 5)
    put(Pose.RIGHT_EAR, CX - 40, NOSE_Y - 5)
    put(Pose.MOUTH_LEFT, CX + 12, NOSE_Y + 20)
    put(Pose.MOUTH_RIGHT, CX - 12, NOSE_Y + 20)

    for side, sign in (("LEFT", +1), ("RIGHT", -1)):
        sx = CX + sign * half
        put(Pose[f"{side}_SHOULDER"], sx, SHOULDER_Y)
        put(Pose[f"{side}_ELBOW"], sx + sign * 10, SHOULDER_Y + 0.8 * SW)
        put(Pose[f"{side}_WRIST"], sx + sign * 12, SHOULDER_Y + 1.5 * SW)
        put(Pose[f"{side}_PINKY"], sx + sign * 16, SHOULDER_Y + 1.62 * SW)
        put(Pose[f"{side}_INDEX"], sx + sign * 8, SHOULDER_Y + 1.65 * SW)
        put(Pose[f"{side}_THUMB"], sx + sign * 2, SHOULDER_Y + 1.6 * SW)
        hx = CX + sign * 0.3 * SW
        put(Pose[f"{side}_HIP"], hx, SHOULDER_Y + 1.5 * SW)
        # Legs are below the bottom of a 720p frame, like a top-of-monitor webcam.
        for joint, dy in (("KNEE", 2.5), ("ANKLE", 3.5), ("HEEL", 3.6), ("FOOT_INDEX", 3.65)):
            idx = Pose[f"{side}_{joint}"]
            put(idx, hx, SHOULDER_Y + dy * SW)
            vis[idx] = 0.1
    return px, vis


def _set_arm(px: np.ndarray, side: str, elbow: tuple, wrist: tuple, index: tuple, pinky: tuple):
    px[Pose[f"{side}_ELBOW"]] = elbow
    px[Pose[f"{side}_WRIST"]] = wrist
    px[Pose[f"{side}_INDEX"]] = index
    px[Pose[f"{side}_PINKY"]] = pinky
    px[Pose[f"{side}_THUMB"]] = wrist


def _hand_on_head(px: np.ndarray, side: str) -> None:
    """Elbow out to the side at about ear height, palm resting on the crown."""
    sign = +1 if side == "LEFT" else -1
    _set_arm(
        px,
        side,
        elbow=(CX + sign * 1.0 * SW, SHOULDER_Y - 0.35 * SW),
        wrist=(CX + sign * 0.2 * SW, NOSE_Y - 0.25 * SW),
        index=(CX, NOSE_Y - 0.35 * SW),
        pinky=(CX + sign * 0.1 * SW, NOSE_Y - 0.32 * SW),
    )


def _arm_overhead(px: np.ndarray, side: str) -> None:
    """Straight arm raised above the head."""
    sign = +1 if side == "LEFT" else -1
    sx = CX + sign * SW / 2
    _set_arm(
        px,
        side,
        elbow=(sx - sign * 0.12 * SW, SHOULDER_Y - 0.75 * SW),
        wrist=(sx - sign * 0.2 * SW, SHOULDER_Y - 1.45 * SW),
        index=(sx - sign * 0.22 * SW, SHOULDER_Y - 1.6 * SW),
        pinky=(sx - sign * 0.18 * SW, SHOULDER_Y - 1.58 * SW),
    )


def _hand_on_chin(px: np.ndarray, side: str) -> None:
    """Thinking pose: hand at the chin. Bent elbow, but below the nose."""
    sign = +1 if side == "LEFT" else -1
    _set_arm(
        px,
        side,
        elbow=(CX + sign * 0.5 * SW, SHOULDER_Y + 0.6 * SW),
        wrist=(CX + sign * 0.1 * SW, NOSE_Y + 0.4 * SW),
        index=(CX, NOSE_Y + 0.25 * SW),
        pinky=(CX + sign * 0.05 * SW, NOSE_Y + 0.3 * SW),
    )


_POSES = {"on_head": _hand_on_head, "overhead": _arm_overhead, "chin": _hand_on_chin}


def make_frame(
    timestamp_ms: int = 0,
    left: str | None = None,
    right: str | None = None,
    scale: float = 1.0,
    hidden: tuple[Pose, ...] = (),
    jitter_px: float = 0.0,
    rng: np.random.Generator | None = None,
    wrist_lift: tuple[float, float] = (0.0, 0.0),
    rise: float = 0.0,
) -> PoseFrame:
    """Build a PoseFrame.

    Args:
        left, right: None (arm down) or one of "on_head", "overhead", "chin".
        scale: Shrink/grow the person around the image centre (simulates
            standing further from / closer to the camera).
        hidden: Landmarks to mark as not visible.
        jitter_px: Std-dev of Gaussian noise added to every point, in pixels.
        wrist_lift: (left, right) raise of a hanging hand in shoulder widths
            (negative lowers it).
        rise: Move the whole body up by this many shoulder widths (negative =
            down), e.g. the bounce of running or crouching.
    """
    px, vis = _neutral_pixels()
    if left:
        _POSES[left](px, "LEFT")
    if right:
        _POSES[right](px, "RIGHT")
    for side, lift in (("LEFT", wrist_lift[0]), ("RIGHT", wrist_lift[1])):
        for joint in ("WRIST", "INDEX", "PINKY", "THUMB"):
            px[Pose[f"{side}_{joint}"], 1] -= lift * SW
    px[:, 1] -= rise * SW
    centre = np.array([IMAGE_SIZE[0] / 2, IMAGE_SIZE[1] / 2], dtype=np.float32)
    px = (px - centre) * scale + centre
    if jitter_px:
        rng = rng or np.random.default_rng(0)
        px = px + rng.normal(0.0, jitter_px, px.shape).astype(np.float32)
    for idx in hidden:
        vis[idx] = 0.05
    lms = np.zeros((NUM_POSE_LANDMARKS, 4), dtype=np.float32)
    lms[:, 0] = px[:, 0] / IMAGE_SIZE[0]
    lms[:, 1] = px[:, 1] / IMAGE_SIZE[1]
    lms[:, 3] = vis
    return PoseFrame(timestamp_ms=timestamp_ms, landmarks=lms, image_size=IMAGE_SIZE)


FRAME_MS = 33  # ~30 fps


def motion_stream(
    segments: list[tuple[str | None, int]],
    freq_hz: float = 1.33,
    arm: float = 0.2,
    bounce: float = 0.08,
    jitter_px: float = 0.0,
    seed: int = 0,
    frame_ms: int = FRAME_MS,
    t0: int = 0,
    **frame_kwargs,
):
    """Yield ``(frame, t)`` for a sequence of ``(activity, duration_ms)`` segments.

    Activities:

    - ``"stand"``: still.
    - ``"run"``: running in place. The wrists swing in opposite directions by
      ``arm`` shoulder widths (so left - right swings by 2 * ``arm``) at
      ``freq_hz``, and the whole body bounces by ``bounce`` shoulder widths
      twice per arm cycle (once per step). Defaults match the real recordings.
    - ``"arms"``: the arm swing without the bounce (gesturing, seated pumping).
    - ``"bounce"``: the bounce without the arm swing (bobbing, shifting weight).
    - ``"raise_left"``: left hand raised by 3 * ``arm`` and held.
    - ``"crouch"``: whole body lowered by 3 * ``bounce`` and held.
    - None: no person.
    """
    rng = np.random.default_rng(seed)
    t = t0
    phase_t = 0  # advances only while moving, so each segment continues the rhythm
    for activity, duration in segments:
        end = t + duration
        while t < end:
            if activity is None:
                yield None, t
                t += frame_ms
                continue
            wrists, rise = (0.0, 0.0), 0.0
            if activity in ("run", "arms", "bounce"):
                angle = 2 * np.pi * freq_hz * phase_t / 1000
                if activity != "bounce":
                    wrists = (arm * np.sin(angle), -arm * np.sin(angle))
                if activity != "arms":
                    rise = bounce * np.cos(2 * angle)
                phase_t += frame_ms
            elif activity == "raise_left":
                wrists = (3 * arm, 0.0)
            elif activity == "crouch":
                rise = -3 * bounce
            frame = make_frame(
                t, jitter_px=jitter_px, rng=rng, wrist_lift=wrists, rise=rise, **frame_kwargs
            )
            yield frame, t
            t += frame_ms
