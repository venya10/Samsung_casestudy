"""Inline-SVG chart primitives.

No charting library. Everything here emits plain SVG strings that get written
straight into the page, which means the finished site is self-contained, opens
offline by double-clicking, weighs kilobytes rather than megabytes, and every mark
is under our control rather than a library's defaults.

Design rules applied throughout (and why):
  * Thin marks, hairline grid one shade off the surface, generous padding.
  * Never two y-axes on one plot -- the alignment of two scales is arbitrary, so a
    dual axis invents a correlation the data does not contain. Two charts, or index
    both series to a common base.
  * One measure across many categories gets ONE hue with the extremes picked out,
    not one hue per bar. Colouring by value double-encodes bar length as hue.
  * Scatter plots cap at two or three colour classes; with every pair of points
    adjacent on screen, more cannot stay distinguishable under colour-vision
    deficiency.
  * Direct labels are selective -- the endpoint or the extreme, never a number on
    every point.
  * Every chart pairs with a table in the page, so no value is hover-only.
"""
from __future__ import annotations

import html
import math
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
# Ported from the visual reference project's design system (dashboard/
# template.html :root + app_core.js's `C` chart-colour constant). SAMSUNG_BLUE,
# STATUS and the neutral ink/muted/grid/baseline scale are the reference's
# exact values. SERIES has no reference equivalent -- its own chart palette is
# six chrome/status colours, not an 8-way categorical set for charts like
# "weekly sales by market" (8 series) -- so the existing colour-vision-validated
# palette (lightness band, chroma floor, adjacent CVD separation checked) is
# kept, with slot 0 anchored to the reference's exact accent blue.
SAMSUNG_BLUE = "#1428A0"

SERIES = [
    "#2B6DEF",  # 1  reference's accent blue (--blue-2)
    "#eb6834",  # 2  orange
    "#1baf7a",  # 3  aqua
    "#eda100",  # 4  yellow
    "#e87ba4",  # 5  magenta
    "#008300",  # 6  green
    "#4a3aa7",  # 7  violet
    "#e34948",  # 8  red
]
SERIES_MUTED = "#C7D6FB"      # recessive step of slot 1
# Softer 6-hue cycle, already validated elsewhere as the KPI card icon accents
# (app.css's `.kpis .kpi:nth-child(6n+N)`) -- reused here rather than inventing
# a second pastel set, so the pie chart reads as the same design language.
SERIES_PASTEL = [
    "#7FA8FF",  # 1  blue
    "#6FCFA0",  # 2  green
    "#F2AD5C",  # 3  orange
    "#B39BF0",  # 4  violet
    "#F291B7",  # 5  pink
    "#62C4C2",  # 6  teal
    "#F2D98A",  # 7  yellow
    "#F2A6A6",  # 8  red
]
STATUS = {
    "good": "#0B7A54",
    "warning": "#B26A00",
    "serious": "#ec835a",
    "critical": "#C0272D",
}

INK = "#0A1020"
INK_2 = "#333E52"
MUTED = "#707C91"
GRID = "#EFF2F7"
BASELINE = "#E4E8EF"
SURFACE = "#ffffff"
FAINT = "#9AA5B7"

MARKET_COLOR = {"UAE": SERIES[0], "KSA": SERIES[1], "Egypt": SERIES[2]}


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def money(v: float | None, dp: int = 0) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e9:
        return f"{sign}${a/1e9:,.2f}bn"
    if a >= 1e6:
        return f"{sign}${a/1e6:,.1f}m"
    if a >= 1e3:
        return f"{sign}${a/1e3:,.0f}k"
    return f"{sign}${a:,.{dp}f}"


def num(v: float | None, dp: int = 0) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e6:
        return f"{sign}{a/1e6:,.1f}m"
    if a >= 1e3:
        return f"{sign}{a/1e3:,.0f}k"
    return f"{sign}{a:,.{dp}f}"


def pct(v: float | None, dp: int = 1) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v * 100:,.{dp}f}%"


def esc(s) -> str:
    return html.escape(str(s), quote=True)


