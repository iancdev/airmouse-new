from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict


class ClientEnabled(TypedDict, total=False):
    camera: bool
    accel: bool
    gyro: bool
    orientation: bool


class HelloMsg(TypedDict):
    t: Literal["hello"]
    clientVersion: str
    device: str | None


class ConfigMsg(TypedDict):
    t: Literal["config"]
    sensitivity: float
    cameraFps: int
    enabled: ClientEnabled
    screenAngle: int


class ClickMsg(TypedDict):
    t: Literal["input.click"]
    button: Literal["left", "right"]
    state: Literal["down", "up"]


class ScrollMsg(TypedDict):
    t: Literal["input.scroll"]
    delta: float


class MoveDeltaMsg(TypedDict):
    t: Literal["move.delta"]
    dx: float
    dy: float


class ImuSampleMsg(TypedDict, total=False):
    t: Literal["imu.sample"]
    ts: float
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    alpha: float
    beta: float
    gamma: float


class CamFrameMetaMsg(TypedDict):
    t: Literal["cam.frame"]
    seq: int
    ts: float
    width: int
    height: int
    mime: str


ClientMsg = HelloMsg | ConfigMsg | ClickMsg | ScrollMsg | MoveDeltaMsg | ImuSampleMsg | CamFrameMetaMsg


@dataclass
class ParsedMsg:
    t: str
    raw: dict[str, Any]


def parse_client_msg(payload: Any) -> ParsedMsg:
    if not isinstance(payload, dict):
        raise ValueError("Client message must be a JSON object")
    msg_type = payload.get("t")
    if not isinstance(msg_type, str):
        raise ValueError("Missing or invalid 't' field")
    return ParsedMsg(t=msg_type, raw=payload)
