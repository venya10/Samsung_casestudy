"""Early Warning Marketing System — rule engine.

Reads config/rules.yaml and evaluates every rule, emitting a ranked alert table.

The engine is cross-sectional first. With 8 weeks there is no trailing baseline to
compare a recent window against, but there ARE 8 comparable subsidiaries running
the same channels in the same weeks — so the primary detector asks "is this market
unlike its peers this week?" rather than "is this market unlike its own past?".
That signal is available from week 1 instead of needing a quarter to warm up, and
it cannot be fooled by a group-wide movement that a single-market trend line would
read as a problem.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from common import CONFIG, DATA_PBI, DATA_PROCESSED, DUCKDB_PATH, market_label

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load_rules() -> dict:
    with open(CONFIG / "rules.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _t(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_PROCESSED / f"{name}.parquet")


def _row(rule: dict, week, entity: str, market: str, metric: str,
         value: float, detail: str) -> dict:
    return {
        "week": week, "market": market, "entity": entity,
        "rule_id": rule["id"], "rule": rule["name"], "category": rule["category"],
        "severity": rule["severity"], "owner": rule["owner"],
        "metric": metric, "value": float(value) if pd.notna(value) else np.nan,
        "detail": detail, "action": " ".join(str(rule["action"]).split()),
    }


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
def peer_zscore(rule: dict, spine: pd.DataFrame, settings: dict) -> list[dict]:
    """Flag a market that diverges from its peers in the same week."""
    metric = rule["metric"]
    if metric not in spine.columns:
        return []
    thr = float(rule.get("threshold", 2.0))
    want_below = rule.get("direction", "below") == "below"
    min_peers = int(settings.get("min_peers", 5))
    scale = float(settings.get("z_scale", 1.4826))
    # Practical-significance floor: see the note in rules.yaml.
    min_gap = float(rule.get("min_relative_gap",
                             settings.get("min_relative_gap", 0.08)))

    out = []
    for week, g in spine.groupby("week"):
        s = g[metric].astype(float).dropna()
        if len(s) < min_peers:
            continue
        med = s.median()
        mad = (s - med).abs().median()
        if not np.isfinite(mad) or mad == 0:
            continue
        for idx in g.index:
            v = g.loc[idx, metric]
            if pd.isna(v):
                continue
            z = (v - med) / (scale * mad)
            if not ((want_below and z <= -thr) or (not want_below and z >= thr)):
                continue
            # Statistically extreme is not enough -- the gap must also matter.
            rel_gap = abs(v - med) / abs(med) if med else np.inf
            if rel_gap < min_gap:
                continue
            mkt = g.loc[idx, "market"]
            out.append(_row(
                rule, int(week), market_label(mkt), mkt, metric, v,
                f"{metric} at {v:,.2f} against a peer median of {med:,.2f} "
                f"({rel_gap:+.0%} gap, {z:+.1f} robust SD across {len(s)} markets)",
            ))
    return out


def movement(rule: dict, spine: pd.DataFrame, settings: dict) -> list[dict]:
    """Recent weeks vs the window immediately before. A movement, not a trend."""
    metric = rule["metric"]
    if metric not in spine.columns:
        return []
    recent_n = int(settings.get("recent_weeks", 2))
    base_n = int(settings.get("baseline_weeks", 3))
    thr = float(rule["threshold"])
    down = rule.get("direction", "down") == "down"

    out = []
    for market, g in spine.sort_values("week").groupby("market"):
        if len(g) < recent_n + base_n:
            continue
        recent = g.tail(recent_n)[metric].mean()
        base = g.iloc[-(recent_n + base_n):-recent_n][metric].mean()
        if not np.isfinite(base) or base == 0:
            continue
        change = recent / base - 1
        hit = change <= thr if down else change >= thr
        if hit:
            wk = int(g["week"].max())
            out.append(_row(
                rule, wk, market_label(market), market, metric, change,
                f"{metric} {change:+.1%} across weeks "
                f"{int(g['week'].iloc[-recent_n])}-{wk} versus the {base_n} before",
            ))
    return out


def below_absolute(rule: dict, spine: pd.DataFrame, settings: dict) -> list[dict]:
    """`min_gap` is this test's equivalent of peer_zscore's practical-
    significance floor -- there is no peer median here to take a relative gap
    against, so the floor is an absolute margin past the threshold instead.
    Without it, a razor-thin, essentially-tied crossing (e.g. sov_gap of
    -0.05, a rounding error) fires exactly as loudly as a real one."""
    metric = rule["metric"]
    if metric not in spine.columns:
        return []
    thr = float(rule["threshold"])
    min_gap = float(rule.get("min_gap", 0.0))
    latest = spine[spine["week"] == spine["week"].max()]
    out = []
    for _, r in latest.iterrows():
        v = r[metric]
        if pd.notna(v) and v < thr - min_gap:
            out.append(_row(
                rule, int(r["week"]), market_label(r["market"]), r["market"],
                metric, v,
                f"{metric} at {v:+.1f} points (threshold {thr:g}, minimum gap "
                f"{min_gap:g}) — Samsung {r['share_of_voice']:.1f} vs "
                f"competitor {r['competitor_sov']:.1f}",
            ))
    return out


def group_movement(rule: dict, spine: pd.DataFrame, settings: dict) -> list[dict]:
    """Recent weeks vs baseline, on the GROUP TOTAL across all 8 markets --
    not each market against its own history, and not each market against its
    peers. This exists because peer_zscore is structurally blind to a
    portfolio-wide movement: nothing looks unusual relative to peers when
    every market moves the same direction together. That is not a hypothetical
    -- this dataset's biggest actual pattern (total sales falling ~40% off
    its week-4 peak) produces zero extra peer_zscore alerts in the weeks it
    happens, because every market declined together."""
    metric = rule["metric"]
    recent_n = int(settings.get("recent_weeks", 2))
    base_n = int(settings.get("baseline_weeks", 3))
    thr = float(rule["threshold"])
    down = rule.get("direction", "down") == "down"

    if metric == "mer":
        g = spine.groupby("week").agg(sales=("sales_aed", "sum"), spend=("spend_aed", "sum"))
        wk = (g["sales"] / g["spend"].replace(0, np.nan)).sort_index()
    elif metric in spine.columns:
        wk = spine.groupby("week")[metric].sum().sort_index()
    else:
        return []

    if len(wk) < recent_n + base_n:
        return []
    recent = wk.tail(recent_n).mean()
    base = wk.iloc[-(recent_n + base_n):-recent_n].mean()
    if not np.isfinite(base) or base == 0:
        return []
    change = recent / base - 1
    hit = change <= thr if down else change >= thr
    if not hit:
        return []
    last_wk = int(wk.index.max())
    return [_row(
        rule, last_wk, "Portfolio (all markets)", "All markets", metric, change,
        f"Group-wide {metric} {change:+.1%} across weeks "
        f"{int(wk.index[-recent_n])}-{last_wk} versus the {base_n} before, "
        f"summed across all 8 markets — invisible to every peer-comparison "
        f"rule on this page, since nothing looks unusual when every market "
        f"moves together.",
    )]


def below_margin_breakeven(rule: dict, eff: pd.DataFrame, settings: dict) -> list[dict]:
    thr = float(rule["threshold"])
    out = []
    for _, r in eff.iterrows():
        v = r.get("roi_gross_margin")
        if pd.isna(v) or not r.get("revenue_attributed", False):
            continue
        if v < thr:
            out.append(_row(
                rule, pd.NA, r["channel"], "All markets", "roi_gross_margin", v,
                f"{r['channel']}: {r['roas']:.2f}x on revenue is {v:.2f}x on "
                f"gross margin — below the {thr:g}x breakeven, on "
                f"{r['spend_aed']:,.0f} AED of spend",
            ))
    return out


def unmeasured_spend(rule: dict, eff: pd.DataFrame, settings: dict) -> list[dict]:
    thr = float(rule["threshold"])
    total = eff["spend_aed"].sum()
    out = []
    for _, r in eff.iterrows():
        if r.get("revenue_attributed", True) or total == 0:
            continue
        share = r["spend_aed"] / total
        if share >= thr:
            out.append(_row(
                rule, pd.NA, r["channel"], "All markets", "share_of_spend", share,
                f"{r['channel']} carries {share:.0%} of media spend "
                f"({r['spend_aed']:,.0f} AED) with no attributed sales or "
                f"conversions in this dataset",
            ))
    return out


def cpc_outlier(rule: dict, eff: pd.DataFrame, settings: dict) -> list[dict]:
    """A channel's cost-per-click far above the other paid channels -- the
    channel-level parallel of cpa_outlier, and an earlier warning than CPA:
    a click-cost problem shows up before it becomes a conversion-cost one.

    Only two channels in this source report click data at all (TV, Influencer,
    B2B Roadshow, Retail, PR and Website all show zero clicks), so `min_channels`
    guards against comparing a "median" of two values -- with this data the
    rule stays intentionally dormant, same reasoning as SOV-01's below_absolute
    having nothing to compare against right now. It activates the moment a
    third paid channel starts reporting clicks."""
    mult = float(rule["threshold"])
    min_channels = int(settings.get("min_channels", 3))
    cpc = eff["spend_aed"] / eff["clicks"].replace(0, np.nan)
    valid = eff.assign(cpc_aed=cpc)[(eff["spend_aed"] > 0) & eff["clicks"].notna() & (eff["clicks"] > 0)]
    if len(valid) < min_channels:
        return []
    med = valid["cpc_aed"].median()
    if not np.isfinite(med) or med == 0:
        return []
    out = []
    for _, r in valid[valid["cpc_aed"] >= med * mult].iterrows():
        out.append(_row(
            rule, pd.NA, r["channel"], "All markets", "cpc_aed", r["cpc_aed"],
            f"{r['channel']}: {r['cpc_aed']:.2f} AED CPC against a paid-channel "
            f"median of {med:.2f} ({r['cpc_aed']/med:.1f}x) on "
            f"{r['spend_aed']:,.0f} AED of spend",
        ))
    return out


def cpa_outlier(rule: dict, sc: pd.DataFrame, settings: dict) -> list[dict]:
    mult = float(rule["threshold"])
    med = sc["cpa_aed"].median()
    out = []
    for _, r in sc[sc["cpa_aed"] >= med * mult].iterrows():
        out.append(_row(
            rule, pd.NA, r["influencer"], r["market"], "cpa_aed", r["cpa_aed"],
            f"{r['influencer']}: {r['cpa_aed']:,.0f} AED CPA against a roster "
            f"median of {med:,.0f} ({r['cpa_aed']/med:.1f}x) on "
            f"{r['spend_aed']:,.0f} AED of fees",
        ))
    return out


def engagement_below_roster(rule: dict, sc: pd.DataFrame, settings: dict) -> list[dict]:
    """Engagement vs the WHOLE roster's median -- not a follower-tier peer
    group. A size-based comparison would be more precise in principle (a
    smaller account naturally runs a higher engagement rate), but this
    source's follower counts are too unstable per influencer to build one;
    see build_dims() in model.py. Roster-wide is the honest fallback."""
    thr = float(rule["threshold"])
    out = []
    for _, r in sc[sc["er_vs_roster"] <= thr].iterrows():
        out.append(_row(
            rule, pd.NA, r["influencer"], r["market"], "er_vs_roster", r["er_vs_roster"],
            f"{r['influencer']}: engagement {r['engagement_rate']:.2f}% is "
            f"{r['er_vs_roster']:+.0%} against the roster median",
        ))
    return out


def engagement_declining(rule: dict, fact_inf: pd.DataFrame, settings: dict) -> list[dict]:
    """An influencer's OWN engagement rate, recent weeks vs the weeks before --
    the trend counterpart to engagement_below_roster's snapshot comparison.
    That rule catches an account that's currently weak against the roster;
    this one catches an account getting worse over time, which a snapshot
    comparison cannot see if the whole roster is softening together, or if
    this creator was never unusual but is still declining. Aggregates to
    influencer-week first -- a creator can carry several product rows in the
    same week, and averaging those in before taking "the last 2 weeks" would
    otherwise grab rows, not weeks."""
    recent_n = int(settings.get("recent_weeks", 2))
    base_n = int(settings.get("baseline_weeks", 3))
    thr = float(rule["threshold"])
    wk = fact_inf.groupby(["influencer", "week"], as_index=False).agg(
        engagement_rate=("engagement_rate", "mean"), market=("market", "first"))

    out = []
    for name, g in wk.sort_values("week").groupby("influencer"):
        if len(g) < recent_n + base_n:
            continue
        recent = g.tail(recent_n)["engagement_rate"].mean()
        base = g.iloc[-(recent_n + base_n):-recent_n]["engagement_rate"].mean()
        if not np.isfinite(base) or base == 0:
            continue
        change = recent / base - 1
        if change <= thr:
            out.append(_row(
                rule, int(g["week"].max()), name, g["market"].iloc[-1],
                "engagement_rate", change,
                f"{name}: engagement {change:+.1%} across the last {recent_n} "
                f"weeks versus the {base_n} before — declining independent of "
                f"how it compares to the rest of the roster",
            ))
    return out


def follower_count_unreliable(rule: dict, sc: pd.DataFrame, settings: dict) -> list[dict]:
    """A data-quality flag, not a roster-composition claim. This used to be
    'roster lacks tier diversification' -- but that claim depended on a
    follower-tier classification built by taking the MAX of a value that
    swings by hundreds of thousands of followers for the same influencer
    within a single week (see build_dims() in model.py). Every aggregation
    tried (max, median, mean) collapses the whole roster into one tier, which
    is the tell that the field itself can't support tier classification, not
    that the roster is genuinely undiversified. Fires on the share of
    influencers flagged `followers_unstable`, not on a tier count."""
    if sc.empty:
        return []
    thr = float(rule.get("threshold", 0.5))
    unstable = sc[sc["followers_unstable"].fillna(False)]
    share = len(unstable) / len(sc)
    if share < thr:
        return []
    return [_row(
        rule, pd.NA, "Influencer follower data", "All markets", "followers_unstable", share,
        f"{len(unstable)} of {len(sc)} influencers ({share:.0%}) have a recorded "
        "follower count that swings by more than its own median across rows in "
        "the dataset — the same creator shows very different values week to "
        "week, sometimes even product to product in the same week. "
        "Follower-tier classification and any size-based peer comparison are "
        "not reliable on this field until its meaning is confirmed with the "
        "data source.",
    )]


SPINE_TESTS = {"peer_zscore": peer_zscore, "movement": movement,
               "below_absolute": below_absolute, "group_movement": group_movement}
CHANNEL_TESTS = {"below_margin_breakeven": below_margin_breakeven,
                 "unmeasured_spend": unmeasured_spend, "cpc_outlier": cpc_outlier}
INFLUENCER_TESTS = {"cpa_outlier": cpa_outlier,
                    "engagement_below_roster": engagement_below_roster,
                    "follower_count_unreliable": follower_count_unreliable}
# Needs the raw weekly grain (fact_influencer), not the one-row-per-influencer
# scorecard the tests above use -- kept as a separate dispatch table rather
# than changing what INFLUENCER_TESTS functions receive.
INFLUENCER_TREND_TESTS = {"engagement_declining": engagement_declining}


# --------------------------------------------------------------------------
def run_alerts(min_relative_gap: float | None = None) -> pd.DataFrame:
    """`min_relative_gap`, if given, overrides the config file's global default
    practical-significance floor (the dashboard's sensitivity control uses
    this). A rule with its OWN `min_relative_gap` (e.g. SENT-01) still wins --
    this only moves the floor for rules relying on the shared default."""
    cfg = load_rules()
    settings = dict(cfg.get("settings", {}))
    if min_relative_gap is not None:
        settings["min_relative_gap"] = min_relative_gap
    spine = _t("fact_market_week")
    eff = _t("channel_efficiency")
    sc = _t("influencer_scorecard")
    fact_inf = _t("fact_influencer")

    rows: list[dict] = []
    for rule in cfg["rules"]:
        test = rule["test"]
        if test in SPINE_TESTS:
            rows += SPINE_TESTS[test](rule, spine, settings)
        elif test in CHANNEL_TESTS:
            rows += CHANNEL_TESTS[test](rule, eff, settings)
        elif test in INFLUENCER_TESTS:
            rows += INFLUENCER_TESTS[test](rule, sc, settings)
        elif test in INFLUENCER_TREND_TESTS:
            rows += INFLUENCER_TREND_TESTS[test](rule, fact_inf, settings)

    cols = ["week", "market", "entity", "rule_id", "rule", "category", "severity",
            "owner", "metric", "value", "detail", "action"]
    if not rows:
        return pd.DataFrame(columns=cols + ["severity_rank"])
    df = pd.DataFrame(rows)[cols]
    df["severity_rank"] = df["severity"].map(SEVERITY_ORDER).fillna(9).astype(int)
    return df.sort_values(["severity_rank", "week", "market"],
                          na_position="first").reset_index(drop=True)


def latest_alerts(alerts: pd.DataFrame) -> pd.DataFrame:
    """Alerts for the most recent week, plus every undated (portfolio) alert."""
    if alerts.empty:
        return alerts
    dated = alerts[alerts["week"].notna()]
    undated = alerts[alerts["week"].isna()]
    if dated.empty:
        return undated
    cur = dated[dated["week"] == dated["week"].max()]
    return (pd.concat([cur, undated], ignore_index=True)
            .sort_values(["severity_rank", "market"]).reset_index(drop=True))


def main() -> None:
    import duckdb

    alerts = run_alerts()
    current = latest_alerts(alerts)

    for name, df in [("alerts", alerts), ("alerts_current", current)]:
        df.to_parquet(DATA_PROCESSED / f"{name}.parquet", index=False)
        df.to_csv(DATA_PBI / f"{name}.csv", index=False)

    con = duckdb.connect(str(DUCKDB_PATH))
    for name, df in [("alerts", alerts), ("alerts_current", current)]:
        con.register("tmp", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp")
        con.unregister("tmp")
    con.close()

    print(f"{len(alerts)} alerts across all 8 weeks; {len(current)} open now\n")
    if not alerts.empty:
        print(alerts.groupby(["severity", "category"]).size().to_string())
        print("\n--- OPEN NOW ---")
        for _, r in current.iterrows():
            wk = "portfolio" if pd.isna(r["week"]) else f"wk {int(r['week'])}"
            print(f"[{r['severity'].upper():8s}] {wk:9s} {r['entity']:28s} {r['rule']}")
            print(f"           {r['detail']}")


if __name__ == "__main__":
    main()
