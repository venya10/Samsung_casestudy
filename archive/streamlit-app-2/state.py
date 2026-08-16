"""Power BI-style cross-filtering for Streamlit.

Clicking a mark on any chart filters every other visual on the page. The
mechanics that make that work reliably:

1.  Selections are read from ``st.session_state`` at the TOP of the script run,
    before anything is drawn. Reading a chart's return value instead would leave
    every visual above it on screen showing the previous, unfiltered numbers.

2.  Each chart declares which dimension it filters (``REGISTRY``). A chart owns
    the dimension it set: clicking empty space on that chart clears it, but a
    different chart clearing its own selection cannot wipe it. Without ownership
    two visuals bound to the same dimension fight each other every rerun.

3.  A per-chart signature guard stops an unchanged selection from being
    re-applied on every rerun -- otherwise dismissing a filter chip would be
    instantly undone by the selection still sitting in widget state.

4.  Dismissing a chip bumps that one chart's nonce, which changes its widget key
    and gives it a fresh, unselected widget. Bumping a single global nonce would
    reset every chart and clear filters the user never touched.
"""
from __future__ import annotations

import streamlit as st

DIMS = ["market", "channel", "product", "week"]
DIM_LABEL = {"market": "Market", "channel": "Channel",
             "product": "Product", "week": "Week"}

# chart key -> dimension it filters
REGISTRY: dict[str, str] = {}


def bind(key: str, dim: str, values: list[list] | None = None,
         field: str | None = None) -> str:
    """Register a chart as a filter source and return its nonce-qualified key.

    ``values[curve_number][point_index]`` resolves a clicked point to a dimension
    value. It is stashed in session state because ``consume`` runs before any
    chart is drawn, so it must read the lookup built during the previous render --
    which is precisely the render the user clicked on.
    """
    init()
    REGISTRY[key] = dim
    st.session_state["_xf_map"][key] = (values, field)
    return f"{key}~{st.session_state['_xf_nonce'].get(key, 0)}"


def init() -> None:
    st.session_state.setdefault("xf", {})        # dim -> {"values": [...], "src": key}
    st.session_state.setdefault("_xf_sig", {})   # key -> last processed tuple
    st.session_state.setdefault("_xf_nonce", {})  # key -> int
    st.session_state.setdefault("_xf_map", {})   # key -> (values, field)


def _points(ev) -> list[dict]:
    """Streamlit's selection payload allows both attribute and key access."""
    if ev is None:
        return []
    sel = getattr(ev, "selection", None)
    if sel is None and isinstance(ev, dict):
        sel = ev.get("selection")
    if sel is None:
        return []
    pts = getattr(sel, "points", None)
    if pts is None and isinstance(sel, dict):
        pts = sel.get("points")
    return list(pts or [])


def _resolve(p: dict, values: list[list] | None, field: str | None):
    """Turn one selection point into the dimension value it stands for."""
    if values is not None:
        c, i = p.get("curve_number"), p.get("point_index")
        if c is None or i is None:
            return None
        try:
            return values[int(c)][int(i)]
        except (IndexError, TypeError, ValueError):
            return None
    return p.get(field or "y")


def consume() -> None:
    """Fold every registered chart's selection into the filter state."""
    init()
    xf, sigs, nonces = (st.session_state["xf"], st.session_state["_xf_sig"],
                        st.session_state["_xf_nonce"])
    maps = st.session_state["_xf_map"]

    for key, dim in REGISTRY.items():
        ev = st.session_state.get(f"{key}~{nonces.get(key, 0)}")
        if ev is None:
            continue
        values, field = maps.get(key, (None, None))

        vals = []
        for p in _points(ev):
            v = _resolve(p, values, field)
            if v is not None and v not in vals:
                vals.append(v)
        # Week arrives from plotly as a float; keep dimension types honest.
        if dim == "week":
            vals = [int(v) for v in vals]
        vals = tuple(sorted(vals, key=str))

        if sigs.get(key) == vals:
            continue
        sigs[key] = vals

        if vals:
            xf[dim] = {"values": list(vals), "src": key}
        elif xf.get(dim, {}).get("src") == key:
            xf.pop(dim)


