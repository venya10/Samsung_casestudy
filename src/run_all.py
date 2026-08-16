"""Run the whole pipeline end to end.

    python src/run_all.py              # full rebuild, a few seconds
    python src/run_all.py --skip-site  # analysis only

Idempotent: safe to re-run at any time. Every step writes to data/processed/ and
DuckDB, so a partial failure leaves the previous build intact until the step that
failed is fixed and re-run.
"""
from __future__ import annotations

import argparse
import time

import duckdb

import build_insights
import model
from common import DATA_PBI, DATA_PROCESSED, DUCKDB_PATH


def purge_stale() -> None:
    """Delete outputs left over from an earlier build.

    Without this, a table that a previous version of the pipeline produced sits
    in data/processed/ forever, indistinguishable from a current one. That is not
    tidiness -- after the schema changed, a stale `fact_weekly_market.csv` (USD,
    52 weeks) sat next to the live `fact_market_week.csv` (AED, 8 weeks). Two
    nearly identical names, completely different data, and nothing marking which
    was which.

    DuckDB is the authority: model.py drops and recreates it from scratch on every
    run, so whatever tables it holds at this point ARE the current set.
    """
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    current = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    con.close()

    removed = 0
    for folder, suffix in [(DATA_PROCESSED, ".parquet"), (DATA_PBI, ".csv")]:
        for path in folder.glob(f"*{suffix}"):
            if path.stem not in current:
                path.unlink()
                removed += 1
    print(f"  {len(current)} current tables; removed {removed} stale file(s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-site", action="store_true",
                    help="Stop after the analysis; do not rebuild the dashboard.")
    args = ap.parse_args()

    import alerts
    import build_site
    import validate_site

    steps: list[tuple[str, callable]] = [
        ("Clean and model the source extract", model.main),
        ("Derive the analysis", build_insights.main),
        ("Evaluate early warning rules", alerts.main),
        ("Remove outputs from previous builds", purge_stale),
    ]
    if not args.skip_site:
        steps += [("Build the dashboard site", build_site.build),
                  ("Validate the site", validate_site.main)]

    total = time.time()
    for i, (label, fn) in enumerate(steps, 1):
        print(f"\n{'=' * 78}\n[{i}/{len(steps)}] {label}\n{'=' * 78}")
        start = time.time()
        try:
            fn()
        except Exception as exc:
            # A locked source file is an ordinary situation with an obvious fix;
            # a stack trace buries the one line that tells the user what to do.
            if type(exc).__name__ == "SourceFileLocked":
                print(exc)
                raise SystemExit(1)
            raise
        print(f"  ...done in {time.time() - start:.1f}s")

    print(f"\n{'=' * 78}")
    print(f"Pipeline complete in {time.time() - total:.1f}s")
    print("\nNext:")
    print("  site/index.html            open the dashboard (works offline)")
    print("  python src/serve.py        serve it, with the live AI assistant")


if __name__ == "__main__":
    main()