# --------------------------------------------------------------------------
# Scales
# --------------------------------------------------------------------------
def nice_ticks(lo: float, hi: float, target: int = 5) -> list[float]:
    """Round tick values at a human-readable interval."""
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / max(target, 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for mult in (1, 2, 2.5, 5, 10):
        step = mag * mult
        if raw <= step:
            break
    start = math.floor(lo / step) * step
    ticks, v = [], start
    while v <= hi + step * 0.5:
        ticks.append(round(v, 10))
        v += step
    return ticks


@dataclass
class Series:
    label: str
    values: list[float]
    color: str = SERIES[0]
    width: float = 2.0
    dashed: bool = False
    filter_val: str | None = None  # raw filter value, if it differs from `label`
                                    # (e.g. label "SGE (Gulf)", filter value "SGE")


@dataclass
class Band:
    """A shaded x-range calling out an event window."""
    start: int
    end: int
    label: str = ""


@dataclass
class Marker:
    """A pointed annotation on a specific data point."""
    index: int
    series: int
    text: str
    dy: int = -26


# --------------------------------------------------------------------------
# Line chart
# --------------------------------------------------------------------------
def line_chart(
    x_labels: list[str],
    series: list[Series],
    *,
    height: int = 300,
    width: int = 760,
    y_fmt=num,
    y_zero: bool = False,
    bands: list[Band] | None = None,
    markers: list[Marker] | None = None,
    hover_fmt=None,
    chart_id: str = "c",
    filter_dim: str | None = None,
) -> str:
    """Multi-series line chart with a crosshair + shared tooltip on hover.

    `filter_dim`, when given, makes each SERIES (not each week) a click-to-filter
    target -- e.g. one line per market. A stroke alone is a thin, unreliable
    click target, so a small circle marker is drawn at every point too."""
    pad_l, pad_r, pad_t, pad_b = 58, 18, 16, 34
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    hover_fmt = hover_fmt or y_fmt

    flat = [v for s in series for v in s.values if v is not None and not math.isnan(v)]
    lo, hi = (min(flat), max(flat)) if flat else (0, 1)
    if y_zero:
        lo = min(lo, 0)
    span = hi - lo or 1
    lo -= span * 0.08
    hi += span * 0.08
    ticks = nice_ticks(lo, hi)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])

    n = len(x_labels)

    def X(i: int) -> float:
        return pad_l + (pw * i / max(n - 1, 1))

    def Y(v: float) -> float:
        return pad_t + ph - (v - lo) / (hi - lo) * ph

    out = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]

    # Event bands sit below everything
    for b in bands or []:
        x0, x1 = X(b.start), X(b.end)
        out.append(
            f'<rect x="{x0:.1f}" y="{pad_t}" width="{max(x1-x0,1):.1f}" height="{ph}" '
            f'fill="{MUTED}" opacity="0.07"/>'
        )
        if b.label:
            out.append(
                f'<text x="{(x0+x1)/2:.1f}" y="{pad_t + 12}" text-anchor="middle" '
                f'class="ann">{esc(b.label)}</text>'
            )

    # Gridlines + y ticks
    for t in ticks:
        if t < lo or t > hi:
            continue
        y = Y(t)
        out.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{pad_l-10}" y="{y+4:.1f}" text-anchor="end" class="tick">'
            f"{esc(y_fmt(t))}</text>"
        )

    # X labels — thinned so they never collide
    step = max(1, n // 7)
    for i in range(0, n, step):
        out.append(
            f'<text x="{X(i):.1f}" y="{height-12}" text-anchor="middle" class="tick">'
            f"{esc(x_labels[i])}</text>"
        )

    # Baseline
    out.append(
        f'<line x1="{pad_l}" y1="{pad_t+ph}" x2="{width-pad_r}" y2="{pad_t+ph}" '
        f'stroke="{BASELINE}" stroke-width="1"/>'
    )

    # Lines
    for s in series:
        idx_pts = [
            (i, X(i), Y(v)) for i, v in enumerate(s.values)
            if v is not None and not math.isnan(v)
        ]
        if not idx_pts:
            continue
        fval = s.filter_val if s.filter_val is not None else s.label
        fattrs = f' data-fdim="{esc(filter_dim)}" data-fval="{esc(fval)}"' if filter_dim else ""
        dash = ' stroke-dasharray="5 4"' if s.dashed else ""
        pts = " ".join(f"{px:.1f},{py:.1f}" for _, px, py in idx_pts)
        out.append(
            f'<polyline points="{pts}" fill="none" stroke="{s.color}" '
            f'stroke-width="{s.width}" stroke-linecap="round" stroke-linejoin="round"{dash}{fattrs}/>'
        )
        # White-centre, coloured-ring point markers on every line -- ported
        # from the reference's lineChart()/comboChart(), drawn regardless of
        # whether the series is a click-to-filter target.
        for i, px, py in idx_pts:
            out.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.2" fill="{SURFACE}" '
                f'stroke="{s.color}" stroke-width="1.8" data-title="{esc(s.label)}" '
                f'data-body="{esc(x_labels[i])}: {esc(hover_fmt(s.values[i]) if hover_fmt else y_fmt(s.values[i]))}"'
                f'{fattrs}/>'
            )

    # Pointed annotations
    for m in markers or []:
        s = series[m.series]
        v = s.values[m.index]
        if v is None or math.isnan(v):
            continue
        x, y = X(m.index), Y(v)
        out.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{s.color}" '
            f'stroke="{SURFACE}" stroke-width="2"/>'
        )
        anchor = "middle"
        tx = x
        if x < pad_l + 70:
            anchor, tx = "start", x - 4
        elif x > width - pad_r - 70:
            anchor, tx = "end", x + 4
        out.append(
            f'<text x="{tx:.1f}" y="{y + m.dy:.1f}" text-anchor="{anchor}" '
            f'class="ann-strong">{esc(m.text)}</text>'
        )

    # Hover layer: one full-height band per x index, wider than any mark so the
    # target is easy to hit, carrying the values for the shared tooltip.
    out.append(f'<g class="hit" data-n="{n}">')
    bw = pw / max(n - 1, 1)
    for i in range(n):
        payload = " · ".join(
            f"{s.label}: {hover_fmt(s.values[i])}"
            for s in series
            if i < len(s.values) and s.values[i] is not None and not math.isnan(s.values[i])
        )
        out.append(
            f'<rect x="{X(i)-bw/2:.1f}" y="{pad_t}" width="{bw:.1f}" height="{ph}" '
            f'fill="transparent" data-x="{X(i):.1f}" data-y0="{pad_t}" '
            f'data-y1="{pad_t+ph}" data-title="{esc(x_labels[i])}" '
            f'data-body="{esc(payload)}"/>'
        )
    out.append("</g>")
    out.append(
        f'<line class="crosshair" x1="0" y1="{pad_t}" x2="0" y2="{pad_t+ph}" '
        f'stroke="{BASELINE}" stroke-width="1" opacity="0"/>'
    )
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Horizontal bar chart
# --------------------------------------------------------------------------
def bar_chart_h(
    labels: list[str],
    values: list[float],
    *,
    colors: list[str] | None = None,
    height: int | None = None,
    width: int = 760,
    v_fmt=num,
    label_fmt=None,
    zero_line: float | None = None,
    zero_label: str = "",
    chart_id: str = "b",
    filter_dim: str | None = None,
    filter_vals: list | None = None,
    subs: list[str] | None = None,
    row_height: int = 34,
) -> str:
    """One measure across categories. Bars carry their value as a direct label.

    `filter_dim`/`filter_vals` make each bar a click-to-filter target -- e.g. for
    market bars labelled "SGE (Gulf)" but filtered by the raw code "SGE",
    `filter_vals` carries the raw values in parallel to the display `labels`.

    `subs`, if given, prints a second, smaller line under each category label
    (e.g. spend and CPA) -- ported from the reference's hbars() `sub` field.

    `row_height` shrinks every row proportionally for a long list (e.g. a
    24-name roster) so the whole chart still fits without turning into a
    page-length scroll -- default 34 is unchanged for the normal 4-10 row case."""
    label_fmt = label_fmt or v_fmt
    n = len(labels)
    row = row_height
    pad_l, pad_r, pad_t, pad_b = 152, 74, 8, 22
    height = height or (pad_t + pad_b + row * n)
    pw = width - pad_l - pad_r
    colors = colors or [SERIES[0]] * n

    lo = min(0, min(values)) if values else 0
    hi = max(values) if values else 1
    if hi == lo:
        hi = lo + 1
    pad = (hi - lo) * 0.02
    lo -= pad
    hi += pad

    def X(v: float) -> float:
        return pad_l + (v - lo) / (hi - lo) * pw

    out = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]
    x_zero = X(zero_line if zero_line is not None else 0)

    for i, (lab, v, c) in enumerate(zip(labels, values, colors)):
        y = pad_t + i * row + 6
        h = row - 14
        x1, x2 = (min(X(v), x_zero), max(X(v), x_zero))
        bw = max(x2 - x1, 1.5)
        fval = filter_vals[i] if filter_vals else lab
        fattrs = f' data-fdim="{esc(filter_dim)}" data-fval="{esc(fval)}"' if filter_dim else ""
        # Full-width track behind the bar, so every row shows its available
        # range even where the value itself is small -- ported from the
        # reference's hbars().
        out.append(f'<rect x="{pad_l:.1f}" y="{y:.1f}" width="{pw:.1f}" height="{h}" rx="3" fill="{GRID}"/>')
        # 4px rounded data-end, square against the baseline
        out.append(
            f'<rect x="{x1:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h}" rx="3" '
            f'fill="{c}" data-title="{esc(lab)}" data-body="{esc(label_fmt(v))}" '
            f'class="bar"{fattrs}/>'
        )
        sub = subs[i] if subs else None
        cat_y = (pad_t + i * row + 16) if sub else (y + h / 2 + 4)
        out.append(
            f'<text x="{pad_l-12}" y="{cat_y:.1f}" text-anchor="end" '
            f'class="cat">{esc(lab)}</text>'
        )
        if sub:
            out.append(
                f'<text x="{pad_l-12}" y="{pad_t + i * row + 28:.1f}" text-anchor="end" '
                f'class="cat-sub">{esc(sub)}</text>'
            )

        # Place the value label outside the bar end when there is room, and inside
        # it when there is not. A long bar's outside label otherwise runs into the
        # category gutter and overprints the category name.
        text = label_fmt(v)
        w_est = len(text) * 6.7          # ~12px semibold sans
        positive = v >= (zero_line or 0)
        if positive:
            if x2 + 10 + w_est > width - 4:
                tx, anchor, fill = x2 - 8, "end", "#ffffff"
            else:
                tx, anchor, fill = x2 + 8, "start", INK_2
        else:
            if x1 - 10 - w_est < pad_l:
                tx, anchor, fill = x1 + 8, "start", "#ffffff"
            else:
                tx, anchor, fill = x1 - 8, "end", INK_2
        out.append(
            f'<text x="{tx:.1f}" y="{y + h/2 + 4:.1f}" text-anchor="{anchor}" '
            f'class="val" fill="{fill}">{esc(text)}</text>'
        )

    if zero_line is not None or lo < 0:
        out.append(
            f'<line x1="{x_zero:.1f}" y1="{pad_t}" x2="{x_zero:.1f}" '
            f'y2="{height-pad_b:.1f}" stroke="{BASELINE}" stroke-width="1"/>'
        )
        if zero_label:
            out.append(
                f'<text x="{x_zero:.1f}" y="{height-6}" text-anchor="middle" '
                f'class="tick">{esc(zero_label)}</text>'
            )
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Pie (part-of-whole across categories, click-selectable)
# --------------------------------------------------------------------------
def pie_chart(
    labels: list[str],
    values: list[float],
    *,
    colors: list[str] | None = None,
    v_fmt=money,
    subs: list[str] | None = None,
    size: int = 300,
    chart_id: str = "pie",
    select_dim: str | None = None,
    selected: str | None = None,
) -> str:
    """Single-series part-of-whole. Unlike bar_chart_h (a ranked measure, one
    hue per grade), a pie's slices must sum to something -- so this takes
    whatever `values` are and shows each as a share of their total, not a
    standalone number.

    `select_dim`/`selected`, when given, mark each slice AND its legend chip
    with `data-select-dim`/`data-select-val` -- a click-to-drill-down target
    for a *local* JS interaction (assets/app_pages.js redraws charts scoped to
    the clicked category), deliberately a different attribute name from the
    [data-fdim] the rest of this codebase uses for the page-wide cross-filter,
    so the two click systems can't collide on the same element."""
    n = len(labels)
    colors = colors or [SERIES_PASTEL[i % len(SERIES_PASTEL)] for i in range(n)]
    total = sum(values) or 1
    cx = cy = size / 2
    r = size / 2 - 6

    svg = [
        f'<svg class="chart chart-pie" viewBox="0 0 {size} {size}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]
    legend_items = []
    angle = -90.0
    for i, (lab, v, c) in enumerate(zip(labels, values, colors)):
        frac = v / total
        sweep = frac * 360
        a0, a1 = math.radians(angle), math.radians(angle + sweep)
        x1, y1 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x2, y2 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        large = 1 if sweep > 180 else 0
        sel_cls = " selected" if selected is not None and lab == selected else ""
        sel_attrs = (f' data-select-dim="{esc(select_dim)}" data-select-val="{esc(lab)}"'
                     if select_dim else "")
        sub = f" · {esc(subs[i])}" if subs else ""
        svg.append(
            f'<path class="pie-slice{sel_cls}" d="M{cx:.2f},{cy:.2f} '
            f'L{x1:.2f},{y1:.2f} A{r:.1f},{r:.1f} 0 {large},1 {x2:.2f},{y2:.2f} Z" '
            f'fill="{c}" data-title="{esc(lab)}" '
            f'data-body="{esc(v_fmt(v))} · {frac*100:.1f}% of total{sub}"'
            f'{sel_attrs}/>'
        )
        legend_items.append(
            f'<button type="button" class="pie-legend-item{sel_cls}"{sel_attrs}>'
            f'<span class="lg-dot" style="background:{c}"></span>'
            f'<span class="pli-label">{esc(lab)}</span>'
            f'<span class="pli-share">{frac*100:.0f}%</span></button>'
        )
        angle += sweep
    svg.append("</svg>")

    return (
        '<div class="pie-block">'
        f'<div class="pie-svg-wrap">{"".join(svg)}</div>'
        f'<div class="pie-legend">{"".join(legend_items)}</div>'
        "</div>"
    )


# --------------------------------------------------------------------------
# Lollipop (dot-and-stem) -- market comparisons, visually distinct from the
# filled bars used for channel comparisons on the same page.
# --------------------------------------------------------------------------
def lollipop_chart(
    labels: list[str],
    values: list[float],
    *,
    colors: list[str] | None = None,
    height: int | None = None,
    width: int = 760,
    v_fmt=num,
    chart_id: str = "lol",
    filter_dim: str | None = None,
    filter_vals: list | None = None,
    row_height: int = 34,
) -> str:
    """One measure across categories, as a dot at the end of a thin stem
    rather than a filled bar -- bar_chart_h's shape is reserved for channel
    comparisons elsewhere on the same page, so market comparisons read as a
    visually distinct family at a glance rather than "more bars"."""
    n = len(labels)
    row = row_height
    pad_l, pad_r, pad_t, pad_b = 152, 56, 8, 22
    height = height or (pad_t + pad_b + row * n)
    pw = width - pad_l - pad_r
    colors = colors or [SERIES[0]] * n

    lo = min(0, min(values)) if values else 0
    hi = max(values) if values else 1
    if hi == lo:
        hi = lo + 1
    pad = (hi - lo) * 0.06
    hi += pad
    lo -= pad if lo < 0 else 0

    def X(v: float) -> float:
        return pad_l + (v - lo) / (hi - lo) * pw

    x_zero = X(0) if lo < 0 else pad_l

    out = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]
    for i, (lab, v, c) in enumerate(zip(labels, values, colors)):
        y = pad_t + i * row + row / 2 - 3
        x2 = X(v)
        fval = filter_vals[i] if filter_vals else lab
        fattrs = f' data-fdim="{esc(filter_dim)}" data-fval="{esc(fval)}"' if filter_dim else ""
        out.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<line x1="{x_zero:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
            f'stroke="{c}" stroke-width="2.5"{fattrs}/>'
        )
        out.append(
            f'<circle cx="{x2:.1f}" cy="{y:.1f}" r="5.5" fill="{c}" stroke="{SURFACE}" '
            f'stroke-width="1.5" class="bar" data-title="{esc(lab)}" '
            f'data-body="{esc(v_fmt(v))}"{fattrs}/>'
        )
        out.append(
            f'<text x="{pad_l-12}" y="{y+4:.1f}" text-anchor="end" '
            f'class="cat">{esc(lab)}</text>'
        )
        text = v_fmt(v)
        w_est = len(text) * 6.7
        if x2 + 11 + w_est > width - 4:
            tx, anchor, fill = x2 - 10, "end", "#ffffff"
        else:
            tx, anchor, fill = x2 + 11, "start", INK_2
        out.append(
            f'<text x="{tx:.1f}" y="{y+4:.1f}" text-anchor="{anchor}" '
            f'class="val" fill="{fill}">{esc(text)}</text>'
        )
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Donut (part-of-whole with a centred total) -- product contribution and
# 2-way splits, visually distinct from pie_chart's full wedges (which stay
# reserved for the Channels page's click-to-drill-down pie).
# --------------------------------------------------------------------------
def donut_chart(
    labels: list[str],
    values: list[float],
    *,
    colors: list[str] | None = None,
    v_fmt=money,
    size: int = 300,
    hole: float = 0.6,
    center_label: str | None = None,
    center_sub: str = "",
    chart_id: str = "donut",
    filter_dim: str | None = None,
    filter_vals: list | None = None,
) -> str:
    n = len(labels)
    colors = colors or [SERIES[i % len(SERIES)] for i in range(n)]
    total = sum(values) or 1
    cx = cy = size / 2
    r_out = size / 2 - 6
    r_in = r_out * hole

    svg = [
        f'<svg class="chart chart-pie" viewBox="0 0 {size} {size}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]
    legend_items = []
    angle = -90.0
    for i, (lab, v, c) in enumerate(zip(labels, values, colors)):
        frac = v / total
        sweep = frac * 360
        a0, a1 = math.radians(angle), math.radians(angle + sweep)
        ox1, oy1 = cx + r_out * math.cos(a0), cy + r_out * math.sin(a0)
        ox2, oy2 = cx + r_out * math.cos(a1), cy + r_out * math.sin(a1)
        ix1, iy1 = cx + r_in * math.cos(a1), cy + r_in * math.sin(a1)
        ix2, iy2 = cx + r_in * math.cos(a0), cy + r_in * math.sin(a0)
        large = 1 if sweep > 180 else 0
        fval = filter_vals[i] if filter_vals else lab
        fattrs = f' data-fdim="{esc(filter_dim)}" data-fval="{esc(fval)}"' if filter_dim else ""
        svg.append(
            f'<path class="pie-slice" d="M{ox1:.2f},{oy1:.2f} '
            f'A{r_out:.1f},{r_out:.1f} 0 {large},1 {ox2:.2f},{oy2:.2f} '
            f'L{ix1:.2f},{iy1:.2f} A{r_in:.1f},{r_in:.1f} 0 {large},0 {ix2:.2f},{iy2:.2f} Z" '
            f'fill="{c}" data-title="{esc(lab)}" '
            f'data-body="{esc(v_fmt(v))} · {frac*100:.1f}% of total"{fattrs}/>'
        )
        legend_items.append(
            f'<span class="pie-legend-item"{fattrs}>'
            f'<span class="lg-dot" style="background:{c}"></span>'
            f'<span class="pli-label">{esc(lab)}</span>'
            f'<span class="pli-share">{frac*100:.0f}%</span></span>'
        )
        angle += sweep
    svg.append("</svg>")

    center = ""
    if center_label:
        center = (
            '<div class="donut-center">'
            f'<div class="donut-center-val">{esc(center_label)}</div>'
            f'<div class="donut-center-sub">{esc(center_sub)}</div></div>'
        )

    return (
        '<div class="pie-block">'
        f'<div class="pie-svg-wrap donut-wrap">{"".join(svg)}{center}</div>'
        f'<div class="pie-legend">{"".join(legend_items)}</div>'
        "</div>"
    )


# --------------------------------------------------------------------------
# Grouped horizontal bars (two measures per category)
# --------------------------------------------------------------------------
def grouped_bar_h(
    labels: list[str],
    series: list[tuple[str, list[float], str]],
    *,
    width: int = 760,
    v_fmt=pct,
    label_series: int = -1,
    chart_id: str = "g",
) -> str:
    """Two measures per category.

    `label_series` fixes which series carries the direct label. Labelling
    whichever series happens to be LARGER makes the number mean a different thing
    on every row, which is worse than no label at all.
    """
    n = len(labels)
    k = len(series)
    row = 40
    pad_l, pad_r, pad_t, pad_b = 152, 62, 8, 18
    height = pad_t + pad_b + row * n
    pw = width - pad_l - pad_r
    hi = max((v for _, vals, _ in series for v in vals), default=1) * 1.04

    out = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]
    bar_h = (row - 16) / k
    for i, lab in enumerate(labels):
        y0 = pad_t + i * row + 8
        out.append(
            f'<text x="{pad_l-12}" y="{y0 + (row-16)/2 + 4:.1f}" text-anchor="end" '
            f'class="cat">{esc(lab)}</text>'
        )
        for j, (sname, vals, color) in enumerate(series):
            v = vals[i]
            # 2px gap between adjacent fills rather than a border
            y = y0 + j * bar_h + (1 if j else 0)
            w = max(v / hi * pw, 1.5)
            out.append(
                f'<rect x="{pad_l}" y="{y:.1f}" width="{w:.1f}" '
                f'height="{bar_h-2:.1f}" rx="2.5" fill="{color}" class="bar" '
                f'data-title="{esc(lab)}" data-body="{esc(sname)}: {esc(v_fmt(v))}"/>'
            )
        j = label_series % k
        out.append(
            f'<text x="{pad_l + series[j][1][i]/hi*pw + 8:.1f}" '
            f'y="{y0 + (row-16)/2 + 4:.1f}" class="val">'
            f"{esc(v_fmt(series[j][1][i]))}</text>"
        )
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Scatter
# --------------------------------------------------------------------------
@dataclass
class Point:
    x: float
    y: float
    label: str
    size: float = 1.0
    group: str = ""
    detail: str = ""


