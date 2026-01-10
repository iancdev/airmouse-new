from __future__ import annotations

from dataclasses import dataclass
import threading

import pyautogui


@dataclass(frozen=True)
class MouseConfig:
    move_scale: float = 1.0
    scroll_scale: float = 1.0


class MouseController:
    def __init__(self, config: MouseConfig | None = None) -> None:
        self._config = config or MouseConfig()
        self._lock = threading.Lock()
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0
        if hasattr(pyautogui, "MINIMUM_DURATION"):
            pyautogui.MINIMUM_DURATION = 0
        if hasattr(pyautogui, "MINIMUM_SLEEP"):
            pyautogui.MINIMUM_SLEEP = 0

    def update_config(self, config: MouseConfig) -> None:
        self._config = config

    def move_relative(self, dx: float, dy: float) -> None:
        if dx == 0 and dy == 0:
            return
        with self._lock:
            pyautogui.moveRel(dx * self._config.move_scale, dy * self._config.move_scale, duration=0)

    def click(self, *, button: str, state: str) -> None:
        if button not in {"left", "right"}:
            raise ValueError(f"Invalid button: {button}")
        if state == "down":
            with self._lock:
                pyautogui.mouseDown(button=button)
            return
        if state == "up":
            with self._lock:
                pyautogui.mouseUp(button=button)
            return
        raise ValueError(f"Invalid click state: {state}")

    def scroll(self, delta: float) -> None:
        if delta == 0:
            return
        with self._lock:
            pyautogui.scroll(int(delta * self._config.scroll_scale))
