from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.request import urlopen

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
VERIFIED_EVENTS_PATH = RAW_DATA_DIR / "verified_events.csv"
HISTORICAL_PRICE_CACHE_PATH = PROCESSED_DATA_DIR / "fred_prices_2020_2025.csv"
EVENT_WINDOW_RESULTS_PATH = PROCESSED_DATA_DIR / "event_window_results.csv"

HISTORICAL_START = date(2020, 1, 1)
HISTORICAL_END = date(2025, 12, 31)
RETURN_WINDOWS = [1, 3, 5, 10]
REQUIRED_RESULT_COLUMNS = [
    "wti_change_1d",
    "wti_change_3d",
    "wti_change_5d",
    "wti_change_10d",
    "brent_change_1d",
    "brent_change_3d",
    "brent_change_5d",
    "brent_change_10d",
    "wti_event_price",
    "brent_event_price",
    "wti_price_plus_5d",
    "brent_price_plus_5d",
    "wti_negative_price_window",
    "extreme_return_flag",
]
REQUIRED_EVENT_COLUMNS = [
    "event_id",
    "event_date",
    "event_title",
    "source_name",
    "source_url",
    "category",
    "expected_market_signal",
    "event_summary",
    "notes",
]


def load_verified_events(path: Path | str = VERIFIED_EVENTS_PATH) -> pd.DataFrame:
    """Load the user-provided verified historical event dataset."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            "Missing data/raw/verified_events.csv. Historical Validation Mode requires "
            "a user-provided verified historical event dataset."
        )

    events = pd.read_csv(path, parse_dates=["event_date"])
    missing_columns = [column for column in REQUIRED_EVENT_COLUMNS if column not in events.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"verified_events.csv is missing required columns: {missing}")

    events = events[REQUIRED_EVENT_COLUMNS].copy()
    events["source_url_present"] = events["source_url"].fillna("").astype(str).str.strip().ne("")
    return events.sort_values("event_date").reset_index(drop=True)


def _load_fred_series_csv(series_id: str, output_name: str) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urlopen(url, timeout=20) as response:
        frame = pd.read_csv(response)

    frame = frame.rename(columns={"observation_date": "date", series_id: output_name})
    frame["date"] = pd.to_datetime(frame["date"])
    frame[output_name] = pd.to_numeric(frame[output_name], errors="coerce")
    return frame[["date", output_name]].dropna()


def fetch_fred_historical_prices(
    start: date = HISTORICAL_START,
    end: date = HISTORICAL_END,
    cache_path: Path | str = HISTORICAL_PRICE_CACHE_PATH,
) -> pd.DataFrame:
    """
    Fetch actual historical FRED WTI and Brent data for the validation window.

    This function does not fall back to sample data. Historical validation should fail
    visibly if actual historical FRED data cannot be loaded.
    """
    wti = _load_fred_series_csv("DCOILWTICO", "wti_price")
    brent = _load_fred_series_csv("DCOILBRENTEU", "brent_price")
    prices = wti.merge(brent, on="date", how="inner")
    mask = (prices["date"].dt.date >= start) & (prices["date"].dt.date <= end)
    prices = prices.loc[mask].dropna(subset=["wti_price", "brent_price"]).sort_values("date")

    if prices.empty:
        raise ValueError("FRED returned no usable historical WTI/Brent rows for 2020-2025.")

    prices["data_mode"] = "historical_fred"
    prices["source_note"] = "Actual historical FRED WTI and Brent prices for 2020-01-01 through 2025-12-31."
    prices = prices[["date", "wti_price", "brent_price", "data_mode", "source_note"]].reset_index(drop=True)

    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(cache_path, index=False)
    return prices


def load_historical_prices(
    refresh: bool = False,
    cache_path: Path | str = HISTORICAL_PRICE_CACHE_PATH,
) -> pd.DataFrame:
    """Load cached historical FRED prices or fetch them from FRED."""
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        prices = pd.read_csv(cache_path, parse_dates=["date"])
        return prices.sort_values("date").reset_index(drop=True)
    return fetch_fred_historical_prices(cache_path=cache_path)


def align_event_to_price_date(event_date: pd.Timestamp, price_dates: pd.Series) -> pd.Timestamp | pd.NaT:
    """Align an event to the nearest available price date on or after the event date."""
    event_date = pd.to_datetime(event_date)
    future_dates = price_dates[price_dates >= event_date]
    if future_dates.empty:
        return pd.NaT
    return future_dates.iloc[0]


def _forward_return(prices: pd.DataFrame, row_position: int, price_col: str, window: int) -> float | None:
    target_position = row_position + window
    if target_position >= len(prices):
        return None

    start_price = prices.iloc[row_position][price_col]
    end_price = prices.iloc[target_position][price_col]
    if pd.isna(start_price) or pd.isna(end_price) or start_price == 0:
        return None
    return (end_price / start_price) - 1


def _forward_change(prices: pd.DataFrame, row_position: int, price_col: str, window: int) -> float | None:
    target_position = row_position + window
    if target_position >= len(prices):
        return None

    start_price = prices.iloc[row_position][price_col]
    end_price = prices.iloc[target_position][price_col]
    if pd.isna(start_price) or pd.isna(end_price):
        return None
    return end_price - start_price


def calculate_event_windows(events: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Calculate forward trading-day returns around verified events."""
    clean_prices = prices.sort_values("date").dropna(subset=["wti_price", "brent_price"]).reset_index(drop=True)
    clean_prices["brent_wti_spread"] = clean_prices["brent_price"] - clean_prices["wti_price"]
    price_dates = clean_prices["date"]
    date_to_position = {price_date: position for position, price_date in enumerate(price_dates)}

    results = events.copy()
    results["aligned_price_date"] = results["event_date"].apply(lambda value: align_event_to_price_date(value, price_dates))
    results["event_date_shifted"] = results["aligned_price_date"].ne(results["event_date"])

    for window in RETURN_WINDOWS:
        results[f"wti_return_{window}d"] = None
        results[f"brent_return_{window}d"] = None
        results[f"wti_change_{window}d"] = None
        results[f"brent_change_{window}d"] = None

    results["wti_event_price"] = None
    results["brent_event_price"] = None
    results["wti_price_plus_5d"] = None
    results["brent_price_plus_5d"] = None
    results["brent_wti_spread_change_5d"] = None
    results["wti_negative_price_window"] = False
    results["extreme_return_flag"] = False

    for index, row in results.iterrows():
        aligned_date = row["aligned_price_date"]
        if pd.isna(aligned_date) or aligned_date not in date_to_position:
            continue

        position = date_to_position[aligned_date]
        results.at[index, "wti_event_price"] = clean_prices.iloc[position]["wti_price"]
        results.at[index, "brent_event_price"] = clean_prices.iloc[position]["brent_price"]
        wti_window_prices = [clean_prices.iloc[position]["wti_price"]]

        for window in RETURN_WINDOWS:
            results.at[index, f"wti_return_{window}d"] = _forward_return(clean_prices, position, "wti_price", window)
            results.at[index, f"brent_return_{window}d"] = _forward_return(clean_prices, position, "brent_price", window)
            results.at[index, f"wti_change_{window}d"] = _forward_change(clean_prices, position, "wti_price", window)
            results.at[index, f"brent_change_{window}d"] = _forward_change(clean_prices, position, "brent_price", window)

            target_position = position + window
            if target_position < len(clean_prices):
                wti_window_prices.append(clean_prices.iloc[target_position]["wti_price"])

        target_position = position + 5
        if target_position < len(clean_prices):
            results.at[index, "wti_price_plus_5d"] = clean_prices.iloc[target_position]["wti_price"]
            results.at[index, "brent_price_plus_5d"] = clean_prices.iloc[target_position]["brent_price"]
            start_spread = clean_prices.iloc[position]["brent_wti_spread"]
            end_spread = clean_prices.iloc[target_position]["brent_wti_spread"]
            results.at[index, "brent_wti_spread_change_5d"] = end_spread - start_spread

        results.at[index, "wti_negative_price_window"] = any(
            pd.notna(price) and price <= 0 for price in wti_window_prices
        )
        wti_return_5d = results.at[index, "wti_return_5d"]
        wti_return_10d = results.at[index, "wti_return_10d"]
        results.at[index, "extreme_return_flag"] = (
            (pd.notna(wti_return_5d) and abs(wti_return_5d) > 1)
            or (pd.notna(wti_return_10d) and abs(wti_return_10d) > 1)
        )

    numeric_columns = [
        "wti_return_1d",
        "wti_return_3d",
        "wti_return_5d",
        "wti_return_10d",
        "brent_return_1d",
        "brent_return_3d",
        "brent_return_5d",
        "brent_return_10d",
        "wti_change_1d",
        "wti_change_3d",
        "wti_change_5d",
        "wti_change_10d",
        "brent_change_1d",
        "brent_change_3d",
        "brent_change_5d",
        "brent_change_10d",
        "wti_event_price",
        "brent_event_price",
        "wti_price_plus_5d",
        "brent_price_plus_5d",
        "brent_wti_spread_change_5d",
    ]
    for column in numeric_columns:
        results[column] = pd.to_numeric(results[column], errors="coerce")

    return results


