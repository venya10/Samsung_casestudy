"""Handles the Data page's "Replace the dataset" upload.

Validates an uploaded .csv/.xlsx against the exact header set the pipeline was
built for, swaps it in for data/raw/samsung_marketing_full_dataset.csv, and
re-runs the pipeline end to end (same steps as run_all.py). Everything the
pipeline touches -- the source file, data/processed/, site/ -- is snapshotted
first and restored automatically if any step fails, so a bad or malformed
upload can never leave the live site in a broken state.
"""
from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path

import pandas as pd

import ingest
from common import DATA_PROCESSED, SITE, SOURCE_FILE

MAX_BYTES = 25 * 1024 * 1024  # this dataset is a few MB; plenty of headroom


class UploadRejected(ValueError):
    pass


def _parse(body: bytes, filename: str) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix in (".xlsx", ".xls", ".xlsm"):
            df = pd.read_excel(io.BytesIO(body))
        elif suffix == ".csv":
            df = pd.read_csv(io.BytesIO(body))
        else:
            raise UploadRejected(
                f"Unsupported file type '{suffix or '(none)'}' -- upload a .csv or .xlsx.")
    except UploadRejected:
        raise
    except Exception as exc:
        raise UploadRejected(f"Could not read the file: {exc}") from exc

    # Every header the pipeline's RENAME map expects -- not just the hard
    # REQUIRED subset -- since the ask is specifically "same headers as the
    # original", and catching a missing-but-optional column here gives a
    # clear message instead of a KeyError three modules deep during rebuild.
    expected = list(ingest.RENAME.keys())
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise UploadRejected(
            f"{len(missing)} expected column(s) missing: {', '.join(missing)}.\n"
            f"Found instead: {', '.join(list(df.columns)[:12])}"
            + (" ..." if len(df.columns) > 12 else ""))
    if len(df) == 0:
        raise UploadRejected("The file has no data rows.")
    return df


def apply_upload(body: bytes, filename: str) -> dict:
    """Validate, swap in, and rebuild. Raises UploadRejected (safe to show the
    user verbatim) on any failure; the previous working dataset is always
    left intact on disk when this raises."""
    if len(body) > MAX_BYTES:
        raise UploadRejected(f"File too large ({len(body) / 1e6:.1f}MB) -- 25MB limit.")

    df = _parse(body, filename)  # validated before any file on disk is touched

    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp)
        shutil.copy2(SOURCE_FILE, backup / SOURCE_FILE.name)
        shutil.copytree(DATA_PROCESSED, backup / "processed")
        shutil.copytree(SITE, backup / "site")

        def _restore():
            shutil.copy2(backup / SOURCE_FILE.name, SOURCE_FILE)
            shutil.rmtree(DATA_PROCESSED)
            shutil.copytree(backup / "processed", DATA_PROCESSED)
            shutil.rmtree(SITE)
            shutil.copytree(backup / "site", SITE)

        try:
            df.to_csv(SOURCE_FILE, index=False)

            import alerts
            import build_insights
            import build_site
            import model
            import validate_site

            model.main()
            build_insights.main()
            alerts.main()
            build_site.build()
            validate_site.main()

            # site_data.load()/_derive() are @lru_cache'd for the life of the
            # process (the live filter bar's whole point is not re-reading
            # parquet on every request) -- without this, a successful rebuild
            # would silently keep serving the pre-upload dataset to the
            # filter bar and AI insights until the server itself restarted.
            import site_data
            site_data.load.cache_clear()
            site_data._derive.cache_clear()
        except (Exception, SystemExit) as exc:
            # SystemExit too, not just Exception: a couple of these steps use
            # sys.exit()/raise SystemExit for their normal CLI failure path,
            # which is not an Exception subclass and would otherwise skip
            # this rollback and kill the whole server process.
            _restore()
            raise UploadRejected(
                "The file matched the expected headers, but the pipeline failed "
                f"while rebuilding from it ({type(exc).__name__}: {exc}). The "
                "previous dataset has been restored -- nothing on the live site "
                "changed."
            ) from exc

    weeks = sorted(int(w) for w in pd.to_numeric(df["Week"], errors="coerce").dropna().unique())
    return {"rows": len(df), "columns": len(df.columns), "weeks": weeks}
