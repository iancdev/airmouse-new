from __future__ import annotations

from dataclasses import dataclass

import pyautogui


@dataclass(frozen=True)
class MouseConfig:
    move_scale: float = 1.0
    scroll_scale: float = 1.0


class MouseController:
    def __init__(self, config: MouseConfig | None = None) -> None:
        self._config = config or MouseConfig()
        pyautogui.FAILSAFE = True

    def update_config(self, config: MouseConfig) -> None:
        self._config = config

    def move_relative(self, dx: float, dy: float) -> None:
        if dx == 0 and dy == 0:
            return
        pyautogui.moveRel(dx * self._config.move_scale, dy * self._config.move_scale, duration=0)

    def click(self, *, button: str, state: str) -> None:
        if button not in {"left", "right"}:
            raise ValueError(f"Invalid button: {button}")
        if state == "down":
            pyautogui.mouseDown(button=button)
            return
        if state == "up":
            pyautogui.mouseUp(button=button)
            return
        raise ValueError(f"Invalid click state: {state}")

    def scroll(self, delta: float) -> None:
        if delta == 0:
            return
        pyautogui.scroll(int(delta * self._config.scroll_scale))

