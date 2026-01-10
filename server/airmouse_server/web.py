from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import cv2
import numpy as np

from .mouse import MouseConfig, MouseController
from .protocol import parse_client_msg
from .consensus import majority_validate_direction
from .imu import AccelTracker, GyroTracker, MotionDelta, OrientationTracker
from .vision import VisionTracker

logger = logging.getLogger("airmouse")

DEFAULT_ENABLED = {"camera": False, "accel": True, "gyro": False, "orientation": False}
MOVE_SCALES = {"camera": 4.0, "accel": 220.0, "gyro": 18.0, "orientation": 4.0}
MAX_MOVE_PER_EVENT = 120.0

def create_app(*, static_dir: Path | None) -> FastAPI:
    app = FastAPI(title="AirMouse")

    if static_dir is not None and static_dir.exists():
        app.mount("/app", StaticFiles(directory=str(static_dir), html=True), name="app")

        @app.get("/", response_class=HTMLResponse)
        async def root() -> str:
            return (
                "<!doctype html><html><head><meta charset='utf-8'/>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
                "<title>AirMouse</title></head>"
                "<body><a href='/app/'>Open AirMouse</a></body></html>"
            )

    else:

        @app.get("/", response_class=HTMLResponse)
        async def root() -> str:
            return (
                "<!doctype html><html><head><meta charset='utf-8'/>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
                "<title>AirMouse</title></head>"
                "<body><h1>AirMouse server</h1><p>Build the client and pass --static-dir.</p></body></html>"
            )

    mouse = MouseController()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        session = ClientSession()
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

    return app


def _scale_move(source: str, delta: MotionDelta, sensitivity: float) -> tuple[float, float]:
    scale = MOVE_SCALES.get(source, 1.0)
    dx = delta.dx * scale * sensitivity
    dy = delta.dy * scale * sensitivity
    dx = max(-MAX_MOVE_PER_EVENT, min(MAX_MOVE_PER_EVENT, dx))
    dy = max(-MAX_MOVE_PER_EVENT, min(MAX_MOVE_PER_EVENT, dy))
    return dx, dy


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
    enabled: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_ENABLED))
    pending_frame_meta: dict | None = None
    vision: VisionTracker = field(default_factory=VisionTracker)
    accel: AccelTracker = field(default_factory=AccelTracker)
    gyro: GyroTracker = field(default_factory=GyroTracker)
    orientation: OrientationTracker = field(default_factory=OrientationTracker)
    last: dict[str, MotionDelta] = field(default_factory=dict)


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

        enabled = msg.raw.get("enabled")
        if isinstance(enabled, dict):
            for key in DEFAULT_ENABLED:
                val = enabled.get(key)
                if isinstance(val, bool):
                    session.enabled[key] = val

        mouse.update_config(MouseConfig(move_scale=session.sensitivity, scroll_scale=session.sensitivity))
        session.pending_frame_meta = None
        session.vision.reset()
        session.accel.reset()
        session.gyro.reset()
        session.orientation.reset()
        session.last.clear()
        await ws.send_text(json.dumps({"t": "server.state", "configured": True}))
        return

    if msg.t == "input.click":
        mouse.click(button=str(msg.raw.get("button")), state=str(msg.raw.get("state")))
        return

    if msg.t == "input.scroll":
        mouse.scroll(float(msg.raw.get("delta", 0.0)))
        return

    if msg.t == "move.delta":
        dx = float(msg.raw.get("dx", 0.0))
        dy = float(msg.raw.get("dy", 0.0))
        mouse.move_relative(dx, dy)
        return

    if msg.t == "imu.sample":
        if session.enabled.get("accel"):
            delta = session.accel.process_sample(msg.raw)
            session.last["accel"] = _rotate(delta, session.screen_angle_deg)
        if session.enabled.get("gyro"):
            delta = session.gyro.process_sample(msg.raw)
            session.last["gyro"] = _rotate(delta, session.screen_angle_deg)
        if session.enabled.get("orientation"):
            delta = session.orientation.process_sample(msg.raw)
            session.last["orientation"] = _rotate(delta, session.screen_angle_deg)

        # If camera is enabled, treat IMU sources as validators only.
        if session.enabled.get("camera"):
            return

        primary = _select_primary_imu(session)
        if primary is None:
            return
        source, primary_delta = primary
        validators = [
            session.last.get("accel"),
            session.last.get("gyro"),
            session.last.get("orientation"),
        ]
        validators = [v for v in validators if v is not None and v is not primary_delta]
        vote = majority_validate_direction(primary=primary_delta, validators=validators)
        if vote.ok:
            dx, dy = _scale_move(source, primary_delta, session.sensitivity)
            mouse.move_relative(dx, dy)
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

    validators: list[MotionDelta] = []
    if session.enabled.get("accel") and (d := session.last.get("accel")) is not None:
        validators.append(d)
    if session.enabled.get("gyro") and (d := session.last.get("gyro")) is not None:
        validators.append(d)
    if session.enabled.get("orientation") and (d := session.last.get("orientation")) is not None:
        validators.append(d)

    vote = majority_validate_direction(primary=cam_delta, validators=validators)
    if not vote.ok:
        return

    dx, dy = _scale_move("camera", cam_delta, session.sensitivity)
    mouse.move_relative(dx, dy)
