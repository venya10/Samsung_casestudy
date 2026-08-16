"""Cached loaders for the dashboard.

Every page reads from the parquet tables built by the pipeline. Nothing is
recomputed at render time -- the marketing mix model in particular is fitted once
by build_insights.py and read from disk here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROCESSED = ROOT / "data" / "processed"


@st.cache_data(show_spinner=False)
def load(name: str) -> pd.DataFrame:
    path = PROCESSED / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{name}.parquet not found. Run the pipeline first:\n"
            "  python src/generate_synthetic.py\n"
            "  python src/model.py\n"
            "  python src/build_insights.py\n"
            "  python src/alerts.py"
        )
    return pd.read_parquet(path)


@st.cache_data(show_spinner=False)
def spine() -> pd.DataFrame:
    return load("fact_weekly_market")


def market_filter(df: pd.DataFrame, key: str = "market") -> tuple[pd.DataFrame, list[str]]:
    """One filter row above the charts, scoping everything on the page.

    Filters live above the content and re-scope every chart on the page at once --
    per-chart filters make two charts on the same screen disagree.
    """
    markets = sorted(df["market"].unique())
    chosen = st.multiselect("Markets", markets, default=markets, key=key)
    if not chosen:
        chosen = markets
    return df[df["market"].isin(chosen)], chosen


def week_bounds(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    return df["week"].min(), df["week"].max()
