"""Check the generated site before anyone opens it.

A static site fails silently: a chart that rendered with no marks, a broken link,
or a page that lost its synthetic-data disclosure all look fine to the generator
and wrong to a reviewer. This checks each of those.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from common import ROOT

SITE = ROOT / "site"
PAGES = ["index.html", "channels.html", "portfolio.html", "influencers.html",
         "brand.html", "alerts.html", "data.html", "assistant.html"]
# Pages that legitimately carry no charts.
NO_CHART_PAGES = {"assistant.html", "data.html"}

failures: list[str] = []
checks = 0


def check(cond: bool, msg: str) -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(msg)


def main() -> None:
    # Module-level accumulators: a one-shot `python src/validate_site.py`
    # process never noticed these weren't reset -- a fresh process means a
    # fresh empty list every time. A long-lived server process that re-runs
    # the pipeline (the Data page's dataset upload) would otherwise keep
    # every previous run's failures too, and double-count `checks`.
    global failures, checks
    failures, checks = [], 0

    if not SITE.exists():
        raise SystemExit("site/ not found — run `python src/build_site.py` first.")

    # Assets
    for asset in ["assets/app.css", "assets/app.js", "assets/samsung-wordmark.svg"]:
        check((SITE / asset).exists(), f"missing asset: {asset}")

    logo = (SITE / "assets" / "samsung-wordmark.svg").read_text(encoding="utf-8")
    check("currentColor" in logo,
          "logo does not use currentColor — it will not recolour against the blue header")
    check(logo.count("<path") == 1, "logo should be a single flattened path")

    pages_html: dict[str, str] = {}
    for page in PAGES:
        path = SITE / page
        check(path.exists(), f"missing page: {page}")
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8")
        pages_html[page] = html

        check(len(html) > 4000, f"{page}: suspiciously small ({len(html)} bytes)")
        check("SAMSUNG" in html.upper(), f"{page}: no Samsung wordmark")
        check("assets/app.css" in html, f"{page}: stylesheet not linked")
        check("<title>" in html, f"{page}: no title")
        # Currency must be stated and must never be mislabelled as USD.
        check("USD" not in html and "$" not in html.replace("&#36;", ""),
              f"{page}: a USD symbol leaked into an AED report")

        # Every internal link resolves
        for href in set(re.findall(r'href="([^"#:]+\.html)"', html)):
            check((SITE / href).exists(), f"{page}: broken link -> {href}")

        # No unrendered template leftovers
        check("{{" not in html and "None" not in re.findall(r">(None)<", html),
              f"{page}: unrendered placeholder or None leaked into the output")
        check("nan" not in html.lower().replace("finance", "").replace("channel", ""),
              f"{page}: a NaN leaked into the rendered output")

    # Charts: every <svg class="chart"> must actually contain marks
    for page, html in pages_html.items():
        svgs = re.findall(r'<svg class="chart\b.*?</svg>', html, flags=re.S)
        if page in NO_CHART_PAGES:
            continue
        check(len(svgs) >= 1, f"{page}: no charts rendered")
        for i, svg in enumerate(svgs):
            marks = (svg.count("<polyline") + svg.count("<rect")
                     + svg.count("<circle") + svg.count("<path"))
            check(marks >= 2, f"{page}: chart #{i+1} has almost no marks ({marks})")
            cid = re.search(r'data-chart="([^"]+)"', svg)
            check(cid is not None, f"{page}: chart #{i+1} has no chart id")

    # Chart count sanity — a page that lost its charts still looks fine otherwise
    # Counts reflect what each page actually contains; they exist to catch a page
    # silently losing a chart, not to impose a quota.
    # index.html shows only the four charts for the selected KPI at a time by
    # design (the other 4 KPIs' quartets render client-side from
    # window.__OVERVIEW_DATA__ on click, not as static SVG in the HTML).
    expected_min = {"index.html": 4, "channels.html": 3, "portfolio.html": 2,
                    "influencers.html": 1, "brand.html": 4, "alerts.html": 1}
    for page, minimum in expected_min.items():
        n = len(re.findall(r'<svg class="chart\b', pages_html.get(page, "")))
        check(n >= minimum, f"{page}: expected >= {minimum} charts, found {n}")

    print(f"{checks - len(failures)}/{checks} checks passed")
    for f in failures:
        print(f"  FAIL  {f}")
    if failures:
        # A normal exception, not sys.exit(1): main() is also called
        # in-process by data_upload.py, where SystemExit would bypass an
        # `except Exception` rollback handler and kill the whole server.
        # The CLI entry point below still turns this into exit code 1.
        raise RuntimeError(f"{len(failures)} validation check(s) failed")
    print("\nSite is good. Open site/index.html, or run `python src/serve.py`.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"\n{exc}")
        sys.exit(1)
