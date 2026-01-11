from __future__ import annotations

import unittest

from .fusion import FusionConfig, compute_raw_delta
from .imu import MotionDelta


class FusionTests(unittest.TestCase):
    def test_camera_still_vetoes_small_imu(self) -> None:
        cfg = FusionConfig(
            camera_gate_enabled=True,
            camera_max_age_ms=250.0,
            camera_still_px=0.5,
            imu_min_px_when_camera_still=2.5,
        )
        now_ms = 1_000.0
        last_motion = {"camera": MotionDelta(dx=0.0, dy=0.0, ts_ms=now_ms - 10.0, valid=True)}
        dx, dy = compute_raw_delta(
            pending={"accel": (1.0, 0.0)},
            enabled={"camera": True, "accel": True, "gyro": False, "orientation": False},
            last_motion=last_motion,
            last_out=(5.0, 0.0),
            now_ms=now_ms,
            config=cfg,
        )
        self.assertEqual((dx, dy), (0.0, 0.0))

    def test_camera_still_allows_large_imu(self) -> None:
        cfg = FusionConfig(camera_gate_enabled=True, camera_max_age_ms=250.0, camera_still_px=0.5, imu_min_px_when_camera_still=2.5)
        now_ms = 1_000.0
        last_motion = {"camera": MotionDelta(dx=0.0, dy=0.0, ts_ms=now_ms - 10.0, valid=True)}
        dx, dy = compute_raw_delta(
            pending={"accel": (10.0, 0.0)},
            enabled={"camera": True, "accel": True, "gyro": False, "orientation": False},
            last_motion=last_motion,
            last_out=(0.0, 0.0),
            now_ms=now_ms,
            config=cfg,
        )
        self.assertEqual((dx, dy), (10.0, 0.0))

    def test_camera_validator_disagrees_rejects_imu(self) -> None:
        cfg = FusionConfig(
            camera_gate_enabled=True,
            camera_max_age_ms=250.0,
            camera_validator_min_px=1.0,
            max_angle_deg=40.0,
        )
        now_ms = 1_000.0
        last_motion = {"camera": MotionDelta(dx=10.0, dy=0.0, ts_ms=now_ms - 10.0, valid=True)}
        dx, dy = compute_raw_delta(
            pending={"accel": (0.0, 10.0)},
            enabled={"camera": True, "accel": True, "gyro": False, "orientation": False},
            last_motion=last_motion,
            last_out=(0.0, 0.0),
            now_ms=now_ms,
            config=cfg,
        )
        self.assertEqual((dx, dy), (0.0, 0.0))

    def test_camera_primary_is_authoritative(self) -> None:
        cfg = FusionConfig(camera_gate_enabled=True)
        now_ms = 1_000.0
        last_motion = {"camera": MotionDelta(dx=10.0, dy=0.0, ts_ms=now_ms - 10.0, valid=True)}
        dx, dy = compute_raw_delta(
            pending={"camera": (5.0, 0.0), "accel": (0.0, -10.0)},
            enabled={"camera": True, "accel": True, "gyro": False, "orientation": False},
            last_motion=last_motion,
            last_out=(0.0, 0.0),
            now_ms=now_ms,
            config=cfg,
        )
        self.assertEqual((dx, dy), (5.0, 0.0))


if __name__ == "__main__":
    unittest.main()

