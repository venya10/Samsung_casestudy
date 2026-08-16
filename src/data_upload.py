"""Handles the Data page's "Add dataset" upload.

Validates an uploaded .csv/.xlsx against the exact header set the pipeline was
built for, archives the current source file with a timestamp, MERGES the
upload into it (new (week, market, channel, product) combinations are added;
rows whose key already exists are treated as duplicates and dropped, keeping
the existing row), then re-runs the pipeline end to end on the merged result
(same steps as run_all.py). Everything the pipeline touches -- the source
file, data/processed/, site/ -- is snapshotted first and restored
automatically if any step fails, so a bad or malformed upload can never leave
the live site in a broken state.
"""
from __future__ import annotations

import io
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

import ingest
from common import DATA_PROCESSED, DATA_RAW, SITE, SOURCE_FILE

MAX_BYTES = 25 * 1024 * 1024  # this dataset is a few MB; plenty of headroom
ARCHIVE_DIR = DATA_RAW / "archive"

# Raw (pre-rename) header names for ingest.KEY -- the same (week, market,
# channel, product) grain every dedup elsewhere in this pipeline already uses
# (see ingest.clean()'s own duplicate-key handling), derived from RENAME
# rather than hand-listed a second time so the two can't drift apart.
RAW_KEY = [raw for raw, clean in ingest.RENAME.items() if clean in ingest.KEY]


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


def list_archives() -> list[dict]:
    """Every pre-merge backup, newest first -- for the Data page's read-only
    'Archived versions' list. No passcode needed to view/download these: the
    current dataset is already fully public on this dashboard, so a past
    version of the same data isn't more sensitive."""
    if not ARCHIVE_DIR.exists():
        return []
    out = []
    for p in sorted(ARCHIVE_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            weeks = sorted(int(w) for w in
                            pd.read_csv(p, usecols=["Week"])["Week"].dropna().unique())
            rows = sum(1 for _ in open(p, encoding="utf-8")) - 1  # cheap row count, header excluded
        except Exception:
            weeks, rows = [], None
        out.append({
            "name": p.name,
            "size_bytes": p.stat().st_size,
            "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "rows": rows,
            "weeks": weeks,
        })
    return out


def resolve_archive(name: str) -> Path | None:
    """Path-traversal-safe lookup for the download route -- only a filename
    that actually resolves to inside ARCHIVE_DIR is ever returned."""
    candidate = (ARCHIVE_DIR / name).resolve()
    try:
        candidate.relative_to(ARCHIVE_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _merge(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Old rows first, then new -- drop_duplicates(keep='first') on the
    (week, market, channel, product) key therefore keeps the EXISTING row on
    any collision and only ever adds rows whose key is genuinely new. Returns
    (merged, rows_added, duplicates_ignored)."""
    combined = pd.concat([old, new], ignore_index=True)
    merged = combined.drop_duplicates(subset=RAW_KEY, keep="first").reset_index(drop=True)
    added = len(merged) - len(old)
    ignored = len(new) - added
    return merged, added, ignored


def apply_upload(body: bytes, filename: str) -> dict:
    """Validate, archive the current source, merge the upload into it, and
    rebuild. Raises UploadRejected (safe to show the user verbatim) on any
    failure; the previous working dataset is always left intact on disk when
    this raises."""
    if len(body) > MAX_BYTES:
        raise UploadRejected(f"File too large ({len(body) / 1e6:.1f}MB) -- 25MB limit.")

    new_df = _parse(body, filename)  # validated before any file on disk is touched
    old_df = pd.read_csv(SOURCE_FILE)
    merged_df, rows_added, duplicates_ignored = _merge(old_df, new_df)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{SOURCE_FILE.stem}_{stamp}{SOURCE_FILE.suffix}"
    shutil.copy2(SOURCE_FILE, ARCHIVE_DIR / archive_name)

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
            merged_df.to_csv(SOURCE_FILE, index=False)

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
                f"while rebuilding the merged dataset ({type(exc).__name__}: {exc}). "
                "The previous dataset has been restored -- nothing on the live "
                "site changed. (The pre-merge source was still archived to "
                f"data/raw/archive/{archive_name}.)"
            ) from exc

    weeks = sorted(int(w) for w in pd.to_numeric(merged_df["Week"], errors="coerce").dropna().unique())
    return {
        "rows": len(merged_df),
        "columns": len(merged_df.columns),
        "weeks": weeks,
        "rows_added": rows_added,
        "duplicates_ignored": duplicates_ignored,
        "archived_as": archive_name,
    }
