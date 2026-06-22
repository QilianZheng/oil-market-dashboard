from __future__ import annotations

import numpy as np
import pandas as pd


def add_price_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Create portfolio-ready market features from daily WTI and Brent prices."""
    df = prices.copy().sort_values("date").reset_index(drop=True)

    for price_col, prefix in [("wti_price", "wti"), ("brent_price", "brent")]:
        df[f"{prefix}_daily_return"] = df[price_col].pct_change()
        df[f"{prefix}_ma_7"] = df[price_col].rolling(window=7, min_periods=3).mean()
        df[f"{prefix}_ma_30"] = df[price_col].rolling(window=30, min_periods=10).mean()
        df[f"{prefix}_price_change_7d"] = df[price_col].diff(7)
        df[f"{prefix}_price_change_30d"] = df[price_col].diff(30)
        df[f"{prefix}_rolling_volatility_7d"] = (
            df[f"{prefix}_daily_return"].rolling(window=7, min_periods=3).std() * np.sqrt(252)
        )

    df["brent_wti_spread"] = df["brent_price"] - df["wti_price"]
    return df


def latest_market_snapshot(features: pd.DataFrame) -> dict:
    """Return the latest feature row as a plain dict for dashboard metrics and briefs."""
    if features.empty:
        return {}
    latest = features.sort_values("date").iloc[-1]
    return latest.to_dict()
