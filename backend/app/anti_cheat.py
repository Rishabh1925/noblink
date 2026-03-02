"""
Anti-Cheat Engine — server-side validation of incoming landmark data.

Every frame streamed from the client is run through these checks before
the EAR calculation.  If any check fails, the session is flagged.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CheatFlag(str, Enum):
    """Reasons a frame or session may be flagged."""

    MISSING_LANDMARKS = "missing_landmarks"
    INVALID_COORDINATE_RANGE = "invalid_coordinate_range"
    EAR_OUT_OF_RANGE = "ear_out_of_range"
    LOW_FRAME_RATE = "low_frame_rate"
    FROZEN_LANDMARKS = "frozen_landmarks"


@dataclass
class ValidationResult:
    """Outcome of a single frame validation."""

    is_valid: bool
    flag: CheatFlag | None = None
    detail: str = ""


# ── Stateful Anti-Cheat Tracker ─────────────────────────────────────────────


@dataclass
class AntiCheatTracker:
    """
    Per-session tracker that accumulates frame-level stats for anti-cheat
    heuristics (frame rate, landmark freeze detection, etc.).
    """

    # tunables
    min_fps: float = 10.0
    freeze_frame_limit: int = 15

    # internal state
    _frame_count: int = field(default=0, init=False, repr=False)
    _last_frame_time: float = field(default=0.0, init=False, repr=False)
    _last_landmarks: list[dict] | None = field(default=None, init=False, repr=False)
    _identical_frame_count: int = field(default=0, init=False, repr=False)
    _cheat_flags: list[CheatFlag] = field(default_factory=list, init=False, repr=False)

    # ── Public API ───────────────────────────────────────────────────────────

    def validate_frame(
        self,
        left_eye: list[dict],
        right_eye: list[dict],
        ear_value: float | None = None,
    ) -> ValidationResult:
        """
        Run all validation checks on a single frame.

        Parameters
        ----------
        left_eye, right_eye : list[dict]
            The 6-landmark arrays for each eye.
        ear_value : float, optional
            Pre-computed EAR for range checking.

        Returns
        -------
        ValidationResult
        """
        # 1. Landmark completeness
        result = self._check_landmarks(left_eye, right_eye)
        if not result.is_valid:
            return result

        # 2. Coordinate range [0, 1]
        result = self._check_coordinate_range(left_eye + right_eye)
        if not result.is_valid:
            return result

        # 3. EAR physiological range
        if ear_value is not None:
            result = self._check_ear_range(ear_value)
            if not result.is_valid:
                return result

        # 4. Frame rate
        result = self._check_frame_rate()
        if not result.is_valid:
            return result

        # 5. Frozen landmarks
        all_landmarks = left_eye + right_eye
        result = self._check_frozen(all_landmarks)
        if not result.is_valid:
            return result

        # Update bookkeeping
        self._frame_count += 1
        self._last_frame_time = time.monotonic()
        self._last_landmarks = [dict(lm) for lm in all_landmarks]

        return ValidationResult(is_valid=True)

    @property
    def flags(self) -> list[CheatFlag]:
        return list(self._cheat_flags)

    # ── Private Checks ───────────────────────────────────────────────────────

    def _check_landmarks(
        self, left_eye: list[dict], right_eye: list[dict]
    ) -> ValidationResult:
        if len(left_eye) != 6 or len(right_eye) != 6:
            self._cheat_flags.append(CheatFlag.MISSING_LANDMARKS)
            return ValidationResult(
                is_valid=False,
                flag=CheatFlag.MISSING_LANDMARKS,
                detail=f"Expected 6+6 landmarks, got {len(left_eye)}+{len(right_eye)}",
            )
        for lm in left_eye + right_eye:
            if not all(k in lm for k in ("x", "y", "z")):
                self._cheat_flags.append(CheatFlag.MISSING_LANDMARKS)
                return ValidationResult(
                    is_valid=False,
                    flag=CheatFlag.MISSING_LANDMARKS,
                    detail="Landmark missing x/y/z keys",
                )
        return ValidationResult(is_valid=True)

    @staticmethod
    def _check_coordinate_range(landmarks: list[dict]) -> ValidationResult:
        for lm in landmarks:
            for axis in ("x", "y"):
                val = lm[axis]
                if not (-0.5 <= val <= 1.5):
                    return ValidationResult(
                        is_valid=False,
                        flag=CheatFlag.INVALID_COORDINATE_RANGE,
                        detail=f"Coordinate {axis}={val} out of plausible range",
                    )
        return ValidationResult(is_valid=True)

    @staticmethod
    def _check_ear_range(ear: float) -> ValidationResult:
        if not (0.02 <= ear <= 0.55):
            return ValidationResult(
                is_valid=False,
                flag=CheatFlag.EAR_OUT_OF_RANGE,
                detail=f"EAR={ear} outside physiological range [0.05, 0.45]",
            )
        return ValidationResult(is_valid=True)

    def _check_frame_rate(self) -> ValidationResult:
        now = time.monotonic()
        if self._last_frame_time > 0:
            elapsed = now - self._last_frame_time
            if elapsed > 0 and (1.0 / elapsed) < self.min_fps:
                # Only flag if we've received enough frames to judge reliably
                if self._frame_count > 10:
                    self._cheat_flags.append(CheatFlag.LOW_FRAME_RATE)
                    return ValidationResult(
                        is_valid=False,
                        flag=CheatFlag.LOW_FRAME_RATE,
                        detail=f"Frame rate dropped below {self.min_fps} FPS",
                    )
        return ValidationResult(is_valid=True)

    def _check_frozen(self, all_landmarks: list[dict]) -> ValidationResult:
        if self._last_landmarks is not None:
            is_identical = all(
                abs(a["x"] - b["x"]) < 1e-6
                and abs(a["y"] - b["y"]) < 1e-6
                and abs(a["z"] - b["z"]) < 1e-6
                for a, b in zip(all_landmarks, self._last_landmarks)
            )
            if is_identical:
                self._identical_frame_count += 1
            else:
                self._identical_frame_count = 0

            if self._identical_frame_count >= self.freeze_frame_limit:
                self._cheat_flags.append(CheatFlag.FROZEN_LANDMARKS)
                return ValidationResult(
                    is_valid=False,
                    flag=CheatFlag.FROZEN_LANDMARKS,
                    detail="Landmarks unchanged for "
                    f"{self._identical_frame_count} consecutive frames",
                )
        return ValidationResult(is_valid=True)
