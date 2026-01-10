from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import cv2
import numpy as np

from .mouse import MouseConfig, MouseController
from .protocol import parse_client_msg
from .imu import ImuTracker
from .vision import VisionTracker

logger = logging.getLogger("airmouse")

DEFAULT_ENABLED = {"camera": False, "accel": True, "gyro": False, "orientation": False}

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


@dataclass
class ClientSession:
    sensitivity: float = 1.0
    camera_fps: int = 15
    enabled: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_ENABLED))
    pending_frame_meta: dict | None = None
    vision: VisionTracker = field(default_factory=VisionTracker)
    imu: ImuTracker = field(default_factory=ImuTracker)


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

        enabled = msg.raw.get("enabled")
        if isinstance(enabled, dict):
            for key in DEFAULT_ENABLED:
                val = enabled.get(key)
                if isinstance(val, bool):
                    session.enabled[key] = val

        mouse.update_config(MouseConfig(move_scale=session.sensitivity, scroll_scale=session.sensitivity))
        session.pending_frame_meta = None
        session.vision.reset()
        session.imu.reset()
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
            delta = session.imu.process_sample(msg.raw)
            if delta.valid:
                mouse.move_relative(delta.dx * session.sensitivity, delta.dy * session.sensitivity)
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

    mime = meta.get("mime")
    if not isinstance(mime, str) or not mime.startswith("image/"):
        return

    buf = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if frame is None:
        return

    delta = session.vision.process_bgr(frame)
    if not delta.valid:
        return

    # Heuristic scaling: the vision delta is in downscaled pixels.
    dx = delta.dx * 4.0 * session.sensitivity
    dy = delta.dy * 4.0 * session.sensitivity
    mouse.move_relative(dx, dy)
