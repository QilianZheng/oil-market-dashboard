from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Tuple
from urllib.request import urlopen

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
SAMPLE_PRICE_PATH = RAW_DATA_DIR / "sample_prices.csv"
EVENTS_PATH = RAW_DATA_DIR / "events_sample.csv"

FRED_SERIES = {
    "DCOILWTICO": "wti_price",
    "DCOILBRENTEU": "brent_price",
}


def _clean_price_frame(frame: pd.DataFrame, data_mode: str, source_note: str) -> pd.DataFrame:
    prices = frame.rename(columns=FRED_SERIES).copy()
    prices.index = pd.to_datetime(prices.index)
    prices = prices.reset_index().rename(columns={"DATE": "date", "index": "date"})
    prices["date"] = pd.to_datetime(prices["date"])

    for column in ["wti_price", "brent_price"]:
        prices[column] = pd.to_numeric(prices[column], errors="coerce")

    prices = prices.dropna(subset=["wti_price", "brent_price"]).sort_values("date")
    prices["data_mode"] = data_mode
    prices["source_note"] = source_note
    return prices[["date", "wti_price", "brent_price", "data_mode", "source_note"]]


def load_sample_prices(path: Path | str = SAMPLE_PRICE_PATH) -> pd.DataFrame:
    """Load clearly labeled sample demo prices used when live FRED access fails."""
    prices = pd.read_csv(path, parse_dates=["date"])
    prices["data_mode"] = "sample_demo"
    prices["source_note"] = prices["source_note"].fillna("Sample demo data for portfolio reliability.")
    return prices.sort_values("date").reset_index(drop=True)


def _load_fred_with_pandas_datareader(start: date, end: date) -> pd.DataFrame:
    from pandas_datareader import data as web

    fred = web.DataReader(list(FRED_SERIES.keys()), "fred", start, end)
    return _clean_price_frame(
        fred,
        data_mode="live_fred",
        source_note="Live FRED daily crude oil price series: DCOILWTICO and DCOILBRENTEU.",
    )


def _load_fred_with_csv(start: date, end: date) -> pd.DataFrame:
    frames = []
    for series_id, output_name in FRED_SERIES.items():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        with urlopen(url, timeout=10) as response:
            frame = pd.read_csv(response)
        frame["observation_date"] = pd.to_datetime(frame["observation_date"])
        frame[series_id] = pd.to_numeric(frame[series_id], errors="coerce")
        frame = frame.rename(columns={"observation_date": "date", series_id: output_name})
        frames.append(frame[["date", output_name]])

    prices = frames[0].merge(frames[1], on="date", how="inner")
    mask = (prices["date"].dt.date >= start) & (prices["date"].dt.date <= end)
    prices = prices.loc[mask].dropna(subset=["wti_price", "brent_price"]).sort_values("date")
    prices["data_mode"] = "live_fred"
    prices["source_note"] = "Live FRED daily crude oil price series loaded from FRED CSV endpoints."
    return prices[["date", "wti_price", "brent_price", "data_mode", "source_note"]]


def load_fred_prices(
    start: date | None = None,
    end: date | None = None,
    fallback_path: Path | str = SAMPLE_PRICE_PATH,
) -> Tuple[pd.DataFrame, bool, str]:
    """
    Try to load daily WTI and Brent prices from FRED.

    Returns:
        price frame, live-data-success flag, user-facing status message.
    """
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=365)

    live_errors = []
    try:
        prices = _load_fred_with_pandas_datareader(start, end)
        if prices.empty:
            raise ValueError("FRED returned no usable WTI/Brent rows.")
        return prices, True, "Data Mode: Live FRED Data"
    except Exception as exc:
        live_errors.append(f"pandas_datareader failed with {type(exc).__name__}")

    try:
        prices = _load_fred_with_csv(start, end)
        if prices.empty:
            raise ValueError("FRED CSV endpoints returned no usable WTI/Brent rows.")
        return prices, True, "Data Mode: Live FRED Data"
    except Exception as exc:
        live_errors.append(f"FRED CSV failed with {type(exc).__name__}")

    sample = load_sample_prices(fallback_path)
    message = f"Data Mode: Sample Demo Data. Live FRED load failed: {'; '.join(live_errors)}."
    return sample, False, message


def load_events(path: Path | str = EVENTS_PATH) -> pd.DataFrame:
    """Load the manually curated sample event dataset."""
    events = pd.read_csv(path, parse_dates=["date"])
    return events.sort_values("date", ascending=False).reset_index(drop=True)
