from __future__ import annotations

import pandas as pd


def _format_change(value: float | int | None) -> str:
    if pd.isna(value):
        return "not enough history"
    direction = "up" if value > 0 else "down" if value < 0 else "flat"
    return f"{direction} ${abs(value):.2f}"


def generate_market_brief(features: pd.DataFrame, events: pd.DataFrame, max_events: int = 5) -> str:
    """
    Generate a transparent template-based analyst brief.

    This is intentionally not a trained trading model. It converts structured market data and
    curated event rows into a readable narrative for the portfolio MVP.
    """
    if features.empty:
        return "No price data is available for the brief."

    latest = features.sort_values("date").iloc[-1]
    latest_date = pd.to_datetime(latest["date"]).date()
    wti_change = _format_change(latest.get("wti_price_change_7d"))
    brent_change = _format_change(latest.get("brent_price_change_7d"))
    spread = latest.get("brent_wti_spread")

    signal_counts = events["market_signal"].value_counts().to_dict() if not events.empty else {}
    dominant_signal = max(signal_counts, key=signal_counts.get) if signal_counts else "Neutral / Unclear"

    recent_events = events.sort_values("date", ascending=False).head(max_events)
    event_lines = []
    for _, row in recent_events.iterrows():
        event_date = pd.to_datetime(row["date"]).date()
        event_lines.append(
            f"- {event_date}: {row['headline']} ({row['category']}, {row['market_signal']}). "
            f"{row['summary']}"
        )

    event_text = "\n".join(event_lines) if event_lines else "- No selected events."

    return f"""Template-Based Market Brief

As of {latest_date}, WTI is ${latest['wti_price']:.2f} and Brent is ${latest['brent_price']:.2f}. Over the latest 7-day window, WTI is {wti_change} and Brent is {brent_change}. The Brent-WTI spread is ${spread:.2f}, which helps indicate relative international versus U.S. crude market tightness.

The selected event set leans {dominant_signal.lower()} based on curated market signal labels. This MVP uses transparent rules and template logic to structure market context; it is not a trained trading model and does not provide investment advice.

Selected event drivers:
{event_text}

Analyst takeaway: compare the recent price trend with the event mix. Bullish events can point to tighter supply or stronger demand, bearish events can point to weaker demand or looser supply, and mixed signals require checking whether macro, inventory, and geopolitical drivers are offsetting each other."""
