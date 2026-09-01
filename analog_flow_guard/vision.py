from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

from .config import DetectorConfig


def circular_distance(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


@dataclass(frozen=True)
class ImageQuality:
    score: float
    sharpness: float
    contrast: float
    clipped_ratio: float
    warning: str | None


@dataclass(frozen=True)
class NeedleDetection:
    angle_deg: float
    confidence: float
    endpoint: tuple[int, int]


def assess_image_quality(gray: np.ndarray) -> ImageQuality:
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast = float(np.std(gray))
    clipped_ratio = float(np.mean((gray <= 3) | (gray >= 252)))
    sharpness_score = np.clip(sharpness / 120.0, 0.0, 1.0)
    contrast_score = np.clip(contrast / 55.0, 0.0, 1.0)
    exposure_score = np.clip(1.0 - clipped_ratio / 0.55, 0.0, 1.0)
    score = float(100.0 * (0.45 * sharpness_score + 0.35 * contrast_score + 0.20 * exposure_score))
    warning = None
    if sharpness < 18:
        warning = "초점/흔들림 확인"
    elif contrast < 12:
        warning = "침과 배경 대비 부족"
    elif clipped_ratio > 0.45:
        warning = "노출/반사광 확인"
    return ImageQuality(score, sharpness, contrast, clipped_ratio, warning)


def _robust_z(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    scale = max(1e-5, 1.4826 * mad, float(np.std(values)) * 0.25)
    return (values - median) / scale


def _circular_smooth(values: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    if kernel_size <= 1:
        return values
    radius = kernel_size // 2
    kernel = cv2.getGaussianKernel(kernel_size, 1.0).reshape(-1)
    padded = np.concatenate([values[-radius:], values, values[:radius]])
    return np.convolve(padded, kernel, mode="valid").astype(np.float32)


class NeedleDetector:
    """Detects a needle using polar continuity, contrast, and temporal evidence."""

    def __init__(self, config: DetectorConfig) -> None:
        self.config = config
        self.previous_angle: float | None = None
        self.last_quality: ImageQuality | None = None
        # CLAHE setup is invariant; constructing it for every frame creates
        # avoidable allocations and contributes to preview stutter.
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def reset(self) -> None:
        self.previous_angle = None
        self.last_quality = None

    def detect(
        self,
        frame: np.ndarray,
        center: tuple[float, float],
        radius: float,
        angle_allowed: Callable[[float], bool] | None = None,
    ) -> NeedleDetection | None:
        if frame.size == 0 or radius < 10:
            self.last_quality = None
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame.copy()
        self.last_quality = assess_image_quality(gray)
        if self.last_quality.score < self.config.minimum_image_quality:
            return None
        if self.config.polar_mode:
            return self._detect_polar(gray, center, radius, angle_allowed)
        return self._detect_radial(gray, center, radius, angle_allowed)

    def _detect_polar(
        self,
        gray: np.ndarray,
        center: tuple[float, float],
        radius: float,
        angle_allowed: Callable[[float], bool] | None,
    ) -> NeedleDetection | None:
        enhanced = self._clahe.apply(gray)
        enhanced = cv2.GaussianBlur(enhanced, (3, 3), 0)
        inner = max(1, int(radius * self.config.radial_min_ratio))
        outer = max(inner + 6, int(radius * self.config.radial_max_ratio))
        angular_samples = max(180, int(round(360.0 / self.config.angle_step_deg)))
        polar = cv2.warpPolar(
            enhanced,
            (outer + 1, angular_samples),
            center,
            outer,
            cv2.WARP_POLAR_LINEAR | cv2.INTER_LINEAR,
        )
        annulus = 255.0 - polar[:, inner : outer + 1].astype(np.float32)
        radial_baseline = np.median(annulus, axis=0, keepdims=True)
        residual = np.maximum(annulus - radial_baseline, 0.0)
        mean_darkness = np.mean(annulus, axis=1)
        residual_mean = np.mean(residual, axis=1)
        band_scores = [np.mean(band, axis=1) for band in np.array_split(residual, 6, axis=1)]
        radial_continuity = np.percentile(np.stack(band_scores, axis=1), 30, axis=1)
        angular_edges = np.mean(np.abs(cv2.Sobel(annulus, cv2.CV_32F, 0, 1, ksize=3)), axis=1)
        score = (
            0.75 * _robust_z(mean_darkness)
            + 1.00 * _robust_z(residual_mean)
            + 0.85 * _robust_z(radial_continuity)
            + 0.25 * _robust_z(angular_edges)
        )
        score = _circular_smooth(score, 5)
        angles = np.arange(angular_samples, dtype=np.float32) * (360.0 / angular_samples)
        return self._choose_candidate(score, angles, center, outer, angle_allowed)

    def _detect_radial(
        self,
        gray: np.ndarray,
        center: tuple[float, float],
        radius: float,
        angle_allowed: Callable[[float], bool] | None,
    ) -> NeedleDetection | None:
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        darkness = 255.0 - gray.astype(np.float32)
        inner = max(1, int(radius * self.config.radial_min_ratio))
        outer = max(inner + 1, int(radius * self.config.radial_max_ratio))
        radii = np.arange(inner, outer + 1, dtype=np.float32)
        angles = np.arange(0.0, 360.0, self.config.angle_step_deg, dtype=np.float32)
        scores = np.empty(len(angles), dtype=np.float32)
        cx, cy = center
        for index, angle in enumerate(angles):
            radians = np.deg2rad(angle)
            tangent_x, tangent_y = -np.sin(radians), np.cos(radians)
            strips = []
            for offset in range(-self.config.line_half_width_px, self.config.line_half_width_px + 1):
                xs = np.rint(cx + radii * np.cos(radians) + offset * tangent_x).astype(int)
                ys = np.rint(cy + radii * np.sin(radians) + offset * tangent_y).astype(int)
                valid = (xs >= 0) & (xs < gray.shape[1]) & (ys >= 0) & (ys < gray.shape[0])
                if np.any(valid):
                    strips.append(darkness[ys[valid], xs[valid]])
            scores[index] = float(np.mean(np.concatenate(strips))) if strips else 0.0
        return self._choose_candidate(_robust_z(scores), angles, center, outer, angle_allowed)

    def _choose_candidate(
        self,
        raw_score: np.ndarray,
        angles: np.ndarray,
        center: tuple[float, float],
        outer: int,
        angle_allowed: Callable[[float], bool] | None,
    ) -> NeedleDetection | None:
        allowed = np.ones(len(angles), dtype=bool)
        if angle_allowed is not None:
            allowed = np.asarray([angle_allowed(float(angle)) for angle in angles], dtype=bool)
            if not np.any(allowed):
                return None
        score = raw_score.astype(np.float32).copy()
        finite_scale = float(np.std(score[allowed]))
        if self.previous_angle is not None and self.config.continuity_weight > 0:
            distances = np.asarray([circular_distance(float(a), self.previous_angle) for a in angles])
            continuity = np.clip(1.0 - distances / 60.0, 0.0, 1.0)
            score += continuity.astype(np.float32) * finite_scale * self.config.continuity_weight
        score[~allowed] = -np.inf
        best_index = int(np.argmax(score))
        best_angle = float(angles[best_index] % 360.0)
        allowed_values = raw_score[allowed]
        confidence = float((raw_score[best_index] - np.median(allowed_values)) / (np.std(allowed_values) + 1e-6))
        if confidence < self.config.confidence_threshold:
            return None
        self.previous_angle = best_angle
        cx, cy = center
        endpoint = (
            int(round(cx + outer * np.cos(np.deg2rad(best_angle)))),
            int(round(cy + outer * np.sin(np.deg2rad(best_angle)))),
        )
        return NeedleDetection(best_angle, confidence, endpoint)


class CircularMovingAverage:
    def __init__(self, window_size: int) -> None:
        self.values: deque[float] = deque(maxlen=max(1, window_size))

    def add(self, angle_deg: float) -> float:
        self.values.append(angle_deg)
        radians = np.deg2rad(np.asarray(self.values, dtype=float))
        return float(np.rad2deg(np.arctan2(np.mean(np.sin(radians)), np.mean(np.cos(radians)))) % 360.0)

    def clear(self) -> None:
        self.values.clear()
