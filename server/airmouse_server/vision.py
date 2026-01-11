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
        max_corners: int = 400,
        quality_level: float = 0.01,
        min_distance: int = 5,
        min_points: int = 30,
        resize_scale: float = 1.0,
        max_err: float = 12.0,
        fb_thresh: float = 1.5,
    ) -> None:
        self._max_corners = max_corners
        self._quality_level = quality_level
        self._min_distance = min_distance
        self._min_points = min_points
        self._resize_scale = resize_scale
        self._max_err = max_err
        self._fb_thresh = fb_thresh
        self._prev_gray: np.ndarray | None = None
        self._prev_pts: np.ndarray | None = None
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

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
        if self._resize_scale != 1.0:
            gray = cv2.resize(
                gray,
                (0, 0),
                fx=self._resize_scale,
                fy=self._resize_scale,
                interpolation=cv2.INTER_AREA,
            )
        gray = self._clahe.apply(gray)

        if self._prev_gray is None:
            self._prev_gray = gray
            self._prev_pts = self._detect_features(gray)
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=0)

        if self._prev_pts is None or len(self._prev_pts) < self._min_points:
            self._prev_pts = self._detect_features(self._prev_gray)

        if self._prev_pts is None:
            self._prev_gray = gray
            self._prev_pts = self._detect_features(gray)
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=0)

        next_pts, status, err = cv2.calcOpticalFlowPyrLK(
            self._prev_gray,
            gray,
            self._prev_pts,
            None,
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )
        if next_pts is None or status is None or err is None:
            self._prev_gray = gray
            self._prev_pts = None
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=0)

        status_mask = status.reshape(-1) == 1
        err_mask = err.reshape(-1) <= self._max_err
        mask = status_mask & err_mask
        if not np.any(mask):
            self._prev_gray = gray
            self._prev_pts = None
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=0)

        prev_pts = self._prev_pts.reshape(-1, 2)[mask]
        next_pts_flat = next_pts.reshape(-1, 2)[mask]

        back_pts, back_status, _back_err = cv2.calcOpticalFlowPyrLK(
            gray,
            self._prev_gray,
            next_pts_flat.reshape(-1, 1, 2),
            None,
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )
        if back_pts is None or back_status is None:
            self._prev_gray = gray
            self._prev_pts = None
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=0)

        back_ok = back_status.reshape(-1) == 1
        back_pts_flat = back_pts.reshape(-1, 2)
        fb_err = np.linalg.norm(prev_pts - back_pts_flat, axis=1)
        fb_mask = back_ok & (fb_err <= self._fb_thresh)
        if not np.any(fb_mask):
            self._prev_gray = gray
            self._prev_pts = None
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=0)

        good_prev = prev_pts[fb_mask]
        good_next = next_pts_flat[fb_mask]

        if len(good_prev) < self._min_points:
            self._prev_gray = gray
            self._prev_pts = None
            return VisionDelta(dx=0.0, dy=0.0, valid=False, num_points=int(len(good_prev)))

        dx = dy = None
        if len(good_prev) >= 6:
            affine, inliers = cv2.estimateAffinePartial2D(
                good_prev,
                good_next,
                method=cv2.RANSAC,
                ransacReprojThreshold=3.0,
                maxIters=2000,
                confidence=0.99,
            )
            if affine is not None and inliers is not None:
                inlier_mask = inliers.reshape(-1) == 1
                inlier_count = int(np.count_nonzero(inlier_mask))
                if inlier_count >= self._min_points:
                    dx = float(affine[0, 2])
                    dy = float(affine[1, 2])
                    good_prev = good_prev[inlier_mask]
                    good_next = good_next[inlier_mask]

        if dx is None or dy is None:
            diffs = good_next - good_prev
            dx, dy = np.median(diffs, axis=0)

        self._prev_gray = gray
        self._prev_pts = good_next.reshape(-1, 1, 2)

        # Invert: desk texture moves opposite the phone movement.
        return VisionDelta(dx=float(-dx), dy=float(-dy), valid=True, num_points=int(len(good_prev)))
