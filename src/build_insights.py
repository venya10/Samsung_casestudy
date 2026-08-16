"""Run the analysis once and persist it.

The site and the AI assistant both read these tables. Nothing is recomputed at
render time.

Run order:  model.py -> build_insights.py -> alerts.py -> build_site.py
"""
from __future__ import annotations

import duckdb
import pandas as pd

from common import DATA_PBI, DATA_PROCESSED, DUCKDB_PATH, format_export_df
from insights import (
    channel_efficiency,
    influencer_scorecard,
    load_tables,
    market_scorecard,
    metric_correlations,
    paid_vs_earned,
    panel_model,
    product_channel,
    product_summary,
    reallocation,
)


def main() -> None:
    t = load_tables()
    chan, spine, base = t["fact_channel"], t["fact_market_week"], t["fact_base"]

    eff = channel_efficiency(chan)
    pc = product_channel(base)

    outputs = {
        "channel_efficiency": eff,
        "market_scorecard": market_scorecard(spine),
        "product_channel": pc,
        "product_summary": product_summary(pc, base),
        "panel_model": panel_model(chan),
        "metric_correlations": metric_correlations(spine),
        "influencer_scorecard": influencer_scorecard(
            t["fact_influencer"], t["dim_influencer"]),
        "paid_vs_earned": paid_vs_earned(chan),
        "reallocation": reallocation(eff),
    }

    con = duckdb.connect(str(DUCKDB_PATH))
    for name, df in outputs.items():
        df.to_parquet(DATA_PROCESSED / f"{name}.parquet", index=False)
        con.register("tmp", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp")
        con.unregister("tmp")
    con.close()

    for name in ["channel_efficiency", "market_scorecard", "product_channel",
                 "product_summary", "influencer_scorecard", "reallocation",
                 "paid_vs_earned", "panel_model", "metric_correlations"]:
        format_export_df(outputs[name]).to_csv(DATA_PBI / f"{name}.csv", index=False)

    print(f"Persisted {len(outputs)} insight tables -> {DATA_PROCESSED}")
    for name, df in outputs.items():
        print(f"  {name:24s} {len(df):5,d} rows")

    pm = outputs["panel_model"]
    sig = pm[pm["significant_5pct"]]["channel"].tolist()
    print(f"\nPanel model: R2 {pm['r_squared'].iloc[0]:.3f} on "
          f"{pm['n_observations'].iloc[0]} observations; "
          f"significant at 5%: {sig if sig else 'none'}")


if __name__ == "__main__":
    main()
