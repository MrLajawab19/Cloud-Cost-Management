"""
services/anomaly_detector.py
─────────────────────────────
Implements FR-3 (Anomaly Detection) in full:

  FR-3.1  Flag cost that deviates from the FR-2 forecast baseline
  FR-3.2  Uses FR-2 forecast as the baseline; residuals derive the uncertainty band
  FR-3.3  Unsupervised detection: Z-score (primary) + IQR (secondary)
  FR-3.4  Cross-references FR-2.4 attribution to name the driver service
  FR-3.5  Results persisted to DB for the dashboard anomaly feed

Algorithm
─────────
For each service independently:
  1. Load actual daily costs from cost_records (historical window)
  2. Build per-service forecast using the same FR-2 Holt/Poly models
  3. Compute residuals = actual − forecast on overlapping dates
  4. Rolling Z-score: z = residual / rolling_std (lookback=LOOKBACK_DAYS)
  5. IQR check: flag if residual > Q3 + 1.5*IQR  or  < Q1 − 1.5*IQR
  6. Keep only |z| ≥ Z_THRESHOLD (2.5) → 'warning' or 'critical'
  7. Attach driver_service from get_service_attribution() — shared with FR-2.4

Resolution contract (Point 2, user-confirmed)
─────────────────────────────────────────────
Upsert key: (account_id, service_type, record_date)
  - Row exists, is_resolved=True  → SKIP (never resurrect a dismissed anomaly)
  - Row exists, is_resolved=False → UPDATE z_score/residual/severity only
  - No existing row              → INSERT
"""

import logging
import numpy as np
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.cost_record import CostRecord
from models.anomaly import Anomaly
from services.ml_predictor import (
    _load_per_service_data,
    _train_hw, _predict_hw,
    _train_poly, _predict_poly,
    get_service_attribution,
    MIN_TRAINING_DAYS, PREDICT_DAYS,
)

logger = logging.getLogger(__name__)

# ── Detection constants ───────────────────────────────────────────
Z_THRESHOLD      = 2.5   # |z| below this → not anomalous, row NOT stored
Z_CRITICAL       = 3.5   # |z| above this → 'critical'; between → 'warning'
LOOKBACK_DAYS    = 14    # rolling window for mean/std computation
MIN_RESIDUALS    = 7     # minimum residual points needed to compute reliable stats


# ══════════════════════════════════════════════════════════════════
#  INTERNAL: FORECAST AGAINST ACTUAL (FR-3.1 / FR-3.2)
# ══════════════════════════════════════════════════════════════════

def _build_residuals(
    service_data: Dict[str, Tuple[np.ndarray, np.ndarray, List[date]]],
) -> Dict[str, Dict[date, float]]:
    """
    For each service, fit the same model as FR-2 and compute
    residuals = actual − forecast on all historical dates.

    Returns: {service → {date → residual}}
    """
    service_residuals: Dict[str, Dict[date, float]] = {}

    for svc, (X, y, dates) in service_data.items():
        n = len(X)
        if n < MIN_TRAINING_DAYS:
            logger.debug("_build_residuals: %s has only %d days — skipping.", svc, n)
            continue

        # Use the same model selection logic as FR-2 per-service
        try:
            if n >= 14:
                model  = _train_hw(y)
                fitted = model.forecast(n)   # in-sample forecast for all points
                # Holt's in-sample: iterate manually to get per-step one-ahead predictions
                # (re-run smoothing to get fitted values for residual computation)
                lvl   = float(y[0])
                trend_v = float(y[1] - y[0]) if n > 1 else 0.0
                fitted_vals = []
                for t in range(n):
                    fitted_vals.append(lvl + trend_v)
                    if t < n - 1:
                        prev_lvl   = lvl
                        prev_trend = trend_v
                        lvl   = model.alpha * float(y[t]) + (1 - model.alpha) * (prev_lvl + prev_trend)
                        trend_v = model.beta  * (lvl - prev_lvl) + (1 - model.beta) * prev_trend
                fitted_arr = np.maximum(np.array(fitted_vals), 0.0)
            else:
                m          = _train_poly(X, y)
                fitted_arr = np.maximum(m.predict(X.reshape(-1, 1)), 0.0)
        except Exception as e:
            logger.warning("_build_residuals: model failed for %s: %s", svc, e)
            continue

        residuals = {}
        for i, d in enumerate(dates):
            residuals[d] = float(y[i]) - float(fitted_arr[i])

        service_residuals[svc] = residuals

    return service_residuals


# ══════════════════════════════════════════════════════════════════
#  INTERNAL: Z-SCORE + IQR DETECTION (FR-3.3)
# ══════════════════════════════════════════════════════════════════

