"""Turn the downloaded Samsung wordmark into a clean, inline-able SVG asset.

The Wikimedia file is an Inkscape export: editor namespaces, clip paths, a
flip-Y matrix transform and a wrapping <g> stack. None of that survives being
pasted into a page well. This flattens it to a single <svg> with one <path>,
sized by viewBox and filled with `currentColor` so CSS controls the colour.

Run once; the result is committed to assets/samsung-wordmark.svg.
"""
from __future__ import annotations

import re
from pathlib import Path

from common import ROOT

SRC = ROOT / "logo_candidate.svg"
DST = ROOT / "assets" / "samsung-wordmark.svg"


def main() -> None:
    if not SRC.exists():
        raise SystemExit(
            f"\n  {SRC.name} not found — this is a ONE-TIME script and has already "
            "run.\n  Its output is committed at assets/samsung-wordmark.svg.\n"
            "  To re-run, download the wordmark from Wikimedia Commons to "
            f"{SRC}\n  (File:Samsung_wordmark.svg) and run this again.\n"
        )
    raw = SRC.read_text(encoding="utf-8")

    # The real wordmark outline is the long path; the short one is the clip rect.
    paths = re.findall(r'<path[^>]*\sd="([^"]+)"', raw, flags=re.S)
    d = max(paths, key=len)

    # Rebuild the transform chain the original nests the path inside:
    #   outer  matrix(12.944053,0,0,-12.944053,-540.03625,1620.0233)
    #   inner  translate(558.9328,88.5098)
    # Keeping them as an explicit transform on a <g> is safer than trying to
    # bake the matrix into thousands of coordinates by hand.
    outer = "matrix(12.944053,0,0,-12.944053,-540.03625,1620.0233)"
    inner = "translate(558.9328,88.5098)"

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 7051.4024 1080" '
        'role="img" aria-label="Samsung">'
        f'<g transform="{outer}">'
        f'<g transform="{inner}">'
        f'<path fill="currentColor" d="{d}"/>'
        "</g></g></svg>"
    )

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(svg, encoding="utf-8")
    print(f"Wrote {DST} ({len(svg):,} bytes)")


if __name__ == "__main__":
    main()