def build_event_window_results(
    events_path: Path | str = VERIFIED_EVENTS_PATH,
    refresh_prices: bool = False,
    output_path: Path | str = EVENT_WINDOW_RESULTS_PATH,
) -> pd.DataFrame:
    """Load verified events and historical FRED prices, calculate windows, and save results."""
    events = load_verified_events(events_path)
    prices = load_historical_prices(refresh=refresh_prices)
    results = calculate_event_windows(events, prices)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_path, index=False)
    return results


def load_or_build_event_window_results(refresh_prices: bool = False) -> pd.DataFrame:
    """Load processed event-window results if available, otherwise build them."""
    if EVENT_WINDOW_RESULTS_PATH.exists() and not refresh_prices:
        results = pd.read_csv(
            EVENT_WINDOW_RESULTS_PATH,
            parse_dates=["event_date", "aligned_price_date"],
        )
        if "source_verified" in results.columns and "source_url_present" not in results.columns:
            results = results.rename(columns={"source_verified": "source_url_present"})
        if any(column not in results.columns for column in REQUIRED_RESULT_COLUMNS):
            return build_event_window_results(refresh_prices=False)
        return results
    return build_event_window_results(refresh_prices=refresh_prices)


def event_window_results_are_stale(
    events_path: Path | str = VERIFIED_EVENTS_PATH,
    results_path: Path | str = EVENT_WINDOW_RESULTS_PATH,
) -> bool:
    """Return True when verified_events.csv is newer than processed event-window results."""
    events_path = Path(events_path)
    results_path = Path(results_path)
    if not events_path.exists() or not results_path.exists():
        return False
    return events_path.stat().st_mtime > results_path.stat().st_mtime