def _detect_for_service(
    svc: str,
    residuals: Dict[date, float],
) -> List[Dict[str, Any]]:
    """
    Apply Z-score (primary) and IQR (secondary) detection to one service's
    residual series.

    Returns list of anomaly dicts for dates where |z| ≥ Z_THRESHOLD.
    Rows with |z| < Z_THRESHOLD are NOT returned — confirmed Point 3.
    """
    sorted_dates = sorted(residuals.keys())
    n = len(sorted_dates)
    if n < MIN_RESIDUALS:
        return []

    results = []
    resid_arr = np.array([residuals[d] for d in sorted_dates])

    # IQR bounds (global, for secondary flagging)
    q1, q3     = np.percentile(resid_arr, [25, 75])
    iqr        = q3 - q1
    upper_iqr  = q3 + 1.5 * iqr
    lower_iqr  = q1 - 1.5 * iqr

    for i, d in enumerate(sorted_dates):
        # Rolling window: use the LOOKBACK_DAYS points before this date (exclusive)
        # This avoids data leakage — we only use past residuals to calibrate stats
        window_start = max(0, i - LOOKBACK_DAYS)
        window       = resid_arr[window_start:i]   # excludes current point

        if len(window) < 3:
            # Not enough history to compute reliable rolling stats
            continue

        mean_r = float(np.mean(window))
        std_r  = float(np.std(window))

        if std_r < 1e-9:
            # Perfectly constant history (e.g. all-seeded flat data) → no anomaly
            continue

        resid    = float(resid_arr[i])
        z        = (resid - mean_r) / std_r
        abs_z    = abs(z)

        # POINT 3 — filter: |z| < 2.5 → skip, row is NOT stored
        if abs_z < Z_THRESHOLD:
            continue

        # Classify severity
        severity  = "critical" if abs_z >= Z_CRITICAL else "warning"
        direction = "spike" if resid > 0 else "drop"
        iqr_flag  = resid > upper_iqr or resid < lower_iqr

        results.append({
            "service_type": svc,
            "record_date":  d,
            "residual":     round(resid, 6),
            "z_score":      round(z, 4),
            "iqr_flagged":  iqr_flag,
            "severity":     severity,
            "direction":    direction,
        })

    return results


# ══════════════════════════════════════════════════════════════════
#  INTERNAL: UPSERT WITH RESOLUTION PROTECTION (FR-3 Point 2)
# ══════════════════════════════════════════════════════════════════

def _upsert_anomalies(
    db: Session,
    account_id: str,
    detections: List[Dict[str, Any]],
    driver_map: Dict[str, str],
    actual_cost_map: Dict[Tuple[str, date], float],
    forecast_cost_map: Dict[Tuple[str, date], float],
) -> Tuple[int, int, int]:
    """
    Upsert anomaly rows with resolution protection.

    Resolution contract (confirmed Point 2):
      - is_resolved=True  → row is SKIPPED — user dismissal is permanent
      - is_resolved=False → UPDATE z_score, residual, severity, direction, iqr_flagged
      - No existing row   → INSERT new

    Returns: (inserted, updated, skipped_resolved)
    """
    inserted = updated = skipped = 0

    for det in detections:
        svc       = det["service_type"]
        rec_date  = det["record_date"]

        existing = (
            db.query(Anomaly)
            .filter(
                Anomaly.account_id   == account_id,
                Anomaly.service_type == svc,
                Anomaly.record_date  == rec_date,
            )
            .first()
        )

        if existing is not None:
            if existing.is_resolved:
                # POINT 2: user dismissed this — NEVER flip back to unresolved
                skipped += 1
                continue
            # Update mutable detection fields only (not resolution state)
            existing.residual      = det["residual"]
            existing.z_score       = det["z_score"]
            existing.iqr_flagged   = det["iqr_flagged"]
            existing.severity      = det["severity"]
            existing.direction     = det["direction"]
            existing.actual_cost   = actual_cost_map.get((svc, rec_date), 0.0)
            existing.forecast_cost = forecast_cost_map.get((svc, rec_date), 0.0)
            existing.driver_service = driver_map.get(svc, svc)
            updated += 1
        else:
            row = Anomaly(
                account_id     = account_id,
                service_type   = svc,
                record_date    = rec_date,
                actual_cost    = actual_cost_map.get((svc, rec_date), 0.0),
                forecast_cost  = forecast_cost_map.get((svc, rec_date), 0.0),
                residual       = det["residual"],
                z_score        = det["z_score"],
                iqr_flagged    = det["iqr_flagged"],
                severity       = det["severity"],
                direction      = det["direction"],
                driver_service = driver_map.get(svc, svc),
                is_resolved    = False,
            )
            db.add(row)
            inserted += 1

    db.commit()
    return inserted, updated, skipped


# ══════════════════════════════════════════════════════════════════
#  PUBLIC: DETECT AND PERSIST (FR-3 entry point)
# ══════════════════════════════════════════════════════════════════

