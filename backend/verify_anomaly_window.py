"""
backend/verify_anomaly_window.py
Verification script for M2.a:
1. Tests that rolling window requires at least MIN_RESIDUALS (7) points.
2. Synthetic series with a spike at index 25 is flagged.
3. Nothing is flagged in the first 7 points (indices 0..6).
4. A flat series stays unflagged.
5. Compares results with OLD window threshold (3) vs NEW window threshold (MIN_RESIDUALS=7).
"""

import sys
import os
import numpy as np
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.anomaly_detector import _detect_for_service, MIN_RESIDUALS, LOOKBACK_DAYS

def run_test():
    print(f"MIN_RESIDUALS = {MIN_RESIDUALS}")
    assert MIN_RESIDUALS == 7, f"Expected MIN_RESIDUALS == 7, got {MIN_RESIDUALS}"

    # Build 35 days of dates
    base_date = date(2026, 9, 1)
    dates = [base_date + timedelta(days=i) for i in range(35)]

    # 1. Flat series
    flat_residuals = {d: 0.0 for d in dates}
    flat_res = _detect_for_service("EC2", flat_residuals)
    print(f"Flat series anomalies count: {len(flat_res)}")
    assert len(flat_res) == 0, "Flat series should have 0 anomalies"

    # 2. Synthetic series with steady noise and a spike at index 25
    np.random.seed(42)
    residuals = {}
    for i, d in enumerate(dates):
        if i == 25:
            residuals[d] = 20.0  # Big spike
        else:
            residuals[d] = float(np.sin(i * 0.5) * 0.5)

    # Run with NEW window (MIN_RESIDUALS = 7)
    new_res = _detect_for_service("EC2", residuals)
    print(f"\n[NEW window={MIN_RESIDUALS}] Detected anomalies: {len(new_res)}")
    for a in new_res:
        idx = dates.index(a["record_date"])
        print(f"  - index={idx} date={a['record_date']} z={a['z_score']} sev={a['severity']}")

    # Assertions for new window:
    # Spike at index 25 must be flagged
    spike_hit = [a for a in new_res if dates.index(a["record_date"]) == 25]
    assert len(spike_hit) == 1, "Spike at index 25 was not flagged!"
    print("PASS: Spike at index 25 is flagged.")

    # Nothing flagged in the first 7 points (indices 0..6)
    early_hits = [a for a in new_res if dates.index(a["record_date"]) < MIN_RESIDUALS]
    assert len(early_hits) == 0, f"Anomalies found in first {MIN_RESIDUALS} points: {early_hits}"
    print(f"PASS: Nothing is flagged in the first {MIN_RESIDUALS} points.")

    # 3. Compare with OLD window (window < 3)
    # Temporarily patch MIN_RESIDUALS to 3
    with patch("services.anomaly_detector.MIN_RESIDUALS", 3):
        old_res = _detect_for_service("EC2", residuals)

    print(f"\n[OLD window=3] Detected anomalies: {len(old_res)}")
    for a in old_res:
        idx = dates.index(a["record_date"])
        print(f"  - index={idx} date={a['record_date']} z={a['z_score']} sev={a['severity']}")

    old_early_hits = [a for a in old_res if dates.index(a["record_date"]) < 7]
    print(f"Old window flagged {len(old_early_hits)} anomalies in first 7 points, New window flagged {len(early_hits)}.")

    print("\nVERIFY_ANOMALY_WINDOW COMPLETE: ALL TESTS PASSED.")

if __name__ == "__main__":
    run_test()
