"""Data access for the static site's live filter API.

`python src/serve.py` exposes this over HTTP for site/'s client-side filter
bar. It calls the same insights.py functions the static-site build itself
calls, so a filtered number here cannot disagree with the unfiltered build.

Exceptions -- tables that are never recomputed on a filtered slice:
  * ``panel_model`` needs the full 64-observation panel and is never re-fitted
    on a subset -- a regression on a handful of rows would be noise with a
    p-value attached.
  * ``market_scorecard`` ranks each market against its peers; filtering the
    market dimension out from under it would make the peer group the market
    itself. Computed off a market-whole slice, then row-filtered.
  * ``reallocation`` compares each channel's ROAS to the group median, so it
    has the same requirement with the channel dimension.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

import insights
from common import DATA_PROCESSED

DIMS = ["week", "channel", "product", "market"]

DERIVED = ["channel_efficiency", "market_scorecard", "product_channel",
           "product_summary", "influencer_scorecard", "paid_vs_earned",
           "reallocation"]
GLOBAL_ONLY = ["panel_model", "metric_correlations", "alerts", "alerts_current"]

FACT_TABLES = ["fact_base", "fact_channel", "fact_market_week",
               "fact_product", "fact_influencer", "fact_brand"]


@lru_cache(maxsize=1)
def load() -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_parquet(p) for p in sorted(DATA_PROCESSED.glob("*.parquet"))}


def _cut(df: pd.DataFrame, keep: dict[str, list], skip: tuple[str, ...] = ()) -> pd.DataFrame:
    for dim, vals in keep.items():
        if dim in df.columns and dim not in skip:
            col = df[dim].astype(str)
            df = df[col.isin([str(v) for v in vals])]
    return df


@lru_cache(maxsize=256)
def _derive(sig: tuple) -> dict[str, pd.DataFrame]:
    """Re-run the analysis on the slice named by `sig` (a hashable filter
    signature -- see `signature()`). Cached per-slice, same as app/data.py."""
    t = load()
    keep = dict(sig)

    chan = _cut(t["fact_channel"], keep)
    base = _cut(t["fact_base"], keep)
    infl = _cut(t["fact_influencer"], keep)

    if not len(chan) or not len(base):
        return {k: pd.DataFrame() for k in DERIVED}

    ms_spine = _cut(t["fact_market_week"], keep, skip=("market",))
    ms = insights.market_scorecard(ms_spine) if len(ms_spine) else pd.DataFrame()
    if len(ms) and "market" in keep:
        ms = ms[ms["market"].astype(str).isin([str(v) for v in keep["market"]])]

    eff = insights.channel_efficiency(chan)
    pc = insights.product_channel(base)

    re_chan = _cut(t["fact_channel"], keep, skip=("channel",))
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


def signature(active: dict[str, list]) -> tuple:
    return tuple(sorted((d, tuple(sorted(map(str, v)))) for d, v in active.items() if v))


def tables(active: dict[str, list]) -> dict[str, pd.DataFrame]:
    """All tables, with the filter-sensitive ones recomputed for `active`
    (dim -> list of selected values; an omitted or empty dim means "all")."""
    t = dict(load())
    sig = signature(active)
    if sig:
        t.update(_derive(sig))
        for name in FACT_TABLES:
            t[name] = _cut(t[name], dict(sig))
    return t
