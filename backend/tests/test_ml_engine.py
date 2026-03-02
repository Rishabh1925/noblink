"""
Unit tests for the ML Engine — EAR calculation and blink detection.
"""

import math

import pytest

from app.ml_engine import BlinkDetector, calculate_avg_ear, calculate_ear


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_landmark(x: float, y: float, z: float = 0.0) -> dict:
    return {"x": x, "y": y, "z": z}


def _open_eye_landmarks() -> list[dict]:
    """
    Simulated open-eye landmarks (EAR ≈ 0.30).

    Layout (roughly):
        p1 ---- p4    (horizontal)
         p2  p3       (upper lid — above center)
         p6  p5       (lower lid — below center)
    """
    return [
        _make_landmark(0.0, 0.0),   # p1 — left corner
        _make_landmark(0.2, 0.15),  # p2 — upper-left
        _make_landmark(0.4, 0.15),  # p3 — upper-right
        _make_landmark(0.6, 0.0),   # p4 — right corner
        _make_landmark(0.4, -0.15), # p5 — lower-right
        _make_landmark(0.2, -0.15), # p6 — lower-left
    ]


def _closed_eye_landmarks() -> list[dict]:
    """
    Simulated closed-eye landmarks (EAR ≈ 0.07).

    The vertical points collapse towards the horizontal axis.
    """
    return [
        _make_landmark(0.0, 0.0),    # p1
        _make_landmark(0.2, 0.02),   # p2 — barely above
        _make_landmark(0.4, 0.02),   # p3
        _make_landmark(0.6, 0.0),    # p4
        _make_landmark(0.4, -0.02),  # p5 — barely below
        _make_landmark(0.2, -0.02),  # p6
    ]


# ── Test EAR Calculation ────────────────────────────────────────────────────


class TestCalculateEAR:
    def test_open_eye_ear_above_threshold(self):
        ear = calculate_ear(_open_eye_landmarks())
        assert ear > 0.20, f"Open eye EAR should be > 0.20, got {ear}"

    def test_closed_eye_ear_below_threshold(self):
        ear = calculate_ear(_closed_eye_landmarks())
        assert ear < 0.15, f"Closed eye EAR should be < 0.15, got {ear}"

    def test_wrong_number_of_landmarks(self):
        with pytest.raises(ValueError, match="Expected 6"):
            calculate_ear([_make_landmark(0, 0)] * 3)

    def test_identical_points_returns_zero(self):
        same = [_make_landmark(0.5, 0.5)] * 6
        ear = calculate_ear(same)
        assert ear == 0.0

    def test_symmetry(self):
        """EAR should be the same regardless of left/right mirroring."""
        lms = _open_eye_landmarks()
        ear_normal = calculate_ear(lms)
        # Mirror horizontally
        mirrored = [_make_landmark(1.0 - lm["x"], lm["y"], lm["z"]) for lm in lms]
        ear_mirror = calculate_ear(mirrored)
        assert abs(ear_normal - ear_mirror) < 0.01


class TestCalculateAvgEAR:
    def test_avg_both_open(self):
        avg = calculate_avg_ear(_open_eye_landmarks(), _open_eye_landmarks())
        assert avg > 0.20

    def test_avg_both_closed(self):
        avg = calculate_avg_ear(_closed_eye_landmarks(), _closed_eye_landmarks())
        assert avg < 0.15

    def test_avg_is_mean(self):
        left = calculate_ear(_open_eye_landmarks())
        right = calculate_ear(_closed_eye_landmarks())
        avg = calculate_avg_ear(_open_eye_landmarks(), _closed_eye_landmarks())
        expected = (left + right) / 2.0
        assert abs(avg - expected) < 0.001


# ── Test Blink Detector ─────────────────────────────────────────────────────


class TestBlinkDetector:
    def test_no_blink_with_open_eyes(self):
        detector = BlinkDetector(threshold=0.21, consec_frames_required=2)
        open_lms = _open_eye_landmarks()

        for _ in range(30):
            result = detector.process_frame(open_lms, open_lms)
            assert result.is_blink is False

    def test_blink_detected_after_consecutive_closed(self):
        detector = BlinkDetector(threshold=0.21, consec_frames_required=2)
        closed_lms = _closed_eye_landmarks()

        # Frame 1: below threshold, but not enough consecutive
        r1 = detector.process_frame(closed_lms, closed_lms)
        assert r1.is_blink is False
        assert r1.consecutive_low_frames == 1

        # Frame 2: still below → blink confirmed
        r2 = detector.process_frame(closed_lms, closed_lms)
        assert r2.is_blink is True
        assert r2.consecutive_low_frames == 2

    def test_blink_not_triggered_with_intermittent_open(self):
        detector = BlinkDetector(threshold=0.21, consec_frames_required=3)
        open_lms = _open_eye_landmarks()
        closed_lms = _closed_eye_landmarks()

        # closed → open → closed → should NOT trigger (interrupted)
        detector.process_frame(closed_lms, closed_lms)
        detector.process_frame(open_lms, open_lms)  # reset
        result = detector.process_frame(closed_lms, closed_lms)
        assert result.is_blink is False

    def test_reset_clears_state(self):
        detector = BlinkDetector(threshold=0.21, consec_frames_required=2)
        closed_lms = _closed_eye_landmarks()

        detector.process_frame(closed_lms, closed_lms)
        detector.process_frame(closed_lms, closed_lms)
        assert detector._blink_detected is True

        detector.reset()
        assert detector._blink_detected is False
        assert detector._consecutive_low == 0

    def test_blink_detected_stays_true(self):
        """Once a blink is detected, subsequent frames still report True."""
        detector = BlinkDetector(threshold=0.21, consec_frames_required=2)
        closed_lms = _closed_eye_landmarks()
        open_lms = _open_eye_landmarks()

        detector.process_frame(closed_lms, closed_lms)
        detector.process_frame(closed_lms, closed_lms)

        # Even with open eyes after, blink stays True
        result = detector.process_frame(open_lms, open_lms)
        assert result.is_blink is True
