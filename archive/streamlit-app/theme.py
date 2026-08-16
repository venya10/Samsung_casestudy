"""Shared visual language for the dashboard.

One place for the palette, the Plotly template and the components every page
reuses, so the five pages read as one product rather than five notebooks.

Colour rules applied throughout (and why):
  * Categorical hues are assigned in a FIXED order and never cycled. A chart that
    would need a ninth colour folds its tail into "Other" or facets instead.
  * Charts showing one measure across many channels use ONE hue with emphasis on
    the extremes -- not eight hues. Eight colours for one measure double-encodes
    bar length as hue and burns the only free channel.
  * Scatter plots cap at the first three categorical slots: with every pair of
    points adjacent on screen, more than three cannot stay distinguishable under
    colour-vision deficiency.
  * Status colours (good/warning/critical) are reserved for state and always ship
    with a word or glyph, never colour alone.
  * No dual-axis charts anywhere. Two measures on different scales get two charts
    or an indexed common base.
"""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
SERIES = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]
# Scatter / all-pairs charts must not exceed these three.
SERIES_SCATTER = SERIES[:3]

STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}
SEVERITY_COLOR = {
    "critical": STATUS["critical"],
    "high": STATUS["serious"],
    "medium": STATUS["warning"],
}
SEVERITY_GLYPH = {"critical": "●", "high": "▲", "medium": "■"}

SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SUCCESS_TEXT = "#006300"

MARKET_COLOR = {"UAE": SERIES[0], "KSA": SERIES[1], "Egypt": SERIES[2]}

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


# --------------------------------------------------------------------------
# Plotly template
# --------------------------------------------------------------------------
def install_template() -> None:
    pio.templates["samsung"] = go.layout.Template(
        layout=dict(
            font=dict(family=FONT, size=13, color=INK_2),
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            colorway=SERIES,
            margin=dict(l=8, r=8, t=48, b=8),
            title=dict(font=dict(size=15, color=INK), x=0, xanchor="left", pad=dict(b=12)),
            hoverlabel=dict(
                bgcolor=SURFACE, bordercolor=BASELINE,
                font=dict(family=FONT, size=12, color=INK),
            ),
            xaxis=dict(
                showgrid=False, zeroline=False,
                linecolor=BASELINE, linewidth=1, ticks="outside", ticklen=4,
                tickcolor=BASELINE, tickfont=dict(color=MUTED, size=11),
            ),
            yaxis=dict(
                showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False,
                showline=False, tickfont=dict(color=MUTED, size=11),
            ),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                font=dict(size=12, color=INK_2), bgcolor="rgba(0,0,0,0)",
            ),
        )
    )
    pio.templates.default = "samsung"


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------
CSS = f"""
<style>
  .stApp {{ background: {PAGE}; }}
  .block-container {{ padding-top: 2.2rem; max-width: 1400px; }}
  h1, h2, h3 {{ font-family: {FONT}; color: {INK}; letter-spacing: -0.01em; }}
  h1 {{ font-size: 1.65rem; font-weight: 640; }}
  h2 {{ font-size: 1.15rem; font-weight: 620; margin-top: 1.6rem; }}

  .kpi-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 4px 0 18px 0; }}
  .kpi {{
    flex: 1 1 160px; background: {SURFACE}; border: 1px solid rgba(11,11,11,0.10);
    border-radius: 10px; padding: 14px 16px 12px 16px;
  }}
  .kpi-label {{
    font-family: {FONT}; font-size: 0.72rem; color: {MUTED};
    text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600;
  }}
  .kpi-value {{
    font-family: {FONT}; font-size: 1.6rem; font-weight: 640; color: {INK};
    line-height: 1.25; margin-top: 3px;
  }}
  .kpi-delta {{ font-family: {FONT}; font-size: 0.8rem; font-weight: 600; margin-top: 2px; }}
  .kpi-sub {{ font-family: {FONT}; font-size: 0.74rem; color: {MUTED}; margin-top: 2px; }}

  .note {{
    background: {SURFACE}; border-left: 3px solid {SERIES[0]};
    border-radius: 0 8px 8px 0; padding: 11px 14px; margin: 10px 0 16px 0;
    font-family: {FONT}; font-size: 0.86rem; color: {INK_2}; line-height: 1.5;
  }}
  .alert-card {{
    background: {SURFACE}; border: 1px solid rgba(11,11,11,0.10);
    border-left-width: 4px; border-radius: 8px; padding: 12px 15px; margin-bottom: 10px;
  }}
  .alert-head {{ font-family: {FONT}; font-weight: 640; font-size: 0.95rem; color: {INK}; }}
  .alert-meta {{ font-family: {FONT}; font-size: 0.76rem; color: {MUTED};
    text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }}
  .alert-body {{ font-family: {FONT}; font-size: 0.85rem; color: {INK_2};
    margin-top: 6px; line-height: 1.5; }}
  .synthetic {{
    background: #fff6e5; border: 1px solid {STATUS['warning']}; border-radius: 8px;
    padding: 9px 13px; font-family: {FONT}; font-size: 0.8rem; color: #6b4c00;
    margin-bottom: 14px;
  }}
</style>
"""


