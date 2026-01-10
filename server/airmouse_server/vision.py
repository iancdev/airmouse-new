from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class VisionDelta:
    dx: float
    dy: float
    valid: bool
    num_points: int


class VisionTracker:
    def __init__(
        self,
        *,
        max_corners: int = 250,
        quality_level: float = 0.01,
        min_distance: int = 7,
        min_points: int = 20,
    ) -> None:
        self._max_corners = max_corners
        self._quality_level = quality_level
        self._min_distance = min_distance
        self._min_points = min_points
        self._prev_gray: np.ndarray | None = None
        self._prev_pts: np.ndarray | None = None

    def reset(self) -> None:
        self._prev_gray = None
        self._prev_pts = None

    def _detect_features(self, gray: np.ndarray) -> np.ndarray | None:
        return cv2.goodFeaturesToTrack(
            gray,
            maxCorners=self._max_corners,
            qualityLevel=self._quality_level,
            minDistance=self._min_distance,
            blockSize=7,
        )

    def process_bgr(self, frame_bgr: np.ndarray) -> VisionDelta:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)

        if self._prev_gray is None:
            self._prev_gray = gray
            self._prev_pts = self._detect_features(gray)
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=0)

        if self._prev_pts is None or len(self._prev_pts) < self._min_points:
            self._prev_pts = self._detect_features(self._prev_gray)

        if self._prev_pts is None:
            self._prev_gray = gray
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=0)

        next_pts, status, _err = cv2.calcOpticalFlowPyrLK(self._prev_gray, gray, self._prev_pts, None)
        if next_pts is None or status is None:
            self._prev_gray = gray
            self._prev_pts = None
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=0)

        status_mask = status.reshape(-1) == 1
        good_prev = self._prev_pts.reshape(-1, 2)[status_mask]
        good_next = next_pts.reshape(-1, 2)[status_mask]

        if len(good_prev) < self._min_points:
            self._prev_gray = gray
            self._prev_pts = None
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=int(len(good_prev)))

        diffs = good_next - good_prev
        dx, dy = np.median(diffs, axis=0)

        self._prev_gray = gray
        self._prev_pts = good_next.reshape(-1, 1, 2)

        # Invert: desk texture moves opposite the phone movement.
        return VisionDelta(dx=float(-dx), dy=float(-dy), valid=True, num_points=int(len(good_prev)))

