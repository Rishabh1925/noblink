"""
ML Engine — Eye Aspect Ratio (EAR) calculation and blink detection.

The frontend runs MediaPipe Face Mesh in the browser and sends the 12 eye
landmark coordinates (6 per eye) to this module.  We compute EAR and use a
stateful detector to decide when a blink has occurred.

EAR formula (Soukupová & Čech, 2016):
    EAR = (||p2-p6|| + ||p3-p5||) / (2 · ||p1-p4||)

MediaPipe Face Mesh landmark indices used by the frontend:
    Left eye : [362, 385, 387, 263, 373, 380]
    Right eye: [33, 160, 158, 133, 153, 144]

Each landmark is sent as {"x": float, "y": float, "z": float} with values
normalised to [0, 1].
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings


# ── Helpers ──────────────────────────────────────────────────────────────────


def _distance(p1: dict, p2: dict) -> float:
    """Euclidean distance between two 3-D landmark points."""
    return math.sqrt(
        (p1["x"] - p2["x"]) ** 2
        + (p1["y"] - p2["y"]) ** 2
        + (p1["z"] - p2["z"]) ** 2
    )


# ── EAR Calculation ─────────────────────────────────────────────────────────


def calculate_ear(eye_landmarks: list[dict]) -> float:
    """
    Compute the Eye Aspect Ratio for a single eye.

    Parameters
    ----------
    eye_landmarks : list[dict]
        Exactly 6 landmark dicts with keys ``x``, ``y``, ``z`` in the order:
        [p1, p2, p3, p4, p5, p6] matching the standard EAR diagram.

    Returns
    -------
    float
        The EAR value.  Typically ~0.25-0.35 for open eyes, <0.20 for closed.
    """
    if len(eye_landmarks) != 6:
        raise ValueError(f"Expected 6 landmarks, got {len(eye_landmarks)}")

    p1, p2, p3, p4, p5, p6 = eye_landmarks

    # Vertical distances
    vertical_a = _distance(p2, p6)
    vertical_b = _distance(p3, p5)

    # Horizontal distance
    horizontal = _distance(p1, p4)

    if horizontal == 0:
        return 0.0

    ear = (vertical_a + vertical_b) / (2.0 * horizontal)
    return round(ear, 4)


def calculate_avg_ear(
    left_eye: list[dict],
    right_eye: list[dict],
) -> float:
    """Average EAR across both eyes."""
    left_ear = calculate_ear(left_eye)
    right_ear = calculate_ear(right_eye)
    return round((left_ear + right_ear) / 2.0, 4)


# ── Blink Detector (stateful, per-session) ───────────────────────────────────


@dataclass
class BlinkResult:
    """Result of processing a single frame."""

    is_blink: bool
    ear_value: float
    consecutive_low_frames: int


@dataclass
class BlinkDetector:
    """
    Stateful blink detector for a single game session.

    Tracks consecutive frames where EAR falls below the threshold and fires
    a blink event once ``ear_consec_frames`` consecutive low-EAR frames are
    observed.
    """

    threshold: float = field(default_factory=lambda: settings.ear_threshold)
    consec_frames_required: int = field(
        default_factory=lambda: settings.ear_consec_frames,
    )

    # internal state
    _consecutive_low: int = field(default=0, init=False, repr=False)
    _blink_detected: bool = field(default=False, init=False, repr=False)

    def reset(self) -> None:
        """Reset internal counters (e.g. for a new session)."""
        self._consecutive_low = 0
        self._blink_detected = False

    def process_frame(
        self,
        left_eye: list[dict],
        right_eye: list[dict],
    ) -> BlinkResult:
        """
        Feed one frame of eye landmarks.

        Returns
        -------
        BlinkResult
            ``is_blink`` is ``True`` the first time a confirmed blink is
            detected.  Subsequent calls continue to return ``True`` until
            ``reset()`` is called.
        """
        avg_ear = calculate_avg_ear(left_eye, right_eye)

        if avg_ear < self.threshold:
            self._consecutive_low += 1
        else:
            self._consecutive_low = 0

        if self._consecutive_low >= self.consec_frames_required:
            self._blink_detected = True

        return BlinkResult(
            is_blink=self._blink_detected,
            ear_value=avg_ear,
            consecutive_low_frames=self._consecutive_low,
        )
