from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SmoothingConfig:
    half_life_ms: float = 0.0
    deadzone_px: float = 0.0
    max_step_px: float = 120.0


class MotionSmoother:
    def __init__(self, config: SmoothingConfig | None = None) -> None:
        self._config = config or SmoothingConfig()
        self._sx = 0.0
        self._sy = 0.0

    @property
    def config(self) -> SmoothingConfig:
        return self._config

    def update_config(self, config: SmoothingConfig) -> None:
        self._config = config

    def reset(self) -> None:
        self._sx = 0.0
        self._sy = 0.0

    def last(self) -> tuple[float, float]:
        return self._sx, self._sy

    def apply(self, dx: float, dy: float, *, dt_s: float) -> tuple[float, float]:
        if dt_s <= 0 or self._config.half_life_ms <= 0:
            sx, sy = dx, dy
        else:
            alpha = 1.0 - math.exp(-math.log(2.0) * (dt_s * 1000.0) / self._config.half_life_ms)
            self._sx += (dx - self._sx) * alpha
            self._sy += (dy - self._sy) * alpha
            sx, sy = self._sx, self._sy

        if self._config.deadzone_px > 0 and math.hypot(sx, sy) < self._config.deadzone_px:
            self._sx = 0.0
            self._sy = 0.0
            return 0.0, 0.0

        max_step = self._config.max_step_px
        if max_step > 0:
            sx = max(-max_step, min(max_step, sx))
            sy = max(-max_step, min(max_step, sy))
            self._sx = sx
            self._sy = sy

        return sx, sy

