from __future__ import annotations

import math
from dataclasses import dataclass

from .consensus import majority_validate_direction
from .imu import MotionDelta

IMU_SOURCES: tuple[str, ...] = ("accel", "gyro", "orientation")
AUTHORITATIVE_SOURCES: tuple[str, ...] = ("camera", "delta")


@dataclass(frozen=True)
class FusionConfig:
    camera_gate_enabled: bool = True
    camera_max_age_ms: float = 250.0
    camera_still_px: float = 0.35
    camera_validator_min_px: float = 0.75
    imu_min_px_when_camera_still: float = 2.5
    imu_opposite_max_px_when_camera_still: float = 6.0
    max_angle_deg: float = 40.0
    min_mag: float = 0.01
    weak_fallback_scale: float = 0.35


def _mag(dx: float, dy: float) -> float:
    return math.hypot(dx, dy)


def compute_raw_delta(
    *,
    pending: dict[str, tuple[float, float]],
    enabled: dict[str, bool],
    last_motion: dict[str, MotionDelta],
    last_out: tuple[float, float],
    now_ms: float,
    config: FusionConfig | None = None,
) -> tuple[float, float]:
    cfg = config or FusionConfig()

    motions: dict[str, MotionDelta] = {}
    for source, (dx, dy) in pending.items():
        if dx == 0.0 and dy == 0.0:
            continue
        motions[source] = MotionDelta(dx=dx, dy=dy, ts_ms=now_ms, valid=True)

    if not motions:
        return 0.0, 0.0

    priority = ["camera", "delta", "accel", "orientation", "gyro"]
    primary_source = next((s for s in priority if s in motions), next(iter(motions.keys())))
    primary = motions[primary_source]

    if primary_source == "camera" and not enabled.get("camera", False):
        return 0.0, 0.0
    if primary_source in IMU_SOURCES and not enabled.get(primary_source, False):
        return 0.0, 0.0

    if primary_source in AUTHORITATIVE_SOURCES:
        return primary.dx, primary.dy

    # Camera can provide a strong "stillness" veto against IMU bounce-back, even on ticks
    # where the camera didn't contribute a pending delta.
    cam = last_motion.get("camera") if enabled.get("camera", False) else None
    cam_fresh = (
        cfg.camera_gate_enabled
        and cam is not None
        and cam.valid
        and (now_ms - cam.ts_ms) >= 0.0
        and (now_ms - cam.ts_ms) <= cfg.camera_max_age_ms
    )
    if cam_fresh and primary_source in IMU_SOURCES:
        cam_mag = _mag(cam.dx, cam.dy)
        if cam_mag <= cfg.camera_still_px:
            imu_mag = _mag(primary.dx, primary.dy)
            prev_dx, prev_dy = last_out
            opposite_prev = (prev_dx != 0.0 or prev_dy != 0.0) and (primary.dx * prev_dx + primary.dy * prev_dy) < 0.0
            if imu_mag <= cfg.imu_min_px_when_camera_still:
                return 0.0, 0.0
            if opposite_prev and imu_mag <= cfg.imu_opposite_max_px_when_camera_still:
                return 0.0, 0.0

    validators = [v for s, v in motions.items() if s != primary_source]
    if cam_fresh and "camera" not in motions and _mag(cam.dx, cam.dy) >= cfg.camera_validator_min_px:
        validators.append(cam)

    if len(validators) >= 2:
        vote = majority_validate_direction(
            primary=primary,
            validators=validators,
            max_age_ms=cfg.camera_max_age_ms,
            min_mag=cfg.min_mag,
            max_angle_deg=cfg.max_angle_deg,
        )
        if not vote.ok:
            return 0.0, 0.0
        return primary.dx, primary.dy

    if len(validators) == 1:
        v = validators[0]
        vote = majority_validate_direction(
            primary=primary,
            validators=validators,
            max_age_ms=cfg.camera_max_age_ms,
            min_mag=cfg.min_mag,
            max_angle_deg=cfg.max_angle_deg,
        )
        if vote.ok:
            return primary.dx, primary.dy

        # If the camera is the validator and it disagrees, prefer a hard reject (camera is
        # typically the best anti-bounce signal when it is fresh + valid).
        if cam_fresh and v is cam:
            return 0.0, 0.0

        prev_dx, prev_dy = last_out
        if prev_dx == 0.0 and prev_dy == 0.0:
            return primary.dx * cfg.weak_fallback_scale, primary.dy * cfg.weak_fallback_scale

        prev = MotionDelta(dx=prev_dx, dy=prev_dy, ts_ms=now_ms, valid=True)
        tie = majority_validate_direction(
            primary=primary,
            validators=[prev],
            max_age_ms=10_000.0,
            min_mag=cfg.min_mag,
            max_angle_deg=cfg.max_angle_deg,
        )
        if tie.ok:
            return primary.dx, primary.dy
        return primary.dx * cfg.weak_fallback_scale, primary.dy * cfg.weak_fallback_scale

    return primary.dx, primary.dy

