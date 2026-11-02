"""Command-line entry point.

Commands:
    sww download-models   Fetch the MediaPipe pose model(s) (one-time, needs internet).
    sww keytest           Send one key after a countdown, to check SendInput reaches an app.
    sww run               Webcam → pose → "hand on head" → tap a key.

Safety defaults: ``run`` and ``keytest`` are dry runs (nothing is sent) unless
you pass ``--send``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from sww.output.base import KeyboardBackend, RecordingBackend
from sww.output.keys import key_to_vk, known_keys


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
    print(f"{mode}: will tap '{args.key}' in {args.delay} s. Switch to the target window now.")
    for remaining in range(args.delay, 0, -1):
        print(f"  {remaining}...", flush=True)
        time.sleep(1)
    backend.tap(args.key)
    print(f"Tapped '{args.key}'." if args.send else f"Would have tapped '{args.key}'.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    # Heavy imports here so `sww --help` and `keytest` start instantly.
    import cv2

    from sww.actions import ActionMapper, Mapping
    from sww.capture import LatestFrameCamera, now_ms
    from sww.engine import Engine
    from sww.gestures import HandOnHead
    from sww.models import pose_model_path
    from sww.output.focus import window_title_gate
    from sww.preview import draw_banner, render
    from sww.state import DebounceConfig
    from sww.timing import PerfStats
    from sww.tracking import PoseTracker

    backend = _make_backend(args.send, args.tap_ms)
    gate = window_title_gate(args.window) if args.window else None
    detector = HandOnHead()
    engine = Engine(
        detectors=[detector],
        mapper=ActionMapper([Mapping(detector.name, args.key)], backend, gate),
        debounce={detector.name: DebounceConfig(min_on_ms=args.min_on_ms)},
    )
    stats = PerfStats()
    model = pose_model_path(args.model, Path(args.models_dir))

    send_desc = "SENDING keys" if args.send else "DRY RUN (no keys sent; add --send)"
    target = (
        f"only while a window titled '*{args.window}*' is focused"
        if args.window
        else "to any focused window"
    )
    print(f"{send_desc} {target}. Gesture: hand on head -> tap '{args.key}'.")
    print("Quit: press q or Esc in the preview window, or Ctrl+C here.")

    last_banner = ""
    last_banner_ms = 0
    last_stats_ms = now_ms()
    window_name = "sww - preview"

    with (
        PoseTracker(model) as tracker,
        LatestFrameCamera(
            args.camera, args.width, args.height, args.fps, api=args.api, mjpg=not args.no_mjpg
        ) as camera,
    ):
        w, h = camera.actual_size
        print(
            f"Camera {args.camera} via {args.api}: {w}x{h} {camera.actual_fourcc} "
            f"@ {camera.actual_fps:.0f} fps (driver-reported)"
        )
        seq = 0
        try:
            while True:
                captured = camera.read_latest(after_seq=seq, timeout_s=2.0)
                if captured is None:
                    print("No frame for 2 s; is the camera in use by another app?", file=sys.stderr)
                    continue
                seq = captured.seq
                start = now_ms()
                pose = tracker.process(captured.image, captured.timestamp_ms)
                tracked = now_ms()
                step = engine.step(pose, captured.timestamp_ms)
                done = now_ms()
                stats.add(captured.timestamp_ms, start, tracked, done)

                for rec in step.actions:
                    msg = f"{rec.action.upper()} '{rec.key}'"
                    if rec.reason:
                        msg += f" ({rec.reason})"
                    if not args.send and rec.action == "tap":
                        msg = f"[dry run] {msg}"
                    print(f"{done / 1000:10.3f}s  {rec.event.gesture} -> {msg}", flush=True)
                    last_banner, last_banner_ms = msg, done

                if done - last_stats_ms >= args.stats_every * 1000:
                    summary = stats.summary()
                    if summary:
                        print(f"[perf] {summary}", flush=True)
                    last_stats_ms = done

                if args.no_preview:
                    continue
                summary = stats.summary()
                status = [
                    send_desc,
                    "no person detected" if pose is None else "tracking",
                    str(summary) if summary else "",
                ]
                img = render(
                    captured.image, pose, step, status, mirror=not args.no_mirror, debug=args.debug
                )
                if last_banner and done - last_banner_ms < 1500:
                    draw_banner(img, last_banner)
                cv2.imshow(window_name, img)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
        except KeyboardInterrupt:
            pass
        finally:
            cv2.destroyAllWindows()
    final = stats.summary()
    if final:
        print(f"[perf, last {len(stats)} frames] {final}")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sww", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("download-models", help="download MediaPipe pose model(s)")
    p.add_argument("--variant", nargs="+", default=["lite"], choices=["lite", "full", "heavy"])
    p.add_argument("--models-dir", default="models")
    p.add_argument("--force", action="store_true", help="re-download even if present")
    p.set_defaults(func=cmd_download_models)

    p = sub.add_parser("keytest", help="tap one key after a countdown")
    p.add_argument("--key", type=_check_key, default="b")
    p.add_argument("--delay", type=int, default=3, help="seconds before the tap")
    p.add_argument("--send", action="store_true", help="really send the key (default: dry run)")
    p.add_argument("--tap-ms", type=int, default=15, help="how long a tap holds the key down")
    p.set_defaults(func=cmd_keytest)

    p = sub.add_parser("run", help="track the webcam and tap a key on 'hand on head'")
    p.add_argument("--key", type=_check_key, default="b", help="key to tap (default: b)")
    p.add_argument("--send", action="store_true", help="really send keys (default: dry run)")
    p.add_argument("--window", help="only send while the foreground window title contains this")
    p.add_argument("--tap-ms", type=int, default=15, help="how long a tap holds the key down")
    p.add_argument("--min-on-ms", type=int, default=50, help="gesture must hold this long to fire")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--api", default="dshow", choices=["dshow", "msmf"], help="capture backend")
    p.add_argument("--no-mjpg", action="store_true", help="don't request MJPG frames")
    p.add_argument("--model", default="lite", choices=["lite", "full", "heavy"])
    p.add_argument("--models-dir", default="models")
    p.add_argument("--no-preview", action="store_true", help="headless: no window")
    p.add_argument("--no-mirror", action="store_true", help="don't mirror the preview")
    p.add_argument("--debug", action="store_true", help="show rule values for tuning")
    p.add_argument("--stats-every", type=float, default=5.0, help="seconds between perf lines")
    p.set_defaults(func=cmd_run)

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
