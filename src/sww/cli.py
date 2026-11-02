"""Command-line entry point.

Commands:
    sww download-models   Fetch the MediaPipe pose model(s) (one-time, needs internet).
    sww keytest           Send one key after a countdown, to check SendInput reaches an app.
    sww run               Webcam → pose → gestures → keys (hand on head → tap B,
                          running in place (arm swing + body bounce) → hold W).
    sww record            Save pose landmarks from the webcam to a .npz file, then
                          replay it into a per-frame .csv next to it.
    sww replay            Run the gesture engine on a recording (nothing is sent).
    sww bench             Measure camera fps and model speed separately.

Safety defaults: ``run`` and ``keytest`` are dry runs (nothing is sent) unless
you pass ``--send``. While ``run`` is going, the pause hotkey (default
Ctrl+Alt+P) releases every held key and blocks output until pressed again.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from sww.output.base import KeyboardBackend, RecordingBackend
from sww.output.hotkey import DEFAULT_PAUSE_HOTKEY, parse_hotkey
from sww.output.keys import key_to_vk, known_keys

if TYPE_CHECKING:
    from sww.actions import ActionRecord
    from sww.engine import Engine

WINDOW_NAME = "sww - preview"


def _make_backend(send: bool, tap_ms: int) -> KeyboardBackend:
    if not send:
        return RecordingBackend()
    from sww.output.sendinput import SendInputBackend

    return SendInputBackend(tap_ms=tap_ms)


def _check_key(key: str) -> str:
    try:
        key_to_vk(key)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"unknown key {key!r}. Known keys: {', '.join(known_keys())}"
        ) from None
    return key


def _check_hotkey(spec: str) -> str:
    try:
        parse_hotkey(spec)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"bad hotkey {spec!r}: {e}") from None
    return spec


def build_engine(
    args: argparse.Namespace, backend: KeyboardBackend, gate=None
) -> tuple[Engine, list[str]]:
    """Build the gesture engine from the gesture options. Returns (engine, descriptions).

    Shared by ``run`` and ``replay`` so a replay behaves exactly like a live run.
    """
    from sww.actions import ActionMapper, Mapping, Mode
    from sww.engine import Engine
    from sww.gestures import HandOnHead, RunningInPlace, pumping_arms
    from sww.state import DebounceConfig

    head = HandOnHead()
    detectors = [head]
    mappings = [Mapping(head.name, args.head_key, Mode.TAP)]
    debounce = {head.name: DebounceConfig(min_on_ms=args.min_on_ms)}
    described = [f"hand on head -> tap '{args.head_key}'"]

    if args.forward != "off":
        if args.forward == "run":
            forward, label = RunningInPlace(), "running in place (arm swing + body bounce)"
        else:
            forward, label = pumping_arms(), "pumping arms, seated (arm swing only)"
        name = forward.name
        detectors.append(forward)
        mappings.append(Mapping(name, args.forward_key, Mode.HOLD))
        # Off-debounce bridges the short pause at the top of each stride.
        debounce[name] = DebounceConfig(min_on_ms=50, min_off_ms=args.forward_off_ms)
        described.append(f"{label} -> hold '{args.forward_key}'")

    engine = Engine(detectors, ActionMapper(mappings, backend, gate), debounce)
    return engine, described


def _log_actions(records: Iterable[ActionRecord], send: bool, t0_ms: int = 0) -> str:
    """Print one line per action; return the last message (for the preview banner)."""
    from sww.actions import ActionKind

    last = ""
    for rec in records:
        msg = rec.describe()
        if not send and rec.action is not ActionKind.BLOCKED:
            msg = f"[dry run] {msg}"
        print(f"{(rec.timestamp_ms - t0_ms) / 1000:10.3f}s  {rec.gesture} -> {msg}", flush=True)
        last = msg
    return last


def _window_closed() -> bool:
    import cv2

    try:
        return cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


# --------------------------------------------------------------------------- commands


def cmd_download_models(args: argparse.Namespace) -> int:
    from sww.models import download_pose_model

    for variant in args.variant:
        print(f"Downloading pose model '{variant}' ...", flush=True)
        path = download_pose_model(variant, Path(args.models_dir), force=args.force)
        print(f"  -> {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return 0


def cmd_keytest(args: argparse.Namespace) -> int:
    backend = _make_backend(args.send, args.tap_ms)
    mode = "SENDING" if args.send else "DRY RUN (add --send to really press the key)"
    action = f"hold '{args.key}' for {args.hold_s} s" if args.hold_s else f"tap '{args.key}'"
    print(f"{mode}: will {action} in {args.delay} s. Switch to the target window now.")
    for remaining in range(args.delay, 0, -1):
        print(f"  {remaining}...", flush=True)
        time.sleep(1)
    if not args.hold_s:
        backend.tap(args.key)
        print(f"Tapped '{args.key}'." if args.send else f"Would have tapped '{args.key}'.")
        return 0
    # Hold: exactly one key-down and one key-up, like a hold gesture.
    backend.key_down(args.key)
    try:
        time.sleep(args.hold_s)
    finally:
        backend.key_up(args.key)
    done = "Held" if args.send else "Would have held"
    print(f"{done} '{args.key}' for {args.hold_s} s (one key-down, one key-up).")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    # Heavy imports here so `sww --help` and `keytest` start instantly.
    import cv2

    from sww.capture import LatestFrameCamera, now_ms
    from sww.models import pose_model_path
    from sww.output.focus import window_title_gate
    from sww.output.hotkey import GlobalHotkey
    from sww.output.safety import install_console_close_handler
    from sww.preview import History, draw_banner, render
    from sww.timing import PerfStats
    from sww.tracking import PoseTracker

    if args.send and args.no_pause_hotkey:
        print("Refusing --send without the pause hotkey (it's the kill switch).", file=sys.stderr)
        return 2

    backend = _make_backend(args.send, args.tap_ms)
    gate = window_title_gate(args.window) if args.window else None
    engine, described = build_engine(args, backend, gate)
    mapper = engine.mapper
    stats = PerfStats()
    history = History()
    model = pose_model_path(args.model, Path(args.models_dir))

    send_desc = "SENDING keys" if args.send else "DRY RUN (no keys sent; add --send)"
    target = (
        f"only while a window titled '*{args.window}*' is focused"
        if args.window
        else "to any focused window"
    )
    print(f"{send_desc} {target}.")
    for line in described:
        print(f"  {line}")
    if not args.no_pause_hotkey:
        print(f"Pause/resume: {args.pause_hotkey} (anywhere), or p in the preview.")
    print("Quit: q or Esc in the preview window, or Ctrl+C here.")

    def toggle_pause() -> None:
        # Runs on the hotkey thread; the mapper is thread-safe and releases at once.
        _log_actions(mapper.toggle_pause(now_ms()), args.send)
        print("PAUSED: all keys released" if mapper.paused else "RESUMED", flush=True)

    if args.start_paused:
        mapper.set_paused(True)
        print("Starting PAUSED.")

    last_banner = ""
    last_banner_ms = 0
    last_stats_ms = now_ms()
    no_frame_since: int | None = None

    uninstall_close_handler = install_console_close_handler(
        lambda: engine.shutdown("console closed", now_ms())
    )
    try:
        with contextlib.ExitStack() as stack:
            if not args.no_pause_hotkey:
                try:
                    stack.enter_context(GlobalHotkey(args.pause_hotkey, toggle_pause))
                except OSError as e:
                    print(f"{e}. Choose another with --pause-hotkey.", file=sys.stderr)
                    return 2
            tracker = stack.enter_context(PoseTracker(model))
            camera = stack.enter_context(
                LatestFrameCamera(
                    args.camera,
                    args.width,
                    args.height,
                    args.fps,
                    api=args.api,
                    mjpg=not args.no_mjpg,
                )
            )
            w, h = camera.actual_size
            print(
                f"Camera {args.camera} via {args.api}: {w}x{h} {camera.actual_fourcc} "
                f"@ {camera.actual_fps:.0f} fps (driver-reported)"
            )
            seq = 0
            shown = False
            while True:
                captured = camera.read_latest(after_seq=seq, timeout_s=0.5)
                if captured is None:
                    # Camera stalled: no gesture can end, so let go of held keys now.
                    released = engine.shutdown("no camera frames", now_ms())
                    _log_actions(released, args.send)
                    if no_frame_since is None:
                        no_frame_since = now_ms()
                        print("No camera frames; is it in use by another app?", file=sys.stderr)
                    continue
                no_frame_since = None
                seq = captured.seq
                start = now_ms()
                pose = tracker.process(captured.image, captured.timestamp_ms)
                tracked = now_ms()
                step = engine.step(pose, captured.timestamp_ms)
                done = now_ms()
                stats.add(captured.timestamp_ms, start, tracked, done)
                history.update(step)

                msg = _log_actions(step.actions, args.send)
                if msg:
                    last_banner, last_banner_ms = msg, done

                if done - last_stats_ms >= args.stats_every * 1000:
                    summary = stats.summary()
                    if summary:
                        print(f"[perf] {summary}", flush=True)
                    last_stats_ms = done

                if args.no_preview:
                    continue
                summary = stats.summary()
                held = mapper.held_keys
                status = [
                    send_desc,
                    "PAUSED" if mapper.paused else ("no person" if pose is None else "tracking"),
                    f"holding: {', '.join(k.upper() for k in held)}" if held else "",
                    str(summary) if summary else "",
                ]
                img = render(
                    captured.image,
                    pose,
                    step,
                    [s for s in status if s],
                    mirror=not args.no_mirror,
                    debug=args.debug,
                    history=history,
                )
                if last_banner and done - last_banner_ms < 1500:
                    draw_banner(img, last_banner)
                cv2.imshow(WINDOW_NAME, img)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("p"):
                    toggle_pause()
                if shown and _window_closed():
                    break  # closed with the X button
                shown = True
    except KeyboardInterrupt:
        pass
    finally:
        # Every exit path, including exceptions, ends with all keys up.
        _log_actions(engine.shutdown("exit", now_ms()), args.send)
        uninstall_close_handler()
        if not args.no_preview:
            cv2.destroyAllWindows()
    final = stats.summary()
    if final:
        print(f"[perf, last {len(stats)} frames] {final}")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    import cv2

    from sww.capture import LatestFrameCamera, now_ms
    from sww.models import pose_model_path
    from sww.preview import draw_banner, draw_skeleton
    from sww.recording import Recording
    from sww.tracking import PoseTracker

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    out = (
        Path(args.out)
        if args.out
        else Path(args.recordings_dir) / f"{args.label}_{time.strftime('%Y%m%d-%H%M%S')}.npz"
    )
    model = pose_model_path(args.model, Path(args.models_dir))
    frames: list = []
    print(f"Recording '{args.label}' for {args.seconds} s after a {args.countdown} s countdown.")
    print("Stop early: q or Esc in the preview window, or Ctrl+C here.")

    try:
        with (
            PoseTracker(model) as tracker,
            LatestFrameCamera(
                args.camera, args.width, args.height, args.fps, api=args.api, mjpg=not args.no_mjpg
            ) as camera,
        ):
            size = camera.actual_size
            seq = 0
            t_start = now_ms() + args.countdown * 1000
            t_end = t_start + int(args.seconds * 1000)
            last_said = None
            while True:
                captured = camera.read_latest(after_seq=seq, timeout_s=2.0)
                if captured is None:
                    print("No frame for 2 s; is the camera in use by another app?", file=sys.stderr)
                    continue
                seq = captured.seq
                ts = captured.timestamp_ms
                if ts >= t_end:
                    break
                # Track during the countdown too: VIDEO mode warms up on earlier frames.
                pose = tracker.process(captured.image, ts)
                if ts >= t_start:
                    frames.append((pose, ts))
                    label = f"REC {(t_end - ts) / 1000:4.1f} s left"
                    announce = "REC"
                else:
                    label = announce = f"starting in {-(-(t_start - ts) // 1000)}"  # ceil
                if announce != last_said:
                    print(f"  {announce}", flush=True)
                    last_said = announce
                if args.no_preview:
                    continue
                img = captured.image.copy()
                if pose is not None:
                    draw_skeleton(img, pose)
                img = cv2.flip(img, 1)
                draw_banner(img, label if pose is not None else f"{label}  (no person)")
                cv2.imshow(WINDOW_NAME, img)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        if not args.no_preview:
            cv2.destroyAllWindows()

    if not frames:
        print("Nothing recorded.", file=sys.stderr)
        return 1
    meta = {
        "label": args.label,
        "notes": args.notes,
        "started_at": started_at,
        "model": args.model,
        "camera": args.camera,
        "api": args.api,
        "requested": [args.width, args.height, args.fps],
    }
    rec = Recording.from_frames(frames, size, meta)
    rec.save(out)
    fps = (len(rec) - 1) / (rec.duration_ms / 1000) if rec.duration_ms else 0.0
    print(
        f"Saved {out}: {len(rec)} frames, {rec.duration_ms / 1000:.1f} s, {fps:.1f} fps, "
        f"person tracked in {rec.person_present.mean():.0%} of frames."
    )
    if not args.no_csv:
        # Same as `sww replay <file> --csv`, so the CSV is ready without a second step.
        print()
        _replay(rec, args, str(out), out.with_suffix(".csv"))
    print()
    print(f"Re-run later (e.g. after tuning) with: uv run sww replay {out} --csv")
    return 0


def _replay(rec, args: argparse.Namespace, name: str, csv_path: Path | None) -> None:
    """Run the gesture engine over a recording (nothing is sent); print actions and a summary.

    Writes one CSV row per frame (scores, active flags, every rule value) to
    ``csv_path`` if given. Shared by ``replay`` and ``record``.
    """
    backend = RecordingBackend()
    engine, described = build_engine(args, backend)
    t0 = int(rec.timestamps_ms[0])
    fps = (len(rec) - 1) / (rec.duration_ms / 1000) if rec.duration_ms else 0.0
    print(
        f"{name}: label={rec.meta.get('label')!r}, {len(rec)} frames, "
        f"{rec.duration_ms / 1000:.1f} s, {fps:.1f} fps, "
        f"person in {rec.person_present.mean():.0%} of frames"
    )
    for line in described:
        print(f"  {line}")
    print("Replaying (nothing is sent). Times are seconds from the start of the recording.")

    rows: list[dict[str, object]] = []
    max_score: dict[str, float] = {}
    starts: dict[str, int] = {}
    active_ms: dict[str, int] = {}
    prev_t = t0
    for frame, ts in rec.frames():
        step = engine.step(frame, ts)
        _log_actions(step.actions, send=True, t0_ms=t0)
        row: dict[str, object] = {"t_ms": ts - t0, "person": int(frame is not None)}
        for gesture, ev in step.evaluations.items():
            if ev.score is not None:
                max_score[gesture] = max(max_score.get(gesture, 0.0), ev.score)
            if step.active.get(gesture):
                active_ms[gesture] = active_ms.get(gesture, 0) + (ts - prev_t)
            row[f"{gesture}.score"] = "" if ev.score is None else round(ev.score, 4)
            row[f"{gesture}.active"] = int(step.active.get(gesture, False))
            for key, value in ev.details.items():
                row[f"{gesture}.{key}"] = round(value, 4)
        for event in step.events:
            if event.kind == "start":
                starts[event.gesture] = starts.get(event.gesture, 0) + 1
        rows.append(row)
        prev_t = ts
    _log_actions(engine.shutdown("end of recording", prev_t), send=True, t0_ms=t0)

    print()
    print("Summary:")
    for det in engine.detectors:
        n = det.name
        print(
            f"  {n:18} starts {starts.get(n, 0):3d} | active {active_ms.get(n, 0) / 1000:6.2f} s "
            f"| max score {max_score.get(n, 0.0):.2f}"
        )

    if csv_path is not None:
        fields: list[str] = []
        for row in rows:
            fields.extend(k for k in row if k not in fields)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, restval="")
            writer.writeheader()
            writer.writerows(rows)
        print(f"Per-frame scores and rule values written to {csv_path} ({len(rows)} rows).")


def cmd_replay(args: argparse.Namespace) -> int:
    from sww.recording import Recording

    path = Path(args.file)
    rec = Recording.load(path)
    if not len(rec):
        print("Empty recording.", file=sys.stderr)
        return 1
    # --csv alone writes next to the recording; --csv FILE writes there.
    csv_path = (
        None
        if args.csv is None
        else (path.with_suffix(".csv") if args.csv == "auto" else Path(args.csv))
    )
    _replay(rec, args, args.file, csv_path)
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    import numpy as np

    from sww.bench import bench_cameras, bench_model
    from sww.models import pose_model_path

    sample = None
    if not args.skip_camera:
        print("Camera: stand in view with your normal lighting. Each line takes a few seconds.")
        apis = ["dshow", "msmf"] if sys.platform == "win32" else ["dshow"]
        results, sample = bench_cameras(args.camera, apis, [(1280, 720), (640, 480)], args.seconds)
        ok = [r for r in results if not r.error]
        if ok:
            best = max(ok, key=lambda r: r.fps)
            print(
                f"Fastest: --api {best.api}{'' if best.mjpg else ' --no-mjpg'} "
                f"--width {best.requested[0]} --height {best.requested[1]}  ({best.fps:.1f} fps)"
            )
    if sample is None:
        if not args.skip_camera:
            print("No camera frame captured; timing the model on a synthetic image instead.")
        sample = np.full((720, 1280, 3), 127, np.uint8)

    print("\nPose model (on one frame, 100 runs):")
    found_any = False
    for variant in ("lite", "full", "heavy"):
        path = pose_model_path(variant, Path(args.models_dir))
        if not path.is_file():
            print(f"  {variant:5}  not downloaded (uv run sww download-models --variant {variant})")
            continue
        found_any = True
        print(bench_model(path, variant, sample), flush=True)
    return 0 if found_any else 1


# --------------------------------------------------------------------------- parser


def _gesture_options() -> argparse.ArgumentParser:
    """Options that define the gestures and mappings (shared by run and replay)."""
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("gestures")
    g.add_argument(
        "--head-key",
        "--key",
        dest="head_key",
        type=_check_key,
        default="b",
        help="key tapped by 'hand on head' (default: b)",
    )
    g.add_argument(
        "--min-on-ms", type=int, default=50, help="hand on head must hold this long to fire"
    )
    g.add_argument(
        "--forward",
        choices=["run", "arms", "off"],
        default="run",
        help="forward gesture: running in place (arm swing + body bounce), "
        "pumping arms (seated, arm swing only), or off",
    )
    g.add_argument(
        "--forward-key",
        type=_check_key,
        default="w",
        help="key held by the forward gesture (default: w)",
    )
    g.add_argument(
        "--forward-off-ms", type=int, default=200,
        help="how long the forward gesture must stop before the key is released",
    )  # fmt: skip
    return p


def _camera_options() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    g = p.add_argument_group("camera and model")
    g.add_argument("--camera", type=int, default=0)
    g.add_argument("--width", type=int, default=1280)
    g.add_argument("--height", type=int, default=720)
    g.add_argument("--fps", type=int, default=30)
    g.add_argument("--api", default="dshow", choices=["dshow", "msmf"], help="capture backend")
    g.add_argument("--no-mjpg", action="store_true", help="don't request MJPG frames")
    g.add_argument("--model", default="lite", choices=["lite", "full", "heavy"])
    g.add_argument("--models-dir", default="models")
    g.add_argument("--no-preview", action="store_true", help="headless: no window")
    return p


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sww", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    gestures = _gesture_options()
    camera = _camera_options()

    p = sub.add_parser("download-models", help="download MediaPipe pose model(s)")
    p.add_argument("--variant", nargs="+", default=["lite"], choices=["lite", "full", "heavy"])
    p.add_argument("--models-dir", default="models")
    p.add_argument("--force", action="store_true", help="re-download even if present")
    p.set_defaults(func=cmd_download_models)

    p = sub.add_parser("keytest", help="tap (or hold) one key after a countdown")
    p.add_argument("--key", type=_check_key, default="b")
    p.add_argument("--delay", type=int, default=3, help="seconds before the key")
    p.add_argument("--send", action="store_true", help="really send the key (default: dry run)")
    p.add_argument("--tap-ms", type=int, default=15, help="how long a tap holds the key down")
    p.add_argument(
        "--hold-s", type=float, default=0.0,
        help="hold the key this many seconds (one key-down, one key-up) instead of tapping",
    )  # fmt: skip
    p.set_defaults(func=cmd_keytest)

    p = sub.add_parser(
        "run", parents=[gestures, camera], help="track the webcam and send keys for gestures"
    )
    p.add_argument("--send", action="store_true", help="really send keys (default: dry run)")
    p.add_argument("--window", help="only send while the foreground window title contains this")
    p.add_argument("--tap-ms", type=int, default=15, help="how long a tap holds the key down")
    p.add_argument(
        "--pause-hotkey", type=_check_hotkey, default=DEFAULT_PAUSE_HOTKEY,
        help=f"global pause/resume hotkey (default: {DEFAULT_PAUSE_HOTKEY})",
    )  # fmt: skip
    p.add_argument(
        "--no-pause-hotkey", action="store_true", help="don't register it (dry runs/tests only)"
    )
    p.add_argument("--start-paused", action="store_true", help="start with output paused")
    p.add_argument("--no-mirror", action="store_true", help="don't mirror the preview")
    p.add_argument("--debug", action="store_true", help="show rule values and graphs for tuning")
    p.add_argument("--stats-every", type=float, default=5.0, help="seconds between perf lines")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser(
        "record",
        parents=[gestures, camera],
        help="save pose landmarks to a .npz file (and a per-frame replay .csv next to it)",
    )
    p.add_argument("--label", default="session", help="what you're doing, e.g. running, idle")
    p.add_argument("--notes", default="", help="free text stored in the file")
    p.add_argument("--seconds", type=float, default=15.0, help="recording length")
    p.add_argument("--countdown", type=int, default=3, help="seconds before recording starts")
    p.add_argument("--out", help="output file (default: recordings/<label>_<time>.npz)")
    p.add_argument("--recordings-dir", default="recordings")
    p.add_argument(
        "--no-csv", action="store_true", help="don't replay the recording into a .csv afterwards"
    )
    p.set_defaults(func=cmd_record)

    p = sub.add_parser(
        "replay", parents=[gestures], help="run the gesture engine on a recording (dry run)"
    )
    p.add_argument("file", help="a .npz file from `sww record`")
    p.add_argument(
        "--csv",
        nargs="?",
        const="auto",
        help="write per-frame scores and rule values to a CSV "
        "(default path: the recording's name with .csv)",
    )
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("bench", help="measure camera fps and model speed separately")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--seconds", type=float, default=3.0, help="per camera configuration")
    p.add_argument("--models-dir", default="models")
    p.add_argument("--skip-camera", action="store_true", help="only time the model(s)")
    p.set_defaults(func=cmd_bench)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
