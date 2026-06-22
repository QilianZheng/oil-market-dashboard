from __future__ import annotations

import pandas as pd


CATEGORY_KEYWORDS = {
    "OPEC / Production": ["opec", "production", "output", "quota", "cut", "barrel"],
    "Geopolitical Risk": ["sanction", "conflict", "attack", "risk", "geopolitical", "tension"],
    "Inventory": ["inventory", "stockpile", "draw", "build", "eia", "storage"],
    "Demand Outlook": ["demand", "consumption", "travel", "refinery", "china", "growth"],
    "Macro / USD": ["dollar", "fed", "rate", "inflation", "macro", "usd"],
    "Shipping Disruption": ["shipping", "tanker", "canal", "port", "freight", "route"],
}

SIGNAL_KEYWORDS = {
    "Bullish": ["cut", "draw", "disruption", "risk", "sanction", "delay", "tight"],
    "Bearish": ["build", "weak", "slowdown", "surplus", "higher output", "demand concern"],
    "Mixed": ["mixed", "offset", "uncertain", "balanced"],
}


def classify_category(text: str) -> str:
    text_l = text.lower()
    scores = {
        category: sum(keyword in text_l for keyword in keywords)
        for category, keywords in CATEGORY_KEYWORDS.items()
    }
    best_category = max(scores, key=scores.get)
    return best_category if scores[best_category] > 0 else "Other"


def classify_signal(text: str) -> str:
    text_l = text.lower()
    scores = {
        signal: sum(keyword in text_l for keyword in keywords)
        for signal, keywords in SIGNAL_KEYWORDS.items()
    }
    best_signal = max(scores, key=scores.get)
    return best_signal if scores[best_signal] > 0 else "Neutral / Unclear"


def classify_events(events: pd.DataFrame) -> pd.DataFrame:
    """
    Add transparent rule-based labels next to the manually curated labels.

    The original category and market_signal columns remain intact so the project can show
    both data curation and automated classification logic.
    """
    df = events.copy()
    text = (
        df["headline"].fillna("")
        + " "
        + df["summary"].fillna("")
        + " "
        + df["category"].fillna("")
    )
    df["rule_based_category"] = text.apply(classify_category)
    df["rule_based_market_signal"] = text.apply(classify_signal)
    df["signal_score"] = df["market_signal"].map(
        {"Bullish": 1, "Mixed": 0, "Neutral / Unclear": 0, "Bearish": -1}
    )
    return df