# --------------------------------------------------------------------------
# reading / mutating
# --------------------------------------------------------------------------
def active() -> dict[str, list]:
    return {d: v["values"] for d, v in st.session_state.get("xf", {}).items()}


def signature() -> tuple:
    """Hashable key for caching a recompute."""
    return tuple(sorted((d, tuple(map(str, v))) for d, v in active().items()))


def is_filtered(dim: str | None = None) -> bool:
    a = active()
    return bool(a) if dim is None else dim in a


def clear(dim: str) -> None:
    entry = st.session_state["xf"].pop(dim, None)
    if entry:  # give the owning chart a fresh widget so its marks deselect
        n = st.session_state["_xf_nonce"]
        n[entry["src"]] = n.get(entry["src"], 0) + 1


def clear_all() -> None:
    for dim in list(st.session_state.get("xf", {})):
        clear(dim)


# --------------------------------------------------------------------------
# explicit dropdown filters (Overview page)
# --------------------------------------------------------------------------
# These write into the same `xf` dict a chart click does, under src="filter_bar",
# so a dropdown selection and a chart click are two doors into one filter state --
# not two competing mechanisms. The one thing a dropdown needs that a chart click
# doesn't: if a chart click (or a different dropdown's Reset) changes xf[dim] out
# from under it, the multiselect widget must be force-remounted (its `default` is
# only honoured the first time Streamlit sees a given widget key), or it would
# silently keep showing a stale selection. `_filter_last_src` records what set
# xf[dim] last time this ran, so a change in *who* set it -- not just a change to
# "filter_bar" itself, which is this widget's own write landing back -- is what
# triggers that remount.
def _filter_state():
    st.session_state.setdefault("_filter_nonce", {})
    st.session_state.setdefault("_filter_last_src", {})
    return st.session_state["_filter_nonce"], st.session_state["_filter_last_src"]


def filter_bar_controls(options: dict[str, list], label_fns: dict[str, callable] | None = None,
                        scope_note: str | None = None) -> None:
    """One popover-pill dropdown per dimension in ``options``, e.g.
    ``{"week": [1..8], "market": [...], "channel": [...], "product": [...]}``.
    ``label_fns`` optionally maps a dim to a display-label function (e.g. market
    codes -> "SGE (Gulf)"). ``scope_note`` is a right-aligned status string, e.g.
    "1,687 of 2,360 fact rows in scope".
    """
    init()
    nonces, last_src = _filter_state()
    xf = st.session_state["xf"]
    dims = list(options.keys())
    label_fns = label_fns or {}

    box = st.container(key="page_filter_bar")
    widths = [1.1] * len(dims) + [1.0, 1.6]
    cols = box.columns(widths, gap="small")

    for i, dim in enumerate(dims):
        cur_src = xf.get(dim, {}).get("src")
        if cur_src != last_src.get(dim) and cur_src != "filter_bar":
            nonces[dim] = nonces.get(dim, 0) + 1   # set by something else -> remount

        all_vals = options[dim]
        current = xf.get(dim, {}).get("values", list(all_vals))
        key = f"filt_{dim}~{nonces.get(dim, 0)}"
        fmt = label_fns.get(dim, str)

        # The popover's label has to be fixed before its body (where the
        # multiselect lives) is even rendered -- computing it from `xf` would
        # make it one interaction behind, since xf[dim] is only written further
        # below, AFTER the button (and its label) has already been drawn. The
        # widget's own persisted value under `key`, in contrast, is already
        # updated by Streamlit before this rerun starts -- that's how a widget's
        # return value can reflect a click that just happened -- so peeking at
        # it here is what makes the pill's "N selected" summary current instead
        # of stale by one click.
        label_vals = st.session_state.get(key, current)
        n = len(label_vals)
        summary = "All" if n == len(all_vals) else f"{n} selected" if n else "None"

        with cols[i]:
            with st.popover(f"{DIM_LABEL[dim].upper()}   {summary}",
                            use_container_width=True):
                selected = st.multiselect(
                    DIM_LABEL[dim], all_vals, default=current, key=key,
                    format_func=fmt, label_visibility="collapsed")

        # Only touch xf if the SET of selected values actually differs from
        # `current` -- right after a remount, `selected` always equals `current`
        # (it's just the `default` echoed back), because nothing has changed yet.
        # Writing unconditionally here would reassign a chart-click's filter to
        # "filter_bar" ownership the very next time this function renders, purely
        # because it displayed that chart's selection -- not because the user
        # touched the widget. That silent ownership steal is exactly what broke
        # "clicking empty space on the owning chart clears its own filter": the
        # chart no longer owned it by the time it tried.
        if set(selected) != set(current):
            if not selected or set(selected) == set(all_vals):
                if xf.get(dim, {}).get("src") == "filter_bar":
                    del xf[dim]
            else:
                xf[dim] = {"values": selected, "src": "filter_bar"}
        last_src[dim] = xf.get(dim, {}).get("src")

    with cols[len(dims)]:
        if st.button("Reset filters", key="filter_bar_reset"):
            for dim in dims:
                xf.pop(dim, None)
                nonces[dim] = nonces.get(dim, 0) + 1
                last_src[dim] = None
            st.rerun()

    if scope_note:
        with cols[len(dims) + 1]:
            st.markdown(f'<div class="filter-scope-note">{scope_note}</div>',
                        unsafe_allow_html=True)


