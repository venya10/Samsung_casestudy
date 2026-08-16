"""Data access for the Streamlit app.

The app reads the same parquet tables the static site and Power BI model read --
there is no second analysis layer and no numbers computed in the UI.

The one thing that has to happen live is cross-filtering. Every insight function
in ``src/insights.py`` is a pure function of a fact frame, so when the user
filters to (say) Saudi Arabia the app re-runs the real analysis on that slice
rather than showing a pre-aggregated all-market number with rows hidden. Results
are cached on the filter signature, so a slice is computed once per session.

Exceptions, stated where they are shown in the UI:
  * ``panel_model`` needs the full 64-observation panel and is never re-fitted on
    a subset -- a regression on 8 rows would be noise with a p-value attached.
  * ``cross_market_outliers`` is defined by comparison against peer markets, so
    filtering to one market would remove the comparison that defines it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import insights  # noqa: E402
import state  # noqa: E402

PROCESSED = ROOT / "data" / "processed"

# Recomputed per filter slice.
DERIVED = ["channel_efficiency", "market_scorecard", "product_channel",
           "product_summary", "influencer_scorecard", "paid_vs_earned",
           "reallocation"]
# Only meaningful on the full panel.
GLOBAL_ONLY = ["panel_model", "metric_correlations", "data_quality_log", "alerts",
               "alerts_current"]


@st.cache_data(show_spinner=False)
def load() -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_parquet(p) for p in sorted(PROCESSED.glob("*.parquet"))}


@st.cache_data(show_spinner=False)
def _derive(sig: tuple) -> dict[str, pd.DataFrame]:
    """Re-run the analysis on the slice named by ``sig`` (the filter signature)."""
    t = load()
    keep = dict(sig)

    def cut(df: pd.DataFrame, skip: tuple[str, ...] = ()) -> pd.DataFrame:
        for dim, vals in keep.items():
            if dim in df.columns and dim not in skip:
                col = df[dim].astype(str)
                df = df[col.isin([str(v) for v in vals])]
        return df

    chan, spine, base = (cut(t["fact_channel"]), cut(t["fact_market_week"]),
                         cut(t["fact_base"]))
    infl = cut(t["fact_influencer"])

    if not len(chan) or not len(base):
        return {k: pd.DataFrame() for k in DERIVED}

    # market_scorecard ranks each market against its peers (quartile, rank vs.
    # median MER) -- filtering the market dimension out from under it would make
    # the peer group the market itself and pd.qcut fails outright on <4 unique
    # values. Compute it across every market that survives the OTHER filters,
    # then only row-filter to the selection, mirroring how cross_market_outliers
    # is kept off the DERIVED path for the same reason.
    ms_spine = cut(t["fact_market_week"], skip=("market",))
    ms = insights.market_scorecard(ms_spine) if len(ms_spine) else pd.DataFrame()
    if len(ms) and "market" in keep:
        ms = ms[ms["market"].astype(str).isin([str(v) for v in keep["market"]])]

    eff = insights.channel_efficiency(chan)
    pc = insights.product_channel(base)

    # reallocation() picks donors and receivers by comparing each channel's ROAS
    # to the group median, so it has the same requirement as market_scorecard:
    # the group it compares against has to stay whole. Filtering to one channel
    # would make that channel its own median (everything HOLDs, spend_change=0),
    # a degenerate table rather than an error -- compute it off a channel-whole
    # slice and only row-filter afterward.
    re_chan = cut(t["fact_channel"], skip=("channel",))
    re_eff = insights.channel_efficiency(re_chan) if len(re_chan) else pd.DataFrame()
    realloc = insights.reallocation(re_eff) if len(re_eff) else pd.DataFrame()
    if len(realloc) and "channel" in keep:
        realloc = realloc[realloc["channel"].astype(str)
                          .isin([str(v) for v in keep["channel"]])]

    return {
        "channel_efficiency": eff,
        "market_scorecard": ms,
        "product_channel": pc,
        "product_summary": insights.product_summary(pc, base),
        "influencer_scorecard": (insights.influencer_scorecard(infl, t["dim_influencer"])
                                 if len(infl) else pd.DataFrame()),
        "paid_vs_earned": insights.paid_vs_earned(chan),
        "reallocation": realloc,
    }


def tables() -> dict[str, pd.DataFrame]:
    """All tables, with the filter-sensitive ones recomputed for the active slice."""
    t = dict(load())
    sig = state.signature()
    if sig:
        t.update(_derive(sig))
        for name in ["fact_base", "fact_channel", "fact_market_week",
                     "fact_product", "fact_influencer", "fact_brand"]:
            t[name] = state.apply(t[name])
    return t


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------
def aed(v, dp: int = 0) -> str:
    if pd.isna(v):
        return "—"
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:,.{max(dp, 2)}f}bn AED"
    if a >= 1e6:
        return f"{v / 1e6:,.{max(dp, 1)}f}m AED"
    if a >= 1e4:
        return f"{v / 1e3:,.0f}k AED"
    return f"{v:,.{dp}f} AED"


def num(v, dp: int = 0) -> str:
    return "—" if pd.isna(v) else f"{v:,.{dp}f}"


def pct(v, dp: int = 1) -> str:
    """v is a fraction (0-1): multiplies by 100. Do not use on brand-tracking
    fields -- brand_awareness/purchase_intent/share_of_voice/competitor_sov are
    stored already on a 0-100 scale (see pp() below)."""
    return "—" if pd.isna(v) else f"{v * 100:,.{dp}f}%"


def pp(v, dp: int = 1) -> str:
    """v is already on a 0-100 percentage-point scale -- no multiplying.
    Use this for brand_awareness, purchase_intent, share_of_voice, competitor_sov."""
    return "—" if pd.isna(v) else f"{v:,.{dp}f}%"


def mult(v, dp: int = 2) -> str:
    return "—" if pd.isna(v) else f"{v:,.{dp}f}x"
