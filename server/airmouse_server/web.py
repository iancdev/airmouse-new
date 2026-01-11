from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import cv2
import numpy as np

from .mouse import MouseController
from .protocol import parse_client_msg
from .consensus import majority_validate_direction
from .imu import AccelTracker, GyroTracker, MotionDelta, OrientationTracker
from .smoothing import MotionSmoother, SmoothingConfig
from .vision import VisionTracker

logger = logging.getLogger("airmouse")

DEFAULT_ENABLED = {"camera": False, "accel": True, "gyro": False, "orientation": False}
MOVE_SCALES = {"camera": 4.0, "accel": 220.0, "gyro": 18.0, "orientation": 4.0}
DEFAULT_TICK_HZ = 60.0
DEFAULT_SMOOTHING_HALF_LIFE_MS = 80.0
DEFAULT_DEADZONE_PX = 0.25
MAX_STEP_PX = 120.0

def create_app(*, static_dir: Path | None) -> FastAPI:
    app = FastAPI(title="AirMouse")

    mouse = MouseController()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        session = ClientSession()
        _start_motion_thread(mouse, session)
        try:
            while True:
                message = await ws.receive()
                if "text" in message and message["text"] is not None:
                    await _handle_text_message(ws, message["text"], mouse, session)
                elif "bytes" in message and message["bytes"] is not None:
                    await _handle_binary_message(ws, message["bytes"], mouse, session)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            logger.exception("WebSocket error: %s", exc)
            try:
                await ws.send_text(json.dumps({"t": "error", "message": str(exc)}))
            except Exception:
                pass
        finally:
            _stop_motion_thread(session)

    if static_dir is not None and static_dir.exists():
        # Next.js static export expects to be served at the origin root.
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="app")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def root() -> str:
            return (
                "<!doctype html><html><head><meta charset='utf-8'/>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
                "<title>AirMouse</title></head>"
                "<body><h1>AirMouse server</h1><p>Build the client and pass --static-dir.</p></body></html>"
            )

    return app


def _scale_move(source: str, delta: MotionDelta) -> tuple[float, float]:
    scale = MOVE_SCALES.get(source, 1.0)
    return delta.dx * scale, delta.dy * scale


def _select_primary_imu(session: "ClientSession") -> tuple[str, MotionDelta] | None:
    for source in ("accel", "orientation", "gyro"):
        if not session.enabled.get(source):
            continue
        delta = session.last.get(source)
        if delta is not None and delta.valid:
            return source, delta
    return None


def _rotate(delta: MotionDelta, screen_angle_deg: int) -> MotionDelta:
    angle = screen_angle_deg % 360
    if angle == 0 or not delta.valid:
        return delta

    dx, dy = delta.dx, delta.dy
    if angle == 90:
        dx, dy = -dy, dx
    elif angle == 180:
        dx, dy = -dx, -dy
    elif angle == 270:
        dx, dy = dy, -dx
    else:
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        dx, dy = (dx * cos_a - dy * sin_a), (dx * sin_a + dy * cos_a)
    return MotionDelta(dx=dx, dy=dy, ts_ms=delta.ts_ms, valid=delta.valid)


@dataclass
class ClientSession:
    sensitivity: float = 1.0
    camera_fps: int = 15
    screen_angle_deg: int = 0
    tick_hz: float = DEFAULT_TICK_HZ
    enabled: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_ENABLED))
    pending_frame_meta: dict | None = None
    vision: VisionTracker = field(default_factory=VisionTracker)
    accel: AccelTracker = field(default_factory=AccelTracker)
    gyro: GyroTracker = field(default_factory=GyroTracker)
    orientation: OrientationTracker = field(default_factory=OrientationTracker)
    last: dict[str, MotionDelta] = field(default_factory=dict)
    pending: dict[str, tuple[float, float]] = field(default_factory=dict, repr=False)
    pending_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    motion_thread: threading.Thread | None = field(default=None, repr=False)
    smoother: MotionSmoother = field(
        default_factory=lambda: MotionSmoother(
            SmoothingConfig(
                half_life_ms=DEFAULT_SMOOTHING_HALF_LIFE_MS,
                deadzone_px=DEFAULT_DEADZONE_PX,
                max_step_px=MAX_STEP_PX,
            )
        ),
        repr=False,
    )
    last_out_dx: float = 0.0
    last_out_dy: float = 0.0