def scatter(
    points: list[Point],
    groups: list[tuple[str, str, str]],
    *,
    width: int = 760,
    height: int = 460,
    x_label: str = "",
    y_label: str = "",
    x_fmt=num,
    y_fmt=num,
    y_log: bool = False,
    med_x: float | None = None,
    med_y: float | None = None,
    quadrant_notes: list[tuple[str, str]] | None = None,
    diagonal: bool = False,
    filter_dim: str | None = None,
    point_labels: bool = False,
    x_pad_frac: float | None = None,
    quadrant_fill: bool = False,
    size_scale: str = "linear",
    chart_id: str = "s",
) -> str:
    """Bubble scatter. `groups` is [(group name, colour, svg symbol)].

    `x_pad_frac`, if given, replaces the default asymmetric 10%/8% x-axis
    padding with a bigger padding fraction applied EQUALLY on both sides.
    Use it for a measure whose real range is narrow relative to its natural
    scale (e.g. every value within a point of each other on a 0-100 scale) --
    the tight default padding alone stretches that narrow band across the
    full chart width, which visually overstates differences a reader would
    otherwise call noise. A hard floor at 0 was tried and rejected here: for
    a metric whose real minimum sits well above 0 (e.g. reach, which can't be
    near 0 given a follower-count floor), forcing the axis to start at 0
    crams every point into one edge of the chart instead of fixing the
    exaggeration -- symmetric padding widens the empty margin on BOTH sides,
    so the cluster reads as tight without also reading as lopsided.

    `quadrant_fill` tints the four regions either side of `med_x`/`med_y` --
    ported 1:1 (same four hex colours) from the reference's scatter(). It is
    purely positional context; point colour is driven by `groups`/`p.group`
    and is free to disagree with which tinted quadrant a point sits in --
    e.g. a large-audience contract that still converts badly.

    `size_scale="sqrt"` makes bubble AREA proportional to `size` (the
    reference's convention); the default "linear" (radius proportional to
    size) is kept for every existing chart so this doesn't change them."""
    # Top padding has to clear the largest bubble radius, or the biggest marker
    # gets clipped by the plot edge -- which is always the one that matters most.
    pad_l, pad_r, pad_t, pad_b = 66, 30, 34, 48
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b

    xs = [p.x for p in points]
    ys = [math.log10(max(p.y, 1e-6)) if y_log else p.y for p in points]
    xlo, xhi = min(xs), max(xs)
    ylo, yhi = min(ys), max(ys)
    # Compute the spans BEFORE mutating the bounds -- expanding lo first and then
    # deriving hi's padding from the already-widened span silently inflates the
    # top of every axis.
    xspan = (xhi - xlo) or 1
    yspan = (yhi - ylo) or 1
    if x_pad_frac is not None:
        xlo -= xspan * x_pad_frac
        xhi += xspan * x_pad_frac
        if min(xs) >= 0:
            xlo = max(xlo, 0.0)
    else:
        xlo -= xspan * 0.10
        xhi += xspan * 0.08
    ylo -= yspan * 0.12
    yhi += yspan * 0.16

    def X(v):
        return pad_l + (v - xlo) / (xhi - xlo) * pw

    def Y(v):
        v = math.log10(max(v, 1e-6)) if y_log else v
        return pad_t + ph - (v - ylo) / (yhi - ylo) * ph

    out = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]

    if quadrant_fill and med_x is not None and med_y is not None:
        mx, my = X(med_x), Y(med_y)
        x2, y2 = width - pad_r, height - pad_b
        out.append(f'<rect x="{pad_l:.1f}" y="{pad_t:.1f}" width="{mx-pad_l:.1f}" '
                    f'height="{my-pad_t:.1f}" fill="#EDF7F1" opacity=".75"/>')
        out.append(f'<rect x="{mx:.1f}" y="{pad_t:.1f}" width="{x2-mx:.1f}" '
                    f'height="{my-pad_t:.1f}" fill="#EAF0FE" opacity=".75"/>')
        out.append(f'<rect x="{mx:.1f}" y="{my:.1f}" width="{x2-mx:.1f}" '
                    f'height="{y2-my:.1f}" fill="#FDECEC" opacity=".6"/>')
        out.append(f'<rect x="{pad_l:.1f}" y="{my:.1f}" width="{mx-pad_l:.1f}" '
                    f'height="{y2-my:.1f}" fill="#F5F6F8" opacity=".8"/>')

    for t in nice_ticks(ylo, yhi, 5):
        if t < ylo or t > yhi:
            continue
        y = pad_t + ph - (t - ylo) / (yhi - ylo) * ph
        real = 10 ** t if y_log else t
        out.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{pad_l-10}" y="{y+4:.1f}" text-anchor="end" class="tick">'
            f"{esc(y_fmt(real))}</text>"
        )
    for t in nice_ticks(xlo, xhi, 5):
        if t < xlo or t > xhi:
            continue
        out.append(
            f'<text x="{X(t):.1f}" y="{height-26}" text-anchor="middle" class="tick">'
            f"{esc(x_fmt(t))}</text>"
        )

    if med_x is not None:
        out.append(
            f'<line x1="{X(med_x):.1f}" y1="{pad_t}" x2="{X(med_x):.1f}" '
            f'y2="{pad_t+ph}" stroke="{BASELINE}" stroke-width="1"/>'
        )
    if med_y is not None:
        out.append(
            f'<line x1="{pad_l}" y1="{Y(med_y):.1f}" x2="{width-pad_r}" '
            f'y2="{Y(med_y):.1f}" stroke="{BASELINE}" stroke-width="1"/>'
        )
    if diagonal:
        # y=x reference: "above the line" reads directly off the plot instead of
        # needing the axis figures compared by eye.
        lim = min(xhi, yhi if not y_log else 10 ** yhi)
        out.append(
            f'<line x1="{X(0):.1f}" y1="{Y(0):.1f}" x2="{X(lim):.1f}" y2="{Y(lim):.1f}" '
            f'stroke="{BASELINE}" stroke-width="1.2" stroke-dasharray="4 4"/>'
        )

    for pos, text in quadrant_notes or []:
        x = pad_l + 8 if "left" in pos else width - pad_r - 8
        y = pad_t + 16 if "top" in pos else pad_t + ph - 8
        anchor = "start" if "left" in pos else "end"
        out.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" class="ann">'
            f"{esc(text)}</text>"
        )

    smax = max((p.size for p in points), default=1) or 1
    by_group = {g: [] for g, _, _ in groups}
    for p in points:
        by_group.setdefault(p.group, []).append(p)

    for gname, color, symbol in groups:
        for p in by_group.get(gname, []):
            r = (5 + math.sqrt(p.size / smax) * 20 if size_scale == "sqrt"
                 else 6 + (p.size / smax) * 16)
            cx, cy = X(p.x), Y(p.y)
            body = f"{y_label}: {y_fmt(p.y)} · {x_label}: {x_fmt(p.x)}"
            if p.detail:
                body += f" · {p.detail}"
            fattrs = f' data-fdim="{esc(filter_dim)}" data-fval="{esc(p.label)}"' if filter_dim else ""
            common = (
                f'class="pt" data-title="{esc(p.label)}" data-body="{esc(body)}" '
                f'stroke="{SURFACE}" stroke-width="2"{fattrs}'
            )
            if symbol == "x":
                d = r * 0.62
                out.append(
                    f'<g {common}><circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
                    f'fill="{color}" opacity="0.30" stroke="none"/>'
                    f'<path d="M{cx-d:.1f},{cy-d:.1f} L{cx+d:.1f},{cy+d:.1f} '
                    f'M{cx+d:.1f},{cy-d:.1f} L{cx-d:.1f},{cy+d:.1f}" '
                    f'stroke="{color}" stroke-width="2.4" stroke-linecap="round" '
                    f'fill="none"/></g>'
                )
            else:
                out.append(
                    f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{color}" '
                    f'fill-opacity="0.78" {common}/>'
                )
            if point_labels:
                out.append(
                    f'<text x="{cx:.1f}" y="{cy-r-6:.1f}" text-anchor="middle" '
                    f'class="ann">{esc(p.label)}</text>'
                )

    out.append(
        f'<text x="{pad_l + pw/2:.1f}" y="{height-6}" text-anchor="middle" '
        f'class="axis-title">{esc(x_label)}</text>'
    )
    out.append(
        f'<text x="16" y="{pad_t + ph/2:.1f}" text-anchor="middle" '
        f'class="axis-title" transform="rotate(-90 16 {pad_t + ph/2:.1f})">'
        f"{esc(y_label)}</text>"
    )
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Stacked columns
# --------------------------------------------------------------------------
def stacked_columns(
    x_labels: list[str],
    series: list[tuple[str, list[float], str]],
    *,
    width: int = 760,
    height: int = 280,
    chart_id: str = "sc",
    v_fmt=None,
    filter_dim: str | None = None,
) -> str:
    pad_l, pad_r, pad_t, pad_b = 46, 16, 14, 34
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(x_labels)
    totals = [sum(s[1][i] for s in series) for i in range(n)]
    hi = max(totals) or 1
    ticks = nice_ticks(0, hi, 4)
    hi = max(hi, ticks[-1])

    out = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]
    for t in ticks:
        y = pad_t + ph - t / hi * ph
        out.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" class="tick">'
            f"{int(t)}</text>"
        )

    fmt = v_fmt or (lambda v: str(int(v)))
    cw = pw / max(n, 1)
    bw = min(cw * 0.62, 18)
    for i in range(n):
        cx = pad_l + cw * (i + 0.5)
        acc = 0.0
        for sname, vals, color in series:
            v = vals[i]
            if v <= 0:
                continue
            h = v / hi * ph
            y = pad_t + ph - (acc + v) / hi * ph
            fattrs = f' data-fdim="{esc(filter_dim)}" data-fval="{esc(sname)}"' if filter_dim else ""
            # 2px surface gap between stacked segments, not a border
            out.append(
                f'<rect x="{cx-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                f'height="{max(h-2,1):.1f}" rx="2" fill="{color}" class="bar" '
                f'data-title="{esc(x_labels[i])}" '
                f'data-body="{esc(sname)}: {esc(fmt(v))}"{fattrs}/>'
            )
            acc += v

    step = max(1, n // 8)
    for i in range(0, n, step):
        out.append(
            f'<text x="{pad_l + cw*(i+0.5):.1f}" y="{height-12}" '
            f'text-anchor="middle" class="tick">{esc(x_labels[i])}</text>'
        )
    out.append(
        f'<line x1="{pad_l}" y1="{pad_t+ph}" x2="{width-pad_r}" y2="{pad_t+ph}" '
        f'stroke="{BASELINE}" stroke-width="1"/>'
    )
    out.append("</svg>")
    return "".join(out)


def bar_chart_graded(
    x_labels: list[str],
    values: list[float],
    colors: list[str],
    tooltip_titles: list[str],
    tooltip_bodies: list[str],
    *,
    width: int = 760,
    height: int = 280,
    chart_id: str = "bcg",
    v_fmt=None,
) -> str:
    """Single-series vertical bars, coloured and annotated per bar rather
    than per series. Purpose-built for the Influencers page's metric
    comparison, where colour marks a performance band (not a category) and
    the hover needs every stat for that one influencer, not just the metric
    on the axis -- stacked_columns' per-series colouring and title/body
    can't express either."""
    pad_l, pad_r, pad_t, pad_b = 46, 16, 14, 34
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(x_labels)
    hi = max(values) if values else 1
    ticks = nice_ticks(0, hi, 4)
    hi = max(hi, ticks[-1]) or 1
    fmt = v_fmt or (lambda v: str(int(v)))

    out = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]
    for t in ticks:
        y = pad_t + ph - t / hi * ph
        out.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" class="tick">'
            f"{esc(fmt(t))}</text>"
        )

    cw = pw / max(n, 1)
    bw = min(cw * 0.62, 22)
    for i in range(n):
        cx = pad_l + cw * (i + 0.5)
        v = max(values[i], 0)
        h = v / hi * ph
        y = pad_t + ph - h
        out.append(
            f'<rect x="{cx-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" '
            f'height="{max(h,1):.1f}" rx="2" fill="{colors[i]}" class="bar" '
            f'data-title="{esc(tooltip_titles[i])}" '
            f'data-body="{esc(tooltip_bodies[i])}"/>'
        )
    for i in range(n):
        out.append(
            f'<text x="{pad_l + cw*(i+0.5):.1f}" y="{height-12}" '
            f'text-anchor="middle" class="tick">{esc(x_labels[i])}</text>'
        )
    out.append(
        f'<line x1="{pad_l}" y1="{pad_t+ph}" x2="{width-pad_r}" y2="{pad_t+ph}" '
        f'stroke="{BASELINE}" stroke-width="1"/>'
    )
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Coefficient plot with confidence intervals
# --------------------------------------------------------------------------
def coefficient_plot(
    labels: list[str],
    estimates: list[float],
    lows: list[float],
    highs: list[float],
    significant: list[bool],
    *,
    width: int = 760,
    v_fmt=lambda v: f"{v:,.1f}",
    chart_id: str = "coef",
) -> str:
    """Point estimates with 95% intervals and a zero line.

    The interval is the point of this chart, not decoration. On 8 weeks most
    channels cannot be distinguished from zero, and a bare bar chart of the point
    estimates would hide exactly that -- letting a reader treat a number the data
    cannot support as if it were established.
    """
    n = len(labels)
    row = 42
    pad_l, pad_r, pad_t, pad_b = 148, 90, 14, 30
    height = pad_t + pad_b + row * n
    pw = width - pad_l - pad_r

    lo = min(min(lows), 0.0)
    hi = max(max(highs), 0.0)
    span = (hi - lo) or 1
    lo -= span * 0.06
    hi += span * 0.06

    def X(v: float) -> float:
        return pad_l + (v - lo) / (hi - lo) * pw

    out = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]
    x0 = X(0.0)
    out.append(
        f'<line x1="{x0:.1f}" y1="{pad_t}" x2="{x0:.1f}" y2="{height-pad_b:.1f}" '
        f'stroke="{BASELINE}" stroke-width="1"/>'
    )
    out.append(
        f'<text x="{x0:.1f}" y="{height-10}" text-anchor="middle" class="tick">'
        f"no effect</text>"
    )

    for i, (lab, est, l, h, sig) in enumerate(
        zip(labels, estimates, lows, highs, significant)
    ):
        y = pad_t + i * row + row / 2
        color = SERIES[0] if sig else MUTED
        out.append(
            f'<text x="{pad_l-12}" y="{y+4:.1f}" text-anchor="end" class="cat">'
            f"{esc(lab)}</text>"
        )
        out.append(
            f'<line x1="{X(l):.1f}" y1="{y:.1f}" x2="{X(h):.1f}" y2="{y:.1f}" '
            f'stroke="{color}" stroke-width="2" stroke-linecap="round" '
            f'opacity="{"0.9" if sig else "0.55"}"/>'
        )
        for cap in (l, h):
            out.append(
                f'<line x1="{X(cap):.1f}" y1="{y-5:.1f}" x2="{X(cap):.1f}" '
                f'y2="{y+5:.1f}" stroke="{color}" stroke-width="2" '
                f'opacity="{"0.9" if sig else "0.55"}"/>'
            )
        out.append(
            f'<circle cx="{X(est):.1f}" cy="{y:.1f}" r="5.5" fill="{color}" '
            f'stroke="{SURFACE}" stroke-width="2" class="pt" '
            f'data-title="{esc(lab)}" '
            f'data-body="{esc(v_fmt(est))} (95% CI {esc(v_fmt(l))} to '
            f'{esc(v_fmt(h))}){", significant" if sig else ", not distinguishable from zero"}"/>'
        )
        note = v_fmt(est) + ("" if sig else "  n.s.")
        out.append(
            f'<text x="{width-pad_r+10}" y="{y+4:.1f}" class="val" '
            f'fill="{INK_2 if sig else MUTED}">{esc(note)}</text>'
        )
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Heatmap
# --------------------------------------------------------------------------
# Sequential ramp: ONE hue, light to dark. Never a rainbow -- a multi-hue scale
# implies categories where the data has magnitude.
SEQ_BLUE = ["#e8eefc", "#cddafa", "#a9c1f3", "#7fa2ea", "#5581df", "#3a63d6", "#2f4bd4"]


