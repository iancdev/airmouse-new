from __future__ import annotations

import math
from dataclasses import dataclass

from .imu import MotionDelta


@dataclass(frozen=True)
class VoteResult:
    ok: bool
    total_votes: int
    yes_votes: int


def _mag(dx: float, dy: float) -> float:
    return math.hypot(dx, dy)


def _angle(dx: float, dy: float) -> float:
    return math.atan2(dy, dx)


def _angle_diff(a: float, b: float) -> float:
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return abs(d)


def majority_validate_direction(
    *,
    primary: MotionDelta,
    validators: list[MotionDelta],
    max_age_ms: float = 140.0,
    min_mag: float = 0.01,
    max_angle_deg: float = 40.0,
) -> VoteResult:
    if not primary.valid:
        return VoteResult(ok=False, total_votes=0, yes_votes=0)

    primary_mag = _mag(primary.dx, primary.dy)
    if primary_mag < min_mag:
        return VoteResult(ok=True, total_votes=1, yes_votes=1)

    now_ms = primary.ts_ms
    max_angle = math.radians(max_angle_deg)
    primary_angle = _angle(primary.dx, primary.dy)

    votes = 1
    yes = 1

    for v in validators:
        if not v.valid:
            continue
        if abs(now_ms - v.ts_ms) > max_age_ms:
            continue
        if _mag(v.dx, v.dy) < min_mag:
            continue
        votes += 1
        if _angle_diff(primary_angle, _angle(v.dx, v.dy)) <= max_angle:
            yes += 1

    ok = yes >= (votes // 2 + 1)
    return VoteResult(ok=ok, total_votes=votes, yes_votes=yes)

