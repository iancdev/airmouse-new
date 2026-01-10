from __future__ import annotations

import json
import logging
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .mouse import MouseConfig, MouseController
from .protocol import parse_client_msg

logger = logging.getLogger("airmouse")


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
        try:
            while True:
                message = await ws.receive()
                if "text" in message and message["text"] is not None:
                    await _handle_text_message(ws, message["text"], mouse)
                elif "bytes" in message and message["bytes"] is not None:
                    await ws.send_text(json.dumps({"t": "error", "message": "Binary frames not supported yet"}))
        except WebSocketDisconnect:
            return
        except Exception as exc:
            logger.exception("WebSocket error: %s", exc)
            try:
                await ws.send_text(json.dumps({"t": "error", "message": str(exc)}))
            except Exception:
                pass

    return app


async def _handle_text_message(
    ws: WebSocket,
    text: str,
    mouse: MouseController,
) -> None:
    payload = json.loads(text)
    msg = parse_client_msg(payload)

    if msg.t == "hello":
        await ws.send_text(json.dumps({"t": "server.state", "ok": True}))
        return

    if msg.t == "config":
        sensitivity = float(msg.raw.get("sensitivity", 1.0))
        mouse.update_config(MouseConfig(move_scale=sensitivity, scroll_scale=sensitivity))
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

    await ws.send_text(json.dumps({"t": "error", "message": f"Unknown message type: {msg.t}"}))