def _accumulate(session: ClientSession, *, source: str, dx: float, dy: float) -> None:
    if dx == 0 and dy == 0:
        return
    with session.pending_lock:
        prev = session.pending.get(source)
        if prev is None:
            session.pending[source] = (dx, dy)
        else:
            session.pending[source] = (prev[0] + dx, prev[1] + dy)


def _start_motion_thread(mouse: MouseController, session: ClientSession) -> None:
    if session.motion_thread is not None and session.motion_thread.is_alive():
        return
    session.stop_event.clear()
    thread = threading.Thread(target=_motion_loop, args=(mouse, session), daemon=True)
    session.motion_thread = thread
    thread.start()


def _stop_motion_thread(session: ClientSession) -> None:
    session.stop_event.set()
    thread = session.motion_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=1.5)


def _motion_loop(mouse: MouseController, session: ClientSession) -> None:
    last_tick = time.monotonic()
    interval = 1.0 / max(1.0, float(session.tick_hz))

    while not session.stop_event.is_set():
        now = time.monotonic()
        dt = now - last_tick
        if dt < interval:
            session.stop_event.wait(interval - dt)
            continue
        last_tick = now

        with session.pending_lock:
            deltas = session.pending
            session.pending = {}

        raw_dx, raw_dy = _compute_raw_delta(session, deltas)
        dx = raw_dx * session.sensitivity
        dy = raw_dy * session.sensitivity
        dx, dy = session.smoother.apply(dx, dy, dt_s=dt)

        if dx != 0.0 or dy != 0.0:
            session.last_out_dx = dx
            session.last_out_dy = dy
            mouse.move_relative(dx, dy)


def _compute_raw_delta(session: ClientSession, deltas: dict[str, tuple[float, float]]) -> tuple[float, float]:
    now_ms = time.time() * 1000.0

    motions: dict[str, MotionDelta] = {}
    for source, (dx, dy) in deltas.items():
        if dx == 0 and dy == 0:
            continue
        motions[source] = MotionDelta(dx=dx, dy=dy, ts_ms=now_ms, valid=True)

    if not motions:
        return 0.0, 0.0

    priority = ["camera", "delta", "accel", "orientation", "gyro"]
    primary_source = next((s for s in priority if s in motions), next(iter(motions.keys())))
    primary = motions[primary_source]
    validators = [v for s, v in motions.items() if s != primary_source]

    if primary_source == "camera" and not session.enabled.get("camera"):
        return 0.0, 0.0

    if primary_source in DEFAULT_ENABLED and not session.enabled.get(primary_source, False):
        return 0.0, 0.0

    if len(validators) >= 2:
        vote = majority_validate_direction(primary=primary, validators=validators)
        if not vote.ok:
            return 0.0, 0.0
        return primary.dx, primary.dy

    if len(validators) == 1:
        vote = majority_validate_direction(primary=primary, validators=validators)
        if vote.ok:
            return primary.dx, primary.dy

        prev_dx = session.last_out_dx
        prev_dy = session.last_out_dy
        if prev_dx == 0 and prev_dy == 0:
            return primary.dx * 0.35, primary.dy * 0.35

        prev = MotionDelta(dx=prev_dx, dy=prev_dy, ts_ms=now_ms, valid=True)
        tie = majority_validate_direction(primary=primary, validators=[prev], max_age_ms=10_000.0)
        if tie.ok:
            return primary.dx, primary.dy
        return primary.dx * 0.35, primary.dy * 0.35

    return primary.dx, primary.dy