# Diverging ramp for signed quantities such as correlation: two hues that read as
# opposite, with a NEUTRAL grey midpoint so "no relationship" reads as nothing.
# Never a hue in the middle -- that implies a third category where there is none.
DIV_RED_BLUE = ["#b03030", "#cf6a5a", "#e8a898", "#efefec",
                "#9fb6e8", "#5f83db", "#2f4bd4"]


def heatmap(
    row_labels: list[str],
    col_labels: list[str],
    values: list[list[float]],
    *,
    width: int = 760,
    v_fmt=lambda v: f"{v:,.2f}",
    scale_label: str = "",
    diverging: bool = False,
    center: float = 0.0,
    filter_dim: str | None = None,
    chart_id: str = "hm",
) -> str:
    pad_l, pad_r, pad_t, pad_b = 152, 16, 46, 34
    cell_h = 38
    height = pad_t + pad_b + cell_h * len(row_labels)
    cw = (width - pad_l - pad_r) / max(len(col_labels), 1)

    flat = [v for r in values for v in r if v is not None and not math.isnan(v)]
    lo, hi = (min(flat), max(flat)) if flat else (0, 1)
    rng = (hi - lo) or 1
    # A diverging scale must be symmetric about its centre, or the midpoint colour
    # stops meaning "zero" and the chart misreads.
    half = max(abs(hi - center), abs(center - lo)) or 1

    def color_for(v):
        if v is None or math.isnan(v):
            return "#f4f4f2"
        if diverging:
            t = (v - center) / half            # -1 .. +1
            idx = int(round((t + 1) / 2 * (len(DIV_RED_BLUE) - 1)))
            return DIV_RED_BLUE[max(0, min(len(DIV_RED_BLUE) - 1, idx))]
        idx = int((v - lo) / rng * (len(SEQ_BLUE) - 1))
        return SEQ_BLUE[max(0, min(len(SEQ_BLUE) - 1, idx))]

    out = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]
    for j, cl in enumerate(col_labels):
        out.append(
            f'<text x="{pad_l + cw*(j+0.5):.1f}" y="{pad_t-14}" '
            f'text-anchor="middle" class="tick">{esc(cl)}</text>'
        )
    for i, rl in enumerate(row_labels):
        y = pad_t + i * cell_h
        out.append(
            f'<text x="{pad_l-12}" y="{y + cell_h/2 + 4:.1f}" text-anchor="end" '
            f'class="cat">{esc(rl)}</text>'
        )
        for j, cl in enumerate(col_labels):
            v = values[i][j]
            fill = color_for(v)
            fattrs = f' data-fdim="{esc(filter_dim)}" data-fval="{esc(cl)}"' if filter_dim else ""
            # 2px surface gap between cells rather than a stroke.
            out.append(
                f'<rect x="{pad_l + cw*j + 1:.1f}" y="{y+1:.1f}" '
                f'width="{cw-2:.1f}" height="{cell_h-2}" rx="3" fill="{fill}" '
                f'class="bar" data-title="{esc(rl)} · {esc(cl)}" '
                f'data-body="{esc("no data" if v is None or math.isnan(v) else v_fmt(v))}"{fattrs}/>'
            )
            if v is not None and not math.isnan(v):
                # Ink flips to white once the cell is dark enough to need it. On a
                # diverging scale both ENDS are dark, so test distance from the
                # centre rather than position along the range.
                dark = (abs(v - center) / half > 0.62 if diverging
                        else (v - lo) / rng > 0.62)
                out.append(
                    f'<text x="{pad_l + cw*(j+0.5):.1f}" y="{y + cell_h/2 + 4:.1f}" '
                    f'text-anchor="middle" class="val" '
                    f'fill="{"#ffffff" if dark else INK_2}">{esc(v_fmt(v))}</text>'
                )
    if scale_label:
        out.append(
            f'<text x="{pad_l}" y="{height-10}" class="tick">{esc(scale_label)}</text>'
        )
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Legend
# --------------------------------------------------------------------------
def legend(items: list[tuple[str, str]], symbol: str = "line",
           filter_dim: str | None = None) -> str:
    """Always present for two or more series, so identity is never colour-alone.

    When `filter_dim` is given, each chip is also a click-to-filter target --
    the same [data-fdim] mechanism the chart marks use, so a legend entry works
    as a click target for series (like per-market lines) too thin to reliably
    click on the mark itself."""
    parts = ['<div class="legend">']
    for item in items:
        label, color = item[0], item[1]
        fval = item[2] if len(item) > 2 else label
        if symbol == "dot":
            mark = f'<span class="lg-dot" style="background:{color}"></span>'
        else:
            mark = f'<span class="lg-line" style="background:{color}"></span>'
        fattrs = f' data-fdim="{esc(filter_dim)}" data-fval="{esc(fval)}"' if filter_dim else ""
        parts.append(f'<span class="lg-item"{fattrs}>{mark}{esc(label)}</span>')
    parts.append("</div>")
    return "".join(parts)


