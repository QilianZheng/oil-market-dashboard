from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.brief_generator import generate_market_brief
from src.data_loader import load_events, load_sample_prices
from src.event_classifier import classify_events
from src.event_study import (
    build_event_window_results,
    event_window_results_are_stale,
    load_historical_prices,
    load_or_build_event_window_results,
)
from src.feature_engineering import add_price_features, latest_market_snapshot


SAMPLE_MODE = "Sample Demo Scenario"
HISTORICAL_MODE = "Historical Validation Mode"


st.set_page_config(
    page_title="Oil Market Intelligence Dashboard",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def get_sample_mode_data():
    prices = load_sample_prices()
    features = add_price_features(prices)
    events = classify_events(load_events())
    return prices, features, events


@st.cache_data(show_spinner=False)
def get_historical_prices(refresh_prices: bool = False):
    prices = load_historical_prices(refresh=refresh_prices)
    features = add_price_features(prices)
    return prices, features


@st.cache_data(show_spinner=False)
def get_historical_event_windows(rebuild_results: bool = False):
    if rebuild_results:
        return build_event_window_results(refresh_prices=False)
    return load_or_build_event_window_results(refresh_prices=False)


def metric_delta(value) -> str | None:
    if pd.isna(value):
        return None
    return f"{value:+.2f}"


def percent_label(value) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:.2%}"


def mode_banner(mode: str) -> None:
    if mode == SAMPLE_MODE:
        st.info(
            "Mode: Sample Demo Scenario\n\n"
            "Sample Demo Scenario - sample prices and sample events are used for portfolio demonstration. "
            "This mode uses sample data for reliable portfolio demonstration."
        )
    else:
        st.info(
            "Mode: Historical Validation Mode\n\n"
            "This mode uses actual historical FRED WTI/Brent price data from 2020-01-01 through "
            "2025-12-31 and a user-provided verified event dataset."
        )


def executive_monitor(features: pd.DataFrame, events: pd.DataFrame, mode: str) -> None:
    st.title("AI-Assisted Oil Market Intelligence Dashboard")
    st.caption("Portfolio analytics dashboard for crude oil prices, event classification, and analyst-style briefs.")
    mode_banner(mode)

    snapshot = latest_market_snapshot(features)
    if not snapshot:
        st.error("No market data available.")
        return

    cols = st.columns(4)
    cols[0].metric("WTI Price", f"${snapshot['wti_price']:.2f}", metric_delta(snapshot.get("wti_price_change_7d")))
    cols[1].metric("Brent Price", f"${snapshot['brent_price']:.2f}", metric_delta(snapshot.get("brent_price_change_7d")))
    cols[2].metric("Brent-WTI Spread", f"${snapshot['brent_wti_spread']:.2f}")
    cols[3].metric(
        "WTI 7D Volatility",
        "n/a" if pd.isna(snapshot.get("wti_rolling_volatility_7d")) else f"{snapshot['wti_rolling_volatility_7d']:.1%}",
    )

    recent = features.tail(60)
    line = px.line(
        recent,
        x="date",
        y=["wti_price", "brent_price"],
        labels={"value": "USD per barrel", "date": "Date", "variable": "Series"},
        title="Recent WTI and Brent Prices",
    )
    st.plotly_chart(line, use_container_width=True)

    st.subheader("Market Status Summary")
    if "market_signal" in events.columns and not events.empty:
        latest_signal = events["market_signal"].value_counts().idxmax()
        st.write(
            f"The latest monitored price window shows WTI at ${snapshot['wti_price']:.2f} and Brent at "
            f"${snapshot['brent_price']:.2f}. The current event set leans **{latest_signal}** based on "
            "the available curated labels."
        )
    elif "expected_market_signal" in events.columns and not events.empty:
        latest_signal = events["expected_market_signal"].value_counts().idxmax()
        st.write(
            f"The historical validation dataset contains {len(events):,} verified event rows. The most common "
            f"expected market signal is **{latest_signal}**."
        )
    else:
        st.write("No event rows are available for this mode.")