def detect_anomalies(db: Session, account_ids: List[str]) -> Dict[str, int]:
    """
    Full FR-3 detection pipeline for all given accounts.

    Steps:
      1. Load per-service actuals from cost_records
      2. Build residuals = actual − in-sample forecast (FR-3.2)
      3. Z-score + IQR detection; only |z| ≥ 2.5 kept (FR-3.3)
      4. Attach driver_service from get_service_attribution() (FR-3.4)
      5. Upsert with resolution protection into anomalies table (FR-3.1)

    Returns totals dict: {account_id → total_inserted+updated}.
    """
    totals: Dict[str, int] = {}

    for account_id in account_ids:
        logger.info("FR-3 detect_anomalies: account %s", account_id[:8])

        # ── 1. Load actuals ──────────────────────────────────────
        service_data = _load_per_service_data(db, [account_id])
        if not service_data:
            logger.info("FR-3: no service data for account %s — skipping.", account_id[:8])
            totals[account_id] = 0
            continue

        # ── 2. Build residuals ───────────────────────────────────
        service_residuals = _build_residuals(service_data)
        if not service_residuals:
            logger.info("FR-3: insufficient data to build residuals for account %s.", account_id[:8])
            totals[account_id] = 0
            continue

        # ── 3. Detect ────────────────────────────────────────────
        all_detections: List[Dict[str, Any]] = []
        for svc, residuals in service_residuals.items():
            dets = _detect_for_service(svc, residuals)
            all_detections.extend(dets)

        if not all_detections:
            logger.info("FR-3: no anomalies above threshold for account %s.", account_id[:8])
            totals[account_id] = 0
            continue

        # ── 4. Driver attribution (shared with FR-2.4) ───────────
        attribution = get_service_attribution(db, [account_id])
        # Map: service → driver (highest-attribution service for multi-service cases)
        # For per-service anomalies: driver IS the service itself (single-service spike)
        driver_map: Dict[str, str] = {a["service"]: a["service"] for a in attribution}
        # Top attributor for TOTAL anomalies (if added in future)
        top_driver = attribution[0]["service"] if attribution else "Unknown"
        driver_map["TOTAL"] = top_driver

        # ── 5. Build lookup maps for actual/forecast costs ───────
        actual_cost_map: Dict[Tuple[str, date], float] = {}
        forecast_cost_map: Dict[Tuple[str, date], float] = {}

        for svc, (X, y, dates) in service_data.items():
            for i, d in enumerate(dates):
                actual_cost_map[(svc, d)] = float(y[i])

        # Forecast cost = actual − residual (residual already computed above)
        for svc, residuals in service_residuals.items():
            for d, resid in residuals.items():
                act = actual_cost_map.get((svc, d), 0.0)
                forecast_cost_map[(svc, d)] = act - resid

        # ── 6. Upsert with resolution protection ─────────────────
        ins, upd, skp = _upsert_anomalies(
            db, account_id, all_detections, driver_map,
            actual_cost_map, forecast_cost_map,
        )
        logger.info(
            "FR-3 account %s: detected=%d inserted=%d updated=%d skipped_resolved=%d",
            account_id[:8], len(all_detections), ins, upd, skp,
        )
        totals[account_id] = ins + upd

    return totals


# ══════════════════════════════════════════════════════════════════
#  PUBLIC: READ ANOMALIES (for API route)
# ══════════════════════════════════════════════════════════════════

def get_anomalies(
    db: Session,
    account_ids: List[str],
    days: int = 30,
    severity: Optional[str] = None,
    include_resolved: bool = False,
) -> List[Anomaly]:
    """
    Fetch stored anomalies from DB for the given accounts.

    Args:
      days             — look back this many days from today
      severity         — filter by 'warning' or 'critical' (None = both)
      include_resolved — if False (default), exclude is_resolved=True rows
    """
    cutoff = date.today() - timedelta(days=days)
    q = (
        db.query(Anomaly)
        .filter(
            Anomaly.account_id.in_(account_ids),
            Anomaly.record_date >= cutoff,
        )
        .order_by(Anomaly.record_date.desc())
    )
    if severity:
        q = q.filter(Anomaly.severity == severity)
    if not include_resolved:
        q = q.filter(Anomaly.is_resolved == False)
    return q.all()


def get_anomaly_summary(
    db: Session,
    account_ids: List[str],
    days: int = 30,
) -> Dict[str, Any]:
    """
    Aggregate summary for the dashboard widget (FR-3.5).

    Returns: total, warning_count, critical_count, top_driver, recent_critical
    """
    anomalies = get_anomalies(db, account_ids, days=days, include_resolved=False)

    warning_count  = sum(1 for a in anomalies if a.severity == "warning")
    critical_count = sum(1 for a in anomalies if a.severity == "critical")

    # Top driver = service with most critical anomalies (fallback: most warnings)
    from collections import Counter
    driver_counts = Counter(
        a.driver_service for a in anomalies
        if a.driver_service and not a.is_resolved
    )
    top_driver = driver_counts.most_common(1)[0][0] if driver_counts else None

    recent_critical = [
        {
            "service_type": a.service_type,
            "record_date":  str(a.record_date),
            "z_score":      a.z_score,
            "direction":    a.direction,
        }
        for a in anomalies
        if a.severity == "critical"
    ][:5]

    return {
        "total":            len(anomalies),
        "warning_count":    warning_count,
        "critical_count":   critical_count,
        "top_driver":       top_driver,
        "recent_critical":  recent_critical,
        "window_days":      days,
    }