# --------------------------------------------------------------------------
# Funnel (stage volumes, e.g. impressions -> clicks -> sessions -> conversions)
# --------------------------------------------------------------------------
def funnel_chart(stages: list[tuple[str, float, str]], *, chart_id: str = "fun") -> str:
    """Trapezoids sized by sqrt(value) against the top stage, so a 10x volume
    drop doesn't read as a 10x width drop. Geometry and shading ported from
    the reference dashboard's funnelChart() (app_core.js) -- `stages` is
    (label, value, source-description) in top-to-bottom order."""
    W, row_h = 900, 62
    H = len(stages) * row_h + 16
    max_v = stages[0][1] or 1
    cx, max_w = W / 2, 520
    shades = ["#1428A0", "#2B4FC4", "#4A7DE0", "#6D9BEC"]

    out = [
        f'<svg class="chart" viewBox="0 0 {W} {H}" preserveAspectRatio="xMinYMin meet" '
        f'data-chart="{chart_id}" role="img">'
    ]
    for i, (label, value, source) in enumerate(stages):
        y = i * row_h + 8
        w = max(70.0, (value / max_v) ** 0.5 * max_w)
        nv = stages[i + 1][1] if i < len(stages) - 1 else value
        nx = max(70.0, (nv / max_v) ** 0.5 * max_w)
        shade = shades[i] if i < len(shades) else "#8FB4F2"
        step = None if i == 0 else (value / stages[i - 1][1] * 100 if stages[i - 1][1] else None)
        pct_top = value / max_v * 100 if max_v else 0.0
        step_txt = "—" if step is None else f"{step:.2f}%"
        tip = (f"Volume: {value:,.0f}<br>Of impressions: {pct_top:.2f}%"
               f"<br>Step rate: {step_txt}<br>Source: {esc(source)}")
        out.append(
            f'<path d="M{cx-w/2:.1f} {y} L{cx+w/2:.1f} {y} L{cx+nx/2:.1f} {y+row_h-14:.1f} '
            f'L{cx-nx/2:.1f} {y+row_h-14:.1f} Z" fill="{shade}" fill-opacity=".92" '
            f'data-title="{esc(label)}" data-body="{tip}"/>'
        )
        out.append(f'<text x="{cx:.1f}" y="{y+21:.1f}" text-anchor="middle" '
                    f'class="fun-label">{esc(label)}</text>')
        out.append(f'<text x="{cx:.1f}" y="{y+37:.1f}" text-anchor="middle" '
                    f'class="fun-val">{value:,.0f}</text>')
        rate_txt = "100%" if i == 0 else ("—" if step is None else f"{step:.1f}%")
        out.append(f'<text x="{cx+max_w/2+30:.1f}" y="{y+26:.1f}" class="fun-rate">{rate_txt}</text>')
        out.append(f'<text x="{cx+max_w/2+30:.1f}" y="{y+39:.1f}" class="fun-rate-sub">'
                    f'{"entry" if i == 0 else "of previous stage"}</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Lineage / modelling-structure graph
# --------------------------------------------------------------------------
LINEAGE_KIND_COLOR = {
    "source": MUTED,
    "fact": SAMSUNG_BLUE,
    "dim": FAINT,
    "analysis": SERIES[0],
    "decision": STATUS["warning"],
}


def lineage_graph(
    tiers: list[list[dict]],
    edges: list[tuple[str, str]],
    *,
    box_w: int = 150,
    box_h: int = 42,
    col_gap: int = 18,
    row_gap: int = 40,
    chart_id: str = "lineage",
) -> str:
    """A layered data-lineage diagram, top to bottom.

    `tiers` is an ordered list of rows; each row is a list of node dicts
    ({"id","label","kind"}), auto-centred horizontally. `edges` is
    (from_id, to_id) pairs, connected with a curved vertical connector.

    Purpose-built for this pipeline's exact, known, fixed shape rather than a
    general graph-layout algorithm -- ~19 nodes with real cross-tier edges
    (e.g. fact_base feeding an analysis table three tiers down) doesn't need
    a force-directed solver, just picking one clean set of coordinates.
    Vertical (not horizontal) tiers deliberately: a wide-and-short diagram
    scales down to an unreadable font on a normal page width, tall-and-narrow
    doesn't -- the page can scroll, a chart card can't usefully overflow
    sideways.
    """
    width = max(len(row) for row in tiers) * (box_w + col_gap) - col_gap + 40
    height = len(tiers) * (box_h + row_gap) - row_gap + 20

    pos: dict[str, tuple[float, float]] = {}
    for r, row in enumerate(tiers):
        row_w = len(row) * (box_w + col_gap) - col_gap
        x0 = (width - row_w) / 2
        y = 10 + r * (box_h + row_gap)
        for i, node in enumerate(row):
            pos[node["id"]] = (x0 + i * (box_w + col_gap), y)

    out = [
        f'<svg class="chart lineage" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" data-chart="{chart_id}" role="img">'
    ]

    # Edges first, so node boxes sit on top of the lines rather than under them.
    for a, b in edges:
        if a not in pos or b not in pos:
            continue
        ax, ay = pos[a]
        bx, by = pos[b]
        x1, y1 = ax + box_w / 2, ay + box_h
        x2, y2 = bx + box_w / 2, by
        my = (y1 + y2) / 2
        out.append(
            f'<path d="M{x1:.1f} {y1:.1f} C {x1:.1f} {my:.1f} {x2:.1f} {my:.1f} '
            f'{x2:.1f} {y2:.1f}" fill="none" stroke="{BASELINE}" stroke-width="1.4"/>'
        )

    for row in tiers:
        for node in row:
            x, y = pos[node["id"]]
            color = LINEAGE_KIND_COLOR.get(node["kind"], MUTED)
            out.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{box_w}" height="{box_h}" rx="7" '
                f'fill="{SURFACE}" stroke="{color}" stroke-width="1.5" '
                f'data-title="{esc(node["label"])}" data-body="{esc(node.get("sub", node["kind"]))}"/>'
            )
            out.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="4" height="{box_h}" rx="2" fill="{color}"/>'
            )
            out.append(
                f'<text x="{x+box_w/2:.1f}" y="{y+box_h/2+3.2:.1f}" text-anchor="middle" '
                f'class="lineage-label">{esc(node["label"])}</text>'
            )
    out.append("</svg>")
    return "".join(out)
