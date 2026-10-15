"""
measure_forecast.py
───────────────────
Evaluates cost forecasting accuracy using the canonical held-out split (20%, min 3 days)
on the 45-day synthetic demo history, matching services/ml_predictor.py.
Imports actual functions from services.ml_predictor and services.cost_estimator.
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(line_buffering=True)

from config import get_settings
settings = get_settings()
settings.demo_mode = True

from database import SessionLocal
from models.account import CloudAccount
from models.user import User
from models.cost_record import CostRecord
from services.cost_estimator import seed_historical_data
from services.ml_predictor import (
    _load_total_data,
    _held_out_size,
    _train_poly,
    _predict_poly,
    _train_hw,
    _predict_hw,
    _mape,
    _rmse,
)

def run_forecast_benchmark():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            user = User(email="demo@example.com", password_hash="dummy")
            db.add(user)
            db.commit()
            db.refresh(user)

        account_id = "00000000-0000-0000-0000-demoaccount01"
        acc = db.query(CloudAccount).filter(CloudAccount.id == account_id).first()
        if not acc:
            acc = CloudAccount(
                id=account_id,
                user_id=user.id,
                name="Demo_AWS_Account",
                provider="aws",
                region="us-east-1",
                access_key_id="DEMO_KEY",
                encrypted_secret_key="",
            )
            db.add(acc)
            db.commit()

        # Seed 45 days if needed
        seed_historical_data(db, account_id, days=45, min_days_threshold=100)

        # Load total daily aggregated data using actual ml_predictor loader
        X, y, dates = _load_total_data(db, [account_id])
        n = len(X)
        held_out = _held_out_size(n)
        train_end = n - held_out

        X_tr, y_tr = X[:train_end], y[:train_end]
        X_ho, y_ho = X[train_end:], y[train_end:]

        # 1. Model 1: Polynomial Regression (degree 2) using real functions
        m_poly = _train_poly(X_tr, y_tr)
        p_poly = _predict_poly(m_poly, X_ho)
        poly_mape = _mape(y_ho, p_poly)
        poly_rmse = _rmse(y_ho, p_poly)
        poly_mae = float(np.mean(np.abs(y_ho - p_poly)))

        # 2. Model 2: Holt's Double Exponential Smoothing using real functions
        m_hw = _train_hw(y_tr)
        p_hw = _predict_hw(m_hw, held_out)
        hw_mape = _mape(y_ho, p_hw)
        hw_rmse = _rmse(y_ho, p_hw)
        hw_mae = float(np.mean(np.abs(y_ho - p_hw)))

        winner = "Holt-Winters" if hw_mape < poly_mape else "Polynomial Regression (degree 2)"

        print("=" * 70)
        print("RAW MEASURED OUTPUT: FORECAST ACCURACY BENCHMARK")
        print("DATA SOURCE: Synthetic Demo Data (seed_historical_data, 45-day horizon)")
        print("=" * 70)
        print(f"Total Dataset Days      : {n}")
        print(f"Training Window Days    : {train_end} (dates: {dates[0]} to {dates[train_end-1]})")
        print(f"Held-Out Split Days     : {held_out} (dates: {dates[train_end]} to {dates[-1]}) [20% split rule]")
        print("-" * 70)
        print(f"{'Model':<30} | {'MAE ($)':<10} | {'RMSE ($)':<10} | {'MAPE (%)':<10}")
        print("-" * 70)
        print(f"{'Polynomial (Degree 2)':<30} | {poly_mae:<10.4f} | {poly_rmse:<10.4f} | {poly_mape:<10.2f}%")
        print(f"{'Holt-Winters Smoothing':<30} | {hw_mae:<10.4f} | {hw_rmse:<10.4f} | {hw_mape:<10.2f}%")
        print("-" * 70)
        print(f"Tournament Winner       : {winner} (Selected by lowest MAPE)")
        print("=" * 70)

    finally:
        db.close()

if __name__ == "__main__":
    run_forecast_benchmark()
