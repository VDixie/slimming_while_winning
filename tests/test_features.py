import numpy as np
import pytest
from synthetic import NOSE_Y, SHOULDER_Y, SW, make_frame

from sww.features import joint_angle_deg, to_body_frame
from sww.landmarks import Pose, PoseFrame


def test_body_frame_origin_scale_and_up_axis():
    f = to_body_frame(make_frame())
    assert f is not None
    mid = (f.point(Pose.LEFT_SHOULDER) + f.point(Pose.RIGHT_SHOULDER)) / 2
    np.testing.assert_allclose(mid, [0.0, 0.0], atol=1e-5)
    # Shoulders are exactly one unit apart.
    width = np.linalg.norm(f.point(Pose.LEFT_SHOULDER) - f.point(Pose.RIGHT_SHOULDER))
    assert width == pytest.approx(1.0, abs=1e-5)
    # Nose is above the shoulders, so positive y.
    assert f.point(Pose.NOSE)[1] == pytest.approx((SHOULDER_Y - NOSE_Y) / SW, abs=1e-4)
    assert f.shoulder_width_px == pytest.approx(SW, rel=1e-4)


def test_body_frame_is_distance_invariant():
    near = to_body_frame(make_frame(scale=1.0, right="on_head"))
    far = to_body_frame(make_frame(scale=0.5, right="on_head"))
    assert near is not None and far is not None
    np.testing.assert_allclose(near.points, far.points, atol=1e-4)
    assert far.shoulder_width_px == pytest.approx(near.shoulder_width_px / 2, rel=1e-4)


def test_aspect_ratio_handled_via_pixels():
    # Same pixel layout on a 16:9 image: a 45-degree line in pixels must stay 45 degrees.
    lms = np.zeros((33, 4), dtype=np.float32)
    lms[:, 3] = 1.0
    w, h = 1280, 720
    lms[Pose.LEFT_SHOULDER, :2] = (700 / w, 400 / h)
    lms[Pose.RIGHT_SHOULDER, :2] = (600 / w, 400 / h)
    lms[Pose.NOSE, :2] = (650 / w, 350 / h)  # 50 px right of R shoulder, 50 px up
    f = to_body_frame(PoseFrame(0, lms, (w, h)))
    assert f is not None
    np.testing.assert_allclose(f.point(Pose.NOSE), [0.0, 0.5], atol=1e-5)


@pytest.mark.parametrize("hidden", [(Pose.LEFT_SHOULDER,), (Pose.RIGHT_SHOULDER,)])
def test_no_body_frame_without_shoulders(hidden):
    assert to_body_frame(make_frame(hidden=hidden)) is None


def test_no_body_frame_when_shoulders_collapse():
    assert to_body_frame(make_frame(scale=0.1)) is None  # 16 px shoulder width


def test_pose_frame_rejects_bad_shape():
    with pytest.raises(ValueError):
        PoseFrame(0, np.zeros((10, 4), dtype=np.float32), (640, 480))


@pytest.mark.parametrize(
    ("c", "expected"),
    [
        ((2.0, 0.0), 180.0),  # straight line
        ((1.0, 1.0), 90.0),  # right angle
        ((0.0, 0.0), 0.0),  # folded back onto A
        ((1.0, 0.0), 180.0),  # degenerate (C == B) treated as straight
    ],
)
def test_joint_angle(c, expected):
    a, b = np.array([0.0, 0.0]), np.array([1.0, 0.0])
    assert joint_angle_deg(a, b, np.array(c)) == pytest.approx(expected, abs=1e-6)