def price_trends(features: pd.DataFrame) -> None:
    st.title("Price Trends")

    price_fig = go.Figure()
    price_fig.add_trace(go.Scatter(x=features["date"], y=features["wti_price"], name="WTI"))
    price_fig.add_trace(go.Scatter(x=features["date"], y=features["brent_price"], name="Brent"))
    price_fig.add_trace(go.Scatter(x=features["date"], y=features["wti_ma_7"], name="WTI 7D MA", line_dash="dot"))
    price_fig.add_trace(go.Scatter(x=features["date"], y=features["brent_ma_7"], name="Brent 7D MA", line_dash="dot"))
    price_fig.add_trace(go.Scatter(x=features["date"], y=features["wti_ma_30"], name="WTI 30D MA", line_dash="dash"))
    price_fig.add_trace(go.Scatter(x=features["date"], y=features["brent_ma_30"], name="Brent 30D MA", line_dash="dash"))
    price_fig.update_layout(title="Crude Oil Prices and Moving Averages", yaxis_title="USD per barrel")
    st.plotly_chart(price_fig, use_container_width=True)

    cols = st.columns(2)
    vol_fig = px.line(
        features,
        x="date",
        y=["wti_rolling_volatility_7d", "brent_rolling_volatility_7d"],
        title="Rolling Volatility",
        labels={"value": "Annualized volatility", "variable": "Series"},
    )
    cols[0].plotly_chart(vol_fig, use_container_width=True)

    spread_fig = px.line(
        features,
        x="date",
        y="brent_wti_spread",
        title="Brent-WTI Spread",
        labels={"brent_wti_spread": "USD per barrel"},
    )
    cols[1].plotly_chart(spread_fig, use_container_width=True)