def standard_filter_bar() -> None:
    """The one filter row every page calls: Week / Channel / Product / Market
    dropdowns plus a live "N of M fact rows in scope" note. A single shared
    entry point, not a pattern each page re-derives, so every page's filter bar
    is identical by construction -- a page added later gets it for free by
    calling this, rather than by copying four lines of options/labels and
    hoping they stay in sync with the other seven.
    """
    import data          # local import: state.py must not depend on data.py at
    from common import CHANNELS, MARKETS, PRODUCTS, WEEKS, market_label  # module load time (data.py imports state.py)

    total = len(data.load()["fact_base"])
    filter_bar_controls(
        {"week": WEEKS, "channel": CHANNELS, "product": PRODUCTS, "market": MARKETS},
        label_fns={"market": market_label},
        scope_note=f"{len(apply(data.load()['fact_base'])):,} of {total:,} fact rows in scope")


def apply(df, dims: list[str] | None = None):
    """Filter a frame on whichever active dimensions it actually has columns for."""
    if df is None or not len(df):
        return df
    for dim, vals in active().items():
        if dims is not None and dim not in dims:
            continue
        if dim in df.columns:
            df = df[df[dim].isin(vals)]
    return df


# --------------------------------------------------------------------------
# the filter bar
# --------------------------------------------------------------------------
def bar(hint: str = "Click any chart to filter the page") -> None:
    a = active()
    if not a:
        st.markdown(
            f'<div class="fbar"><span class="fbar-l">Filters</span>'
            f'<span class="fbar-none">None — showing all 8 markets, 8 channels, '
            f'6 products, 8 weeks</span>'
            f'<span class="fbar-hint">{hint}</span></div>', unsafe_allow_html=True)
        return

    chips = "".join(
        f'<span class="chip"><span class="dim">{DIM_LABEL[d]}</span>'
        f'{", ".join(str(x) for x in v[:3])}'
        f'{f" +{len(v) - 3}" if len(v) > 3 else ""}</span>'
        for d, v in a.items())
    st.markdown(
        f'<div class="fbar"><span class="fbar-l">Filters</span>{chips}'
        f'<span class="fbar-hint">{hint}</span></div>', unsafe_allow_html=True)

    cols = st.columns(len(a) + 2)
    for i, dim in enumerate(a):
        if cols[i].button(f"✕ {DIM_LABEL[dim]}", key=f"clr_{dim}",
                          use_container_width=True):
            clear(dim)
            st.rerun()
    if cols[len(a)].button("Reset all", key="clr_all", use_container_width=True):
        clear_all()
        st.rerun()
