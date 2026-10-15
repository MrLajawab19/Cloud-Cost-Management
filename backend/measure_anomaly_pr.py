"""
measure_anomaly_pr.py
─────────────────────
Evaluates anomaly detection precision, recall, F1-score, and confusion matrix
by injecting known ground-truth anomalies (spikes and drops) into a synthetic cost stream
and executing the actual rolling 14-day Z-score (|z| >= 2.5) algorithm from services/anomaly_detector.py.
"""

import sys
import os
import numpy as np
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(line_buffering=True)

from services.anomaly_detector import _detect_for_service, _compute_fitted, LOOKBACK_DAYS, Z_THRESHOLD

def run_anomaly_pr_benchmark():
    np.random.seed(42)
    n_days = 60
    base_date = date(2026, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(n_days)]
    
    # 1. Clean synthetic baseline: baseline cost + weekly seasonality + Gaussian noise
    t = np.arange(n_days, dtype=float)
    base_cost = 100.0
    trend = 0.35 * t
    seasonality = 7.5 * np.sin(2 * np.pi * t / 7)
    noise_sigma = 1.5  # 1.5% of base
    noise = np.random.normal(0, noise_sigma, n_days)
    costs = base_cost + trend + seasonality + noise

    # 2. Inject ground-truth anomalies (spikes and drops)
    ground_truth = {d: 0 for d in dates}
    injected_events = [
        (18, +45.0, "spike"),
        (25, -35.0, "drop"),
        (34, +80.0, "spike (critical)"),
        (42, +55.0, "spike"),
        (50, -40.0, "drop"),
        (56, +65.0, "spike"),
    ]
    for idx, delta, label in injected_events:
        costs[idx] += delta
        ground_truth[dates[idx]] = 1

    # 3. Fit in-sample baseline using actual anomaly_detector function
    fitted_vals = _compute_fitted(t, costs, n_days)

    # 4. Build residual dictionary: actual - fitted
    residuals = {dates[i]: float(costs[i] - fitted_vals[i]) for i in range(n_days)}

    # 5. Run actual anomaly detector from services.anomaly_detector
    detected_anomalies = _detect_for_service("EC2", residuals)
    detected_dates = {a["record_date"] for a in detected_anomalies}

    # 6. Evaluate metrics only on eligible evaluation window (after initial rolling lookback)
    eval_dates = dates[LOOKBACK_DAYS:]
    tp = sum(1 for d in eval_dates if ground_truth[d] == 1 and d in detected_dates)
    fp = sum(1 for d in eval_dates if ground_truth[d] == 0 and d in detected_dates)
    fn = sum(1 for d in eval_dates if ground_truth[d] == 1 and d not in detected_dates)
    tn = sum(1 for d in eval_dates if ground_truth[d] == 0 and d not in detected_dates)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    total_eval = len(eval_dates)
    total_injected = sum(1 for d in eval_dates if ground_truth[d] == 1)

    print("=" * 70)
    print("RAW MEASURED OUTPUT: ANOMALY DETECTION BENCHMARK")
    print("ALGORITHM   : services/anomaly_detector.py (Rolling 14-day Z-Score >= 2.5 + IQR)")
    print("=" * 70)
    print("TEST SETUP SPECIFICATIONS:")
    print(f"  • Total Time Series Points   : {n_days} days")
    print(f"  • Rolling Lookback Window    : {LOOKBACK_DAYS} days")
    print(f"  • Evaluated Points Window    : {total_eval} days (Day {LOOKBACK_DAYS} to {n_days})")
    print(f"  • Noise Level Added (sigma)  : {noise_sigma} USD (std dev of Gaussian noise)")
    print(f"  • Injected Anomalies (Ground): {total_injected} events ({len(injected_events)} total across series)")
    print("-" * 70)
    print("CONFUSION MATRIX:")
    print(f"                      Predicted Anomaly    Predicted Normal")
    print(f"  Actual Anomaly (P):      TP = {tp:<5}           FN = {fn:<5}")
    print(f"  Actual Normal  (N):      FP = {fp:<5}           TN = {tn:<5}")
    print("-" * 70)
    print("MEASURED CLASSIFICATION METRICS:")
    print(f"  • Precision : {precision * 100:.2f}% ({tp}/{tp + fp})")
    print(f"  • Recall    : {recall * 100:.2f}% ({tp}/{tp + fn})")
    print(f"  • F1-Score  : {f1 * 100:.2f}%")
    print(f"  • Specificity: {(tn / (tn + fp)) * 100:.2f}% ({tn}/{tn + fp})")
    print("=" * 70)

if __name__ == "__main__":
    run_anomaly_pr_benchmark()
