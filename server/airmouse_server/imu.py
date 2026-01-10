from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotionDelta:
    dx: float
    dy: float
    ts_ms: float
    valid: bool


def _parse_ts_ms(sample: dict) -> float | None:
    ts_ms = sample.get("ts")
    if ts_ms is None:
        return None
    try:
        return float(ts_ms)
    except (TypeError, ValueError):
        return None


class AccelTracker:
    def __init__(self, *, accel_gain: float = 120.0, friction: float = 0.86) -> None:
        self._accel_gain = accel_gain
        self._friction = friction
        self._vx = 0.0
        self._vy = 0.0
        self._last_ts_ms: float | None = None

    def reset(self) -> None:
        self._vx = 0.0
        self._vy = 0.0
        self._last_ts_ms = None

    def process_sample(self, sample: dict) -> MotionDelta:
        ts_ms = _parse_ts_ms(sample)
        ax = sample.get("ax")
        ay = sample.get("ay")
        if ts_ms is None or ax is None or ay is None:
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=0.0, valid=False)

        try:
            ax_f = float(ax)
            ay_f = float(ay)
        except (TypeError, ValueError):
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=ts_ms, valid=False)

        if self._last_ts_ms is None:
            self._last_ts_ms = ts_ms
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=ts_ms, valid=False)

        dt = (ts_ms - self._last_ts_ms) / 1000.0
        self._last_ts_ms = ts_ms
        if dt <= 0 or dt > 0.2:
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=ts_ms, valid=False)

        self._vx = (self._vx * self._friction) + (ax_f * dt * self._accel_gain)
        self._vy = (self._vy * self._friction) + (ay_f * dt * self._accel_gain)
        return MotionDelta(dx=self._vx * dt, dy=self._vy * dt, ts_ms=ts_ms, valid=True)


class GyroTracker:
    def __init__(self, *, gyro_gain: float = 0.7, friction: float = 0.86) -> None:
        self._gyro_gain = gyro_gain
        self._friction = friction
        self._vx = 0.0
        self._vy = 0.0
        self._last_ts_ms: float | None = None

    def reset(self) -> None:
        self._vx = 0.0
        self._vy = 0.0
        self._last_ts_ms = None

    def process_sample(self, sample: dict) -> MotionDelta:
        ts_ms = _parse_ts_ms(sample)
        gy = sample.get("gy")
        gz = sample.get("gz")
        if ts_ms is None or gy is None or gz is None:
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=0.0, valid=False)

        try:
            gy_f = float(gy)
            gz_f = float(gz)
        except (TypeError, ValueError):
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=ts_ms, valid=False)

        if self._last_ts_ms is None:
            self._last_ts_ms = ts_ms
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=ts_ms, valid=False)

        dt = (ts_ms - self._last_ts_ms) / 1000.0
        self._last_ts_ms = ts_ms
        if dt <= 0 or dt > 0.2:
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=ts_ms, valid=False)

        # RotationRate is in deg/s. Use as a directional validator / rough movement.
        self._vx = (self._vx * self._friction) + (gz_f * dt * self._gyro_gain)
        self._vy = (self._vy * self._friction) + (gy_f * dt * self._gyro_gain)
        return MotionDelta(dx=self._vx * dt, dy=self._vy * dt, ts_ms=ts_ms, valid=True)


class OrientationTracker:
    def __init__(self, *, gain: float = 0.9, friction: float = 0.9) -> None:
        self._gain = gain
        self._friction = friction
        self._vx = 0.0
        self._vy = 0.0
        self._last_ts_ms: float | None = None
        self._last_beta: float | None = None
        self._last_gamma: float | None = None

    def reset(self) -> None:
        self._vx = 0.0
        self._vy = 0.0
        self._last_ts_ms = None
        self._last_beta = None
        self._last_gamma = None

    @staticmethod
    def _wrap_deg(delta: float) -> float:
        # Wrap to [-180, 180]
        return (delta + 180.0) % 360.0 - 180.0

    def process_sample(self, sample: dict) -> MotionDelta:
        ts_ms = _parse_ts_ms(sample)
        beta = sample.get("beta")
        gamma = sample.get("gamma")
        if ts_ms is None or beta is None or gamma is None:
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=0.0, valid=False)

        try:
            beta_f = float(beta)
            gamma_f = float(gamma)
        except (TypeError, ValueError):
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=ts_ms, valid=False)

        if self._last_ts_ms is None or self._last_beta is None or self._last_gamma is None:
            self._last_ts_ms = ts_ms
            self._last_beta = beta_f
            self._last_gamma = gamma_f
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=ts_ms, valid=False)

        dt = (ts_ms - self._last_ts_ms) / 1000.0
        self._last_ts_ms = ts_ms
        if dt <= 0 or dt > 0.2:
            self._last_beta = beta_f
            self._last_gamma = gamma_f
            return MotionDelta(dx=0.0, dy=0.0, ts_ms=ts_ms, valid=False)

        d_beta = self._wrap_deg(beta_f - self._last_beta)
        d_gamma = self._wrap_deg(gamma_f - self._last_gamma)
        self._last_beta = beta_f
        self._last_gamma = gamma_f

        self._vx = (self._vx * self._friction) + (d_gamma * self._gain)
        self._vy = (self._vy * self._friction) + (d_beta * self._gain)
        return MotionDelta(dx=self._vx, dy=self._vy, ts_ms=ts_ms, valid=True)


# Back-compat alias (initial implementation).
ImuTracker = AccelTracker
ImuDelta = MotionDelta