def page_setup(title: str, icon: str = "📊") -> None:
    st.set_page_config(page_title=f"{title} · Samsung MENA MI", page_icon=icon, layout="wide")
    install_template()
    st.markdown(CSS, unsafe_allow_html=True)


def synthetic_banner() -> None:
    st.markdown(
        '<div class="synthetic"><b>Synthetic data.</b> Every figure on this '
        "dashboard is generated placeholder data, not Samsung data. The pipeline, "
        "model and alerting are real; swap the files in <code>data/raw/</code> and "
        "re-run to see actual results.</div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------
def fmt_money(v: float, decimals: int = 0) -> str:
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1_000_000_000:
        return f"${v/1_000_000_000:,.2f}B"
    if a >= 1_000_000:
        return f"${v/1_000_000:,.1f}M"
    if a >= 1_000:
        return f"${v/1_000:,.0f}K"
    return f"${v:,.{decimals}f}"


def fmt_num(v: float) -> str:
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1_000_000:
        return f"{v/1_000_000:,.1f}M"
    if a >= 1_000:
        return f"{v/1_000:,.0f}K"
    return f"{v:,.0f}"


def kpi_tiles(tiles: list[dict]) -> None:
    """Render a row of KPI tiles.

    Each tile: {label, value, delta (fraction, optional), sub (optional),
                good_when_up (default True)}.
    The delta shows an arrow glyph as well as a colour, so the direction is never
    carried by colour alone.
    """
    html = ['<div class="kpi-row">']
    for t in tiles:
        delta_html = ""
        d = t.get("delta")
        if d is not None:
            up = d >= 0
            good = up if t.get("good_when_up", True) else not up
            color = SUCCESS_TEXT if good else STATUS["critical"]
            arrow = "▲" if up else "▼"
            delta_html = (
                f'<div class="kpi-delta" style="color:{color}">'
                f"{arrow} {abs(d):.1%} WoW</div>"
            )
        sub_html = f'<div class="kpi-sub">{t["sub"]}</div>' if t.get("sub") else ""
        html.append(
            f'<div class="kpi"><div class="kpi-label">{t["label"]}</div>'
            f'<div class="kpi-value">{t["value"]}</div>{delta_html}{sub_html}</div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<div class="note">{text}</div>', unsafe_allow_html=True)


def emphasis_colors(values, highlight_top: int = 1, highlight_bottom: int = 1) -> list[str]:
    """One hue for a single measure, with the extremes picked out.

    Eight categorical hues for one measure across eight channels would double-encode
    bar length as colour. Instead everything is slot-1 blue, the best few are kept
    saturated and the worst few are marked with the critical status colour -- the
    reading is 'these are the outliers', not 'these are different categories'.
    """
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    top = set(order[:highlight_top])
    bottom = set(order[-highlight_bottom:]) if highlight_bottom else set()
    out = []
    for i in range(len(values)):
        if i in top:
            out.append(SERIES[0])
        elif i in bottom:
            out.append(STATUS["critical"])
        else:
            out.append("#a9c8ee")  # recessive step of the same blue ramp
    return out


def chart(fig: go.Figure, height: int = 340, table: "pd.DataFrame | None" = None,
          table_label: str = "View as table") -> None:
    """Render a figure at a sensible height with its table-view twin.

    Every chart ships a table so no value is reachable only by hovering.
    """
    fig.update_layout(height=height)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    if table is not None:
        with st.expander(table_label):
            st.dataframe(table, use_container_width=True, hide_index=True)