def sample_event_intelligence(events: pd.DataFrame) -> pd.DataFrame:
    st.title("Event Intelligence")
    st.caption("Sample demo event rows are synthetic scenarios or clearly labeled portfolio examples.")

    cols = st.columns(3)
    categories = cols[0].multiselect("Category", sorted(events["category"].dropna().unique()))
    signals = cols[1].multiselect("Market Signal", sorted(events["market_signal"].dropna().unique()))
    record_types = cols[2].multiselect("Record Type", sorted(events["record_type"].dropna().unique()))

    filtered = events.copy()
    if categories:
        filtered = filtered[filtered["category"].isin(categories)]
    if signals:
        filtered = filtered[filtered["market_signal"].isin(signals)]
    if record_types:
        filtered = filtered[filtered["record_type"].isin(record_types)]

    chart_cols = st.columns(2)
    category_counts = filtered["category"].value_counts().reset_index()
    category_counts.columns = ["category", "count"]
    chart_cols[0].plotly_chart(px.bar(category_counts, x="category", y="count", title="Events by Category"), use_container_width=True)

    signal_counts = filtered["market_signal"].value_counts().reset_index()
    signal_counts.columns = ["market_signal", "count"]
    chart_cols[1].plotly_chart(px.bar(signal_counts, x="market_signal", y="count", title="Events by Signal"), use_container_width=True)

    st.dataframe(
        filtered[
            [
                "date",
                "headline",
                "source",
                "category",
                "market_signal",
                "rule_based_category",
                "rule_based_market_signal",
                "record_type",
                "summary",
                "url",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
    return filtered


def historical_event_intelligence(event_windows: pd.DataFrame) -> pd.DataFrame:
    st.title("Event Intelligence")
    st.caption("Verified historical event rows supplied by the user for descriptive validation.")

    cols = st.columns(4)
    categories = cols[0].multiselect("Category", sorted(event_windows["category"].dropna().unique()))
    signals = cols[1].multiselect("Expected Market Signal", sorted(event_windows["expected_market_signal"].dropna().unique()))
    sources = cols[2].multiselect("Source Name", sorted(event_windows["source_name"].dropna().unique()))
    source_url_present = cols[3].multiselect("Source URL Provided", [True, False], default=[True, False])

    filtered = event_windows.copy()
    if categories:
        filtered = filtered[filtered["category"].isin(categories)]
    if signals:
        filtered = filtered[filtered["expected_market_signal"].isin(signals)]
    if sources:
        filtered = filtered[filtered["source_name"].isin(sources)]
    filtered = filtered[filtered["source_url_present"].isin(source_url_present)]

    chart_cols = st.columns(2)
    category_counts = filtered["category"].value_counts().reset_index()
    category_counts.columns = ["category", "count"]
    chart_cols[0].plotly_chart(px.bar(category_counts, x="category", y="count", title="Verified Events by Category"), use_container_width=True)

    signal_counts = filtered["expected_market_signal"].value_counts().reset_index()
    signal_counts.columns = ["expected_market_signal", "count"]
    chart_cols[1].plotly_chart(
        px.bar(signal_counts, x="expected_market_signal", y="count", title="Verified Events by Expected Signal"),
        use_container_width=True,
    )

    st.dataframe(filtered, use_container_width=True, hide_index=True)
    return filtered


def ai_daily_brief(features: pd.DataFrame, events: pd.DataFrame, mode: str) -> None:
    st.title("AI Daily Brief")
    st.info(
        "MVP note: this brief is generated with transparent template logic and curated/rule-based labels. "
        "It is not a trained trading model."
    )

    if mode == SAMPLE_MODE:
        selected_signals = st.multiselect(
            "Include signals",
            sorted(events["market_signal"].dropna().unique()),
            default=list(events["market_signal"].dropna().unique()),
        )
        selected_categories = st.multiselect(
            "Include categories",
            sorted(events["category"].dropna().unique()),
            default=list(events["category"].dropna().unique()),
        )
        filtered = events[
            events["market_signal"].isin(selected_signals)
            & events["category"].isin(selected_categories)
        ]
        st.markdown(generate_market_brief(features, filtered))
        return

    st.warning(
        "Historical Validation Mode uses verified historical event rows and event-window returns. "
        "The sample brief generator is intentionally not used to claim causal or trading conclusions."
    )
    st.write(
        "Use the Historical Event Study page for the descriptive event-window readout. "
        "A production version could later add retrieval-augmented or LLM-assisted narrative generation, "
        "but that is outside this MVP."
    )


def historical_event_study(event_windows: pd.DataFrame) -> None:
    st.title("Historical Event Study")
    st.info(
        "This section uses verified historical oil-market events and actual FRED WTI/Brent price data "
        "from 2020-2025 to examine event-window price reactions. Results are descriptive and do not prove causality."
    )
    st.warning(
        "WTI percentage returns around April 2020 may be distorted by the negative-price anomaly. "
        "Dollar changes and Brent returns are shown as robustness checks."
    )

    cols = st.columns(4)
    categories = cols[0].multiselect("Category", sorted(event_windows["category"].dropna().unique()), key="study_category")
    signals = cols[1].multiselect(
        "Expected Market Signal",
        sorted(event_windows["expected_market_signal"].dropna().unique()),
        key="study_signal",
    )
    sources = cols[2].multiselect("Source Name", sorted(event_windows["source_name"].dropna().unique()), key="study_source")
    source_url_present = cols[3].multiselect("Source URL Provided", [True, False], default=[True, False], key="study_source_url")
    flag_cols = st.columns(2)
    negative_price_filter = flag_cols[0].multiselect(
        "WTI Negative-Price Window",
        [True, False],
        default=[True, False],
        key="study_negative_price",
    )
    extreme_return_filter = flag_cols[1].multiselect(
        "Extreme Return Flag",
        [True, False],
        default=[True, False],
        key="study_extreme_return",
    )

    filtered = event_windows.copy()
    if categories:
        filtered = filtered[filtered["category"].isin(categories)]
    if signals:
        filtered = filtered[filtered["expected_market_signal"].isin(signals)]
    if sources:
        filtered = filtered[filtered["source_name"].isin(sources)]
    filtered = filtered[filtered["source_url_present"].isin(source_url_present)]
    filtered = filtered[filtered["wti_negative_price_window"].isin(negative_price_filter)]
    filtered = filtered[filtered["extreme_return_flag"].isin(extreme_return_filter)]

    st.dataframe(
        filtered[
            [
                "event_id",
                "event_date",
                "aligned_price_date",
                "event_date_shifted",
                "event_title",
                "source_name",
                "source_url_present",
                "category",
                "expected_market_signal",
                "wti_event_price",
                "brent_event_price",
                "wti_price_plus_5d",
                "brent_price_plus_5d",
                "wti_return_1d",
                "wti_return_3d",
                "wti_return_5d",
                "wti_return_10d",
                "wti_change_5d",
                "brent_return_1d",
                "brent_return_3d",
                "brent_return_5d",
                "brent_return_10d",
                "brent_change_5d",
                "wti_negative_price_window",
                "extreme_return_flag",
                "brent_wti_spread_change_5d",
                "source_url",
                "event_summary",
                "notes",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    if filtered.empty:
        st.warning("No events match the selected filters.")
        return

    chart_cols = st.columns(2)
    category_counts = filtered["category"].value_counts().reset_index()
    category_counts.columns = ["category", "count"]
    chart_cols[0].plotly_chart(px.bar(category_counts, x="category", y="count", title="Event Count by Category"), use_container_width=True)

    signal_counts = filtered["expected_market_signal"].value_counts().reset_index()
    signal_counts.columns = ["expected_market_signal", "count"]
    chart_cols[1].plotly_chart(
        px.bar(signal_counts, x="expected_market_signal", y="count", title="Event Count by Expected Market Signal"),
        use_container_width=True,
    )

    avg_category = filtered.groupby("category", as_index=False).agg(
        avg_wti_return_5d=("wti_return_5d", "mean"),
        avg_brent_return_5d=("brent_return_5d", "mean"),
        avg_wti_change_5d=("wti_change_5d", "mean"),
        avg_brent_change_5d=("brent_change_5d", "mean"),
        avg_spread_change_5d=("brent_wti_spread_change_5d", "mean"),
    )
    avg_signal = filtered.groupby("expected_market_signal", as_index=False).agg(
        avg_wti_return_5d=("wti_return_5d", "mean"),
        avg_brent_return_5d=("brent_return_5d", "mean"),
    )

    chart_cols = st.columns(2)
    chart_cols[0].plotly_chart(
        px.bar(avg_category, x="category", y="avg_wti_return_5d", title="Average WTI +5D Percentage Return by Category"),
        use_container_width=True,
    )
    chart_cols[1].plotly_chart(
        px.bar(avg_category, x="category", y="avg_brent_return_5d", title="Average Brent +5D Percentage Return by Category"),
        use_container_width=True,
    )

    chart_cols = st.columns(2)
    chart_cols[0].plotly_chart(
        px.bar(avg_signal, x="expected_market_signal", y="avg_wti_return_5d", title="Average WTI +5D Percentage Return by Expected Signal"),
        use_container_width=True,
    )
    chart_cols[1].plotly_chart(
        px.bar(avg_signal, x="expected_market_signal", y="avg_brent_return_5d", title="Average Brent +5D Percentage Return by Expected Signal"),
        use_container_width=True,
    )

    chart_cols = st.columns(2)
    chart_cols[0].plotly_chart(
        px.bar(avg_category, x="category", y="avg_wti_change_5d", title="Average WTI +5D Dollar Change by Category"),
        use_container_width=True,
    )
    chart_cols[1].plotly_chart(
        px.bar(avg_category, x="category", y="avg_brent_change_5d", title="Average Brent +5D Dollar Change by Category"),
        use_container_width=True,
    )

    st.plotly_chart(
        px.bar(avg_category, x="category", y="avg_spread_change_5d", title="Brent-WTI Spread Change +5D by Category"),
        use_container_width=True,
    )

    url_coverage = filtered["source_url_present"].mean()
    st.metric("Source URL Coverage", percent_label(url_coverage))
    st.warning(
        "Historical event-window analysis is exploratory. Small sample size, overlapping market drivers, "
        "timing uncertainty, market expectations, and source completeness limit causal interpretation."
    )


def methodology(mode: str) -> None:
    st.title("Methodology")
    mode_banner(mode)
    st.markdown(
        """
### Data Sources
- Sample Demo Scenario uses `data/raw/sample_prices.csv` and `data/raw/events_sample.csv`.
- Historical Validation Mode uses actual historical FRED WTI (`DCOILWTICO`) and Brent (`DCOILBRENTEU`) prices from 2020-01-01 through 2025-12-31.
- Historical Validation Mode requires user-provided verified events at `data/raw/verified_events.csv`.

### Feature Engineering
- Daily return
- 7-day and 30-day moving averages
- 7-day and 30-day price changes
- Rolling volatility
- Brent-WTI spread

### Event Classification and Event Study Logic
Sample mode uses transparent keyword rules for event labels. Historical mode aligns verified event dates to the next available FRED price date and calculates +1, +3, +5, and +10 trading-day WTI and Brent returns plus +5 trading-day Brent-WTI spread change.

### Limitations
This is a local portfolio MVP. It is not a production SaaS platform, real-time market data system, causal inference model, trading model, or investment advice product. Historical validation quality depends on the completeness and accuracy of the user-provided verified event dataset.
"""
    )


def historical_mode_error(error: Exception) -> None:
    st.title("Historical Validation Mode")
    st.error(str(error))
    st.write(
        "Historical Validation Mode does not silently replace missing verified events or failed FRED historical "
        "loads with sample demo data. Add `data/raw/verified_events.csv` with the required columns, then refresh."
    )
    st.code(
        "python -c \"from src.event_study import build_event_window_results; "
        "build_event_window_results(refresh_prices=True)\"",
        language="bash",
    )


def main() -> None:
    mode = st.sidebar.selectbox("Data Mode", [SAMPLE_MODE, HISTORICAL_MODE])
    refresh_prices = False
    rebuild_results = False
    if mode == HISTORICAL_MODE:
        refresh_prices = st.sidebar.checkbox("Refresh FRED historical price cache", value=False)
        rebuild_results = st.sidebar.checkbox("Rebuild event-window results", value=False)
        if event_window_results_are_stale():
            st.sidebar.warning(
                "verified_events.csv appears newer than event_window_results.csv. "
                "Rebuild event-window results to use the latest event file."
            )

    page_options = ["Executive Monitor", "Price Trends", "Event Intelligence", "AI Daily Brief", "Methodology"]
    if mode == HISTORICAL_MODE:
        page_options.append("Historical Event Study")
    page = st.sidebar.radio("Dashboard Page", page_options)

    if mode == SAMPLE_MODE:
        prices, features, events = get_sample_mode_data()
        st.sidebar.caption(f"Loaded {len(features):,} sample price rows and {len(events):,} sample event rows.")

        if page == "Executive Monitor":
            executive_monitor(features, events, mode)
        elif page == "Price Trends":
            price_trends(features)
        elif page == "Event Intelligence":
            sample_event_intelligence(events)
        elif page == "AI Daily Brief":
            ai_daily_brief(features, events, mode)
        else:
            methodology(mode)
        return

    try:
        prices, features = get_historical_prices(refresh_prices)
        event_windows = get_historical_event_windows(rebuild_results)
    except Exception as exc:
        historical_mode_error(exc)
        return

    st.sidebar.caption(
        f"Loaded {len(features):,} historical price rows and {len(event_windows):,} verified event rows."
    )

    if page == "Executive Monitor":
        executive_monitor(features, event_windows, mode)
    elif page == "Price Trends":
        price_trends(features)
    elif page == "Event Intelligence":
        historical_event_intelligence(event_windows)
    elif page == "AI Daily Brief":
        ai_daily_brief(features, event_windows, mode)
    elif page == "Historical Event Study":
        historical_event_study(event_windows)
    else:
        methodology(mode)


if __name__ == "__main__":
    main()