async def _handle_text_message(
    ws: WebSocket,
    text: str,
    mouse: MouseController,
    session: ClientSession,
) -> None:
    payload = json.loads(text)
    msg = parse_client_msg(payload)

    if msg.t == "hello":
        await ws.send_text(json.dumps({"t": "server.state", "ok": True}))
        return

    if msg.t == "config":
        session.sensitivity = float(msg.raw.get("sensitivity", 1.0))
        session.camera_fps = int(msg.raw.get("cameraFps", session.camera_fps))
        try:
            session.screen_angle_deg = int(msg.raw.get("screenAngle", 0)) % 360
        except (TypeError, ValueError):
            session.screen_angle_deg = 0
        try:
            smoothing_ms = float(msg.raw.get("smoothingHalfLifeMs", DEFAULT_SMOOTHING_HALF_LIFE_MS))
        except (TypeError, ValueError):
            smoothing_ms = DEFAULT_SMOOTHING_HALF_LIFE_MS
        try:
            deadzone_px = float(msg.raw.get("deadzonePx", DEFAULT_DEADZONE_PX))
        except (TypeError, ValueError):
            deadzone_px = DEFAULT_DEADZONE_PX

        enabled = msg.raw.get("enabled")
        if isinstance(enabled, dict):
            for key in DEFAULT_ENABLED:
                val = enabled.get(key)
                if isinstance(val, bool):
                    session.enabled[key] = val

        session.smoother.update_config(
            SmoothingConfig(
                half_life_ms=max(0.0, smoothing_ms),
                deadzone_px=max(0.0, deadzone_px),
                max_step_px=MAX_STEP_PX,
            )
        )
        session.smoother.reset()
        session.pending_frame_meta = None
        session.vision.reset()
        session.accel.reset()
        session.gyro.reset()
        session.orientation.reset()
        session.last.clear()
        with session.pending_lock:
            session.pending.clear()
        await ws.send_text(json.dumps({"t": "server.state", "configured": True}))
        return

    if msg.t == "input.click":
        mouse.click(button=str(msg.raw.get("button")), state=str(msg.raw.get("state")))
        return

    if msg.t == "input.scroll":
        mouse.scroll(float(msg.raw.get("delta", 0.0)) * session.sensitivity)
        return

    if msg.t == "move.delta":
        dx = float(msg.raw.get("dx", 0.0))
        dy = float(msg.raw.get("dy", 0.0))
        _accumulate(session, source="delta", dx=dx, dy=dy)
        return

    if msg.t == "imu.sample":
        if session.enabled.get("accel"):
            delta = session.accel.process_sample(msg.raw)
            delta = _rotate(delta, session.screen_angle_deg)
            # Cursor coordinates use +Y = down; device acceleration uses +Y = up.
            delta = MotionDelta(dx=delta.dx, dy=-delta.dy, ts_ms=delta.ts_ms, valid=delta.valid)
            session.last["accel"] = delta
            if delta.valid:
                dx, dy = _scale_move("accel", delta)
                _accumulate(session, source="accel", dx=dx, dy=dy)
        if session.enabled.get("gyro"):
            delta = session.gyro.process_sample(msg.raw)
            delta = _rotate(delta, session.screen_angle_deg)
            session.last["gyro"] = delta
            if delta.valid:
                dx, dy = _scale_move("gyro", delta)
                _accumulate(session, source="gyro", dx=dx, dy=dy)
        if session.enabled.get("orientation"):
            delta = session.orientation.process_sample(msg.raw)
            delta = _rotate(delta, session.screen_angle_deg)
            session.last["orientation"] = delta
            if delta.valid:
                dx, dy = _scale_move("orientation", delta)
                _accumulate(session, source="orientation", dx=dx, dy=dy)
        return

    if msg.t == "cam.frame":
        session.pending_frame_meta = msg.raw
        return

    await ws.send_text(json.dumps({"t": "error", "message": f"Unknown message type: {msg.t}"}))


async def _handle_binary_message(
    ws: WebSocket,
    data: bytes,
    mouse: MouseController,
    session: ClientSession,
) -> None:
    if not session.enabled.get("camera"):
        return

    meta = session.pending_frame_meta
    session.pending_frame_meta = None
    if not isinstance(meta, dict):
        return

    ts = meta.get("ts")
    try:
        ts_ms = float(ts) if ts is not None else 0.0
    except (TypeError, ValueError):
        ts_ms = 0.0

    mime = meta.get("mime")
    if not isinstance(mime, str) or not mime.startswith("image/"):
        return

    buf = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if frame is None:
        return

    delta = session.vision.process_bgr(frame)
    cam_delta = MotionDelta(dx=delta.dx, dy=delta.dy, ts_ms=ts_ms, valid=delta.valid)
    session.last["camera"] = cam_delta
    if not cam_delta.valid:
        return

    cam_delta = _rotate(cam_delta, session.screen_angle_deg)
    dx, dy = _scale_move("camera", cam_delta)
    _accumulate(session, source="camera", dx=dx, dy=dy)
