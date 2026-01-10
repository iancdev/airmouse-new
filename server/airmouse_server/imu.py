from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImuDelta:
    dx: float
    dy: float
    valid: bool


class ImuTracker:
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

    def process_sample(self, sample: dict) -> ImuDelta:
        ts_ms = sample.get("ts")
        ax = sample.get("ax")
        ay = sample.get("ay")

        if ts_ms is None or ax is None or ay is None:
            return ImuDelta(dx=0.0, dy=0.0, valid=False)

        try:
            ts_ms_f = float(ts_ms)
            ax_f = float(ax)
            ay_f = float(ay)
        except (TypeError, ValueError):
            return ImuDelta(dx=0.0, dy=0.0, valid=False)

        if self._last_ts_ms is None:
            self._last_ts_ms = ts_ms_f
            return ImuDelta(dx=0.0, dy=0.0, valid=False)

        dt = (ts_ms_f - self._last_ts_ms) / 1000.0
        self._last_ts_ms = ts_ms_f
        if dt <= 0 or dt > 0.2:
            return ImuDelta(dx=0.0, dy=0.0, valid=False)

        # Simple damped acceleration integration (very approximate).
        self._vx = (self._vx * self._friction) + (ax_f * dt * self._accel_gain)
        self._vy = (self._vy * self._friction) + (ay_f * dt * self._accel_gain)

        dx = self._vx * dt
        dy = self._vy * dt
        return ImuDelta(dx=dx, dy=dy, valid=True)

