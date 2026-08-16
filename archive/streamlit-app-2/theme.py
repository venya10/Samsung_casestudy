"""Samsung design system for the Streamlit app.

Streamlit's default chrome is hidden and replaced with the same visual language as
the static site, updated to the black-primary direction Samsung's current branding
has moved toward: a solid black sidebar carries navigation and identity, the content
area stays white for readability, and blue is demoted from "chrome colour" to a
single restrained accent (active nav state, links, chart data). The goal is that
nothing on screen says "Streamlit".

Colour rules:
  * Black is the primary chrome colour (sidebar). Samsung Blue #1428A0 is an
    accent, not chrome -- used only for the active nav indicator, links, chips,
    and (as a lighter validated step, SERIES[0]) chart data. At OKLCH L=0.364 the
    raw brand blue sits below the categorical lightness band and would fail
    colour-vision separation as a data series colour, which is why SERIES[0] is a
    lighter step of the same hue rather than the literal brand hex.
  * One measure across many categories gets one hue with the extremes picked out.
  * Status colours are reserved for state and ship with a word, never colour alone.
"""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]

# ---- chrome (sidebar) -- black is primary ---------------------------------
BLACK = "#0a0a0a"
BLACK_2 = "#151515"           # elevated surface on black (hover)

# ---- accent -- used sparingly: active state, links, chips, chart data -----
SAMSUNG_BLUE = "#1428A0"
SAMSUNG_BLUE_DARK = "#0d1c73"
SERIES = ["#2f4bd4", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SERIES_MUTED = "#b9c4ee"
STATUS = {"good": "#0ca30c", "warning": "#fab219",
          "serious": "#ec835a", "critical": "#d03b3b"}
SUCCESS_TEXT = "#006300"
ACCENT = SERIES[0]            # #2f4bd4 -- the on-white AND on-black accent blue

# ---- content surface -------------------------------------------------------
# PAGE is a neutral, cool-toned light grey -- deliberately distinct from
# SURFACE (card white) this time, for depth: white cards should read as
# lifted off a grey canvas. That's different from the earlier PAGE==SURFACE
# fix, which existed because cards had a hard 1px *border* back then -- a
# border makes any gap between page and card colour look like a stray extra
# frame around the page. Cards are shadow-only now (see the "cards" section
# below), so the same grey canvas reads as intentional elevation instead.
PAGE = "#f4f5f7"
SURFACE = "#ffffff"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#8a8a86"
GRID = "#eceae4"
BASELINE = "#d6d4cc"

FONT = ('"Inter", -apple-system, "SF Pro Display", "Segoe UI", Roboto, '
       '"Helvetica Neue", Arial, sans-serif')
# DISPLAY_FONT and MONO_FONT match the reference dashboard's own font roles
# (Manrope for KPI values, IBM Plex Mono for labels/eyebrows/numeric captions).
# Scoped to the KPI card and filter-pill text specifically, not applied
# site-wide -- the rest of the UI keeps the Inter-based FONT already in place.
DISPLAY_FONT = '"Manrope", ' + FONT
MONO_FONT = '"IBM Plex Mono", ui-monospace, "SF Mono", "Cascadia Code", monospace'

NAV_ICONS = {
    "Overview": "space_dashboard", "Channels": "campaign",
    "Portfolio": "inventory_2", "Influencers": "diversity_3",
    "Brand & Share": "visibility", "Early Warning": "warning",
    "Data": "table_chart", "AI Assistant": "auto_awesome",
}


def logo_svg() -> str:
    return (ROOT / "assets" / "samsung-wordmark.svg").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Plotly template
# --------------------------------------------------------------------------
def install_template() -> None:
    pio.templates["samsung"] = go.layout.Template(
        layout=dict(
            font=dict(family=FONT, size=13, color=INK_2),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=SERIES,
            margin=dict(l=8, r=8, t=10, b=8),
            hoverlabel=dict(bgcolor="#1a1a19", bordercolor="#1a1a19",
                            font=dict(family=FONT, size=12, color="#fff")),
            xaxis=dict(showgrid=False, zeroline=False, linecolor=BASELINE,
                       linewidth=1, ticks="outside", ticklen=4, tickcolor=BASELINE,
                       tickfont=dict(color=MUTED, size=11), automargin=True),
            yaxis=dict(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False,
                       showline=False, tickfont=dict(color=MUTED, size=11),
                       automargin=True),
            # bordercolor/borderwidth aren't cosmetic no-ops here: Plotly draws a
            # legend border by default regardless of bgcolor, and a transparent
            # *fill* alone leaves that 1px stroke in place. Every chart's legend
            # sits at the same relative height, so side-by-side charts each drawing
            # that same thin line independently reads as one continuous rule
            # running across both cards -- it isn't a shared element, just two
            # identical strokes that happen to line up.
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left",
                        x=0, font=dict(size=12, color=INK_2),
                        bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
                        borderwidth=0),
            # "event+select" is what makes a click register as a *selection* rather
            # than a transient event, which is what Streamlit reads back. Leave
            # dragmode alone: setting it to False disables the selection layer and
            # clicks stop registering at all.
            clickmode="event+select",
        )
    )
    pio.templates.default = "samsung"


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Manrope:wght@700;800&family=IBM+Plex+Mono:wght@500;600&display=swap');

/* ---- strip Streamlit chrome so nothing on screen says "Streamlit" ---- */
#MainMenu, footer, header[data-testid="stHeader"] {{ display: none !important; }}
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"] {{ display: none !important; }}
/* No max-width cap: the reference layout uses the full width available,
   whatever that is at a given sidebar state -- a fixed cap here is exactly
   what was leaving a dead gutter on wide screens and not reclaiming the
   sidebar's space when it collapsed. Padding alone defines the gutters. */
[data-testid="stAppViewBlockContainer"],
.block-container {{ padding: 1.6rem 2rem 3rem !important; max-width: none !important; }}
[data-testid="stVerticalBlock"] {{ gap: .5rem; }}
.stApp {{ background: {PAGE}; }}
html, body, [class*="css"] {{ font-family: {FONT}; }}

/* ============================== sidebar ================================ */
/* Streamlit drives the sidebar's width with an inline style (resizable by
   the user, animated to ~0 on collapse) and exposes the state on the element
   itself as `aria-expanded` -- there is no separate "isActive"-style prop
   filtering here, this one really is on the DOM. A `min-width` with
   `!important` was overriding that inline collapse width, which is why the
   sidebar visually never shrank and the content next to it never reclaimed
   the space: fixed-width styling only applies while expanded, and the
   collapse transition is left alone entirely. */
[data-testid="stSidebar"] {{ background: {BLACK}; }}
[data-testid="stSidebar"][aria-expanded="true"] {{
  min-width: 230px !important; max-width: 246px !important;
}}
[data-testid="stSidebarContent"] {{
  display: flex; flex-direction: column; padding-top: 0;
}}
[data-testid="stSidebarHeader"] {{ order: 0; padding: 0; }}
[data-testid="stSidebarHeader"] svg {{ color: rgba(255,255,255,.55); }}
[data-testid="stSidebarUserContent"] {{ order: 1; padding: 0 !important; }}
[data-testid="stSidebarNav"] {{ order: 2; padding: 4px 12px 12px; }}
[data-testid="stSidebarCollapseButton"] button {{ color: rgba(255,255,255,.6); }}

/* The collapsed-state re-expand control and the expanded-state collapse
   button are two separate elements that Streamlit is only supposed to show
   one of at a time: while expanded, the opaque sidebar (later in the DOM, so
   painted on top by default) simply covers the collapsed-control sitting
   underneath it at the same corner -- that's the whole mechanism, no
   display:none involved. Forcing a high z-index here to make it visible
   against the light page (correct once actually collapsed) also lifted it
   ABOVE the sidebar while expanded, which is what produced two visible
   arrows at once. Left at the default stacking (no z-index override) so the
   sidebar's own opacity does the hiding, the way it's designed to. */
[data-testid="stSidebarCollapsedControl"] {{ top: 14px !important; left: 14px !important; }}
[data-testid="stSidebarCollapsedControl"] button {{
  background: {BLACK} !important; border-radius: 8px !important;
  box-shadow: 0 3px 10px rgba(0,0,0,.18);
}}
[data-testid="stSidebarCollapsedControl"] button svg {{ color: #fff !important; fill: #fff !important; }}

/* brand block -- rendered into the sidebar's user-content slot, reordered
   above the native nav (which Streamlit always renders in a fixed slot of
   its own, immune to call order) via the flex `order` rules above. */
.st-key-sidebar_brand {{
  padding: 26px 22px 20px; border-bottom: 1px solid rgba(255,255,255,.09);
  margin-bottom: 8px;
}}
.sb-logo svg {{ width: 122px; height: auto; color: #fff; display: block; margin-bottom: 14px; }}
.sb-name {{ color: #fff; font-size: 13.5px; font-weight: 660; letter-spacing: -.005em; }}
.sb-meta {{ color: rgba(255,255,255,.42); font-size: 11px; margin-top: 4px; letter-spacing: .01em; }}

/* nav items -- icon + label rows, consistent spacing, one active state */
[data-testid="stSidebarNavItems"] {{ display: flex; flex-direction: column; gap: 2px; }}
[data-testid="stSidebarNavLink"] {{
  display: flex !important; align-items: center; gap: 13px;
  padding: 9px 14px !important; border-radius: 9px;
  color: rgba(255,255,255,.56) !important; font-size: 13.8px; font-weight: 500;
  text-decoration: none; transition: background .12s ease, color .12s ease;
  min-height: 0 !important; height: auto !important;
}}
[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"] {{
  font-size: 19px; color: inherit; opacity: .9;
}}
[data-testid="stSidebarNavLink"] span {{ color: inherit; }}
[data-testid="stSidebarNavLink"]:hover {{
  background: rgba(255,255,255,.055); color: #fff !important;
}}
[data-testid="stSidebarNavLink"].nav-active {{
  background: rgba(255,255,255,.1); color: #fff !important; font-weight: 630;
}}
[data-testid="stSidebarNavLink"].nav-active [data-testid="stIconMaterial"] {{
  color: {ACCENT}; opacity: 1;
}}

/* section grouping -- st.navigation(pages: dict[str, list[Page]]) renders a
   stSidebarNavSeparator before each group after the first; the group's own
   heading text is a normal small-caps label Streamlit renders above its
   items, styled here to match the rest of the sidebar's restraint. */
[data-testid="stSidebarNavSeparator"] {{
  border-top: 1px solid rgba(255,255,255,.08); margin: 10px 14px 2px;
}}
[data-testid="stNavSectionHeader"] {{
  font-size: 10.5px !important; font-weight: 700 !important; letter-spacing: .09em;
  text-transform: uppercase; color: rgba(255,255,255,.34) !important;
  margin: 10px 14px 4px !important; padding: 0 !important; background: transparent !important;
}}

/* ------------------------------- headings ----------------------------- */
.eyebrow {{
  font-size: 11px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: {ACCENT}; margin-bottom: 5px;
}}
h1.page-h1 {{
  font-size: 26px; font-weight: 720; letter-spacing: -.024em; color: {INK};
  margin: 0 0 5px; line-height: 1.16;
}}
/* No max-width here: the content column itself no longer has one either
   (the "wasted space" fix), so a leftover ch-based cap on just this
   paragraph made it wrap far short of where every other element on the
   page actually ends -- the "line break appears halfway across the page"
   look. It now wraps at the same width as the filter bar and KPI grid
   below it, and gets real breathing room before them instead of 4px. */
p.lede {{ font-size: 14.5px; color: {INK_2}; margin: 0 0 18px; line-height: 1.55; }}
.sec {{
  font-size: 12px; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; color: {MUTED}; margin: 20px 0 8px;
  padding-bottom: 7px; border-bottom: 1px solid #e4e2db;
}}

/* ------------------------------- kpi ---------------------------------- */
/* Structure and values ported from the reference dashboard's .kpi / .kpi.hero
   (samsung-marketing-intelligence/dashboard/template.html): card -> .lab
   (+ optional .flag) -> .val (+ optional .u unit) -> .foot (.delta badge +
   .vs caption) -> .spark sparkline. app/kpi.py generates this exact markup. */
.kpirow {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap: 10px; margin-bottom: 4px; }}
.kpi {{
  background: {SURFACE}; border-radius: 14px; padding: 15px 16px 12px;
  box-shadow: 0 1px 3px rgba(20,20,15,.05), 0 5px 16px rgba(20,20,15,.05);
  position: relative; overflow: hidden;
  transition: box-shadow .16s ease, transform .16s ease;
}}
.kpi:hover {{
  box-shadow: 0 2px 6px rgba(20,20,15,.07), 0 10px 26px rgba(20,20,15,.08);
  transform: translateY(-1px);
}}
.kpi .lab {{
  font-family: {MONO_FONT}; font-size: 9.5px; font-weight: 600; letter-spacing: .12em;
  text-transform: uppercase; color: {MUTED}; display: flex; align-items: center; gap: 5px;
}}
.kpi .val {{
  font-family: {DISPLAY_FONT}; font-size: 25px; font-weight: 800; letter-spacing: -.035em;
  color: {INK}; margin: 7px 0 2px; font-variant-numeric: tabular-nums; line-height: 1.1;
}}
.kpi .val .u {{ font-family: {FONT}; font-size: 13px; font-weight: 600; color: {MUTED}; letter-spacing: -.01em; }}
.kpi .foot {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; }}
.kpi .delta {{
  display: inline-flex; align-items: center; gap: 3px; font-family: {MONO_FONT};
  font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 5px;
}}
.kpi .delta.up {{ color: {SUCCESS_TEXT}; background: #e6f5ef; }}
.kpi .delta.down {{ color: {STATUS['critical']}; background: #fdecec; }}
.kpi .delta.flat {{ color: {MUTED}; background: #eff2f7; }}
.kpi .vs {{ font-size: 10.5px; color: {MUTED}; }}
.kpi .spark {{ height: 26px; width: 100%; margin-top: 6px; display: block; }}
.kpi .flag {{
  font-family: {MONO_FONT}; font-size: 8.5px; letter-spacing: .08em; text-transform: uppercase;
  padding: 1px 5px; border-radius: 4px; background: #fdf3e3; color: {STATUS['warning']};
  font-weight: 600; cursor: help;
}}
/* hero -- the page's single primary/composite metric, where one exists */
.kpi.hero {{
  background: linear-gradient(155deg, #101B4E 0%, {SAMSUNG_BLUE} 55%, #1E3FC4 100%);
  color: #fff;
}}
.kpi.hero .lab {{ color: rgba(255,255,255,.62); }}
.kpi.hero .val {{ color: #fff; }}
.kpi.hero .val .u, .kpi.hero .vs {{ color: rgba(255,255,255,.6); }}
.kpi.hero .delta.up {{ background: rgba(255,255,255,.15); color: #8FE8C0; }}
.kpi.hero .delta.down {{ background: rgba(255,255,255,.15); color: #FFB3B3; }}
.kpi.hero .delta.flat {{ background: rgba(255,255,255,.15); color: rgba(255,255,255,.75); }}

/* ------------------------------- cards -------------------------------- */
/* Streamlit wraps every st.container() -- keyed or not, bordered or not -- in
   a stVerticalBlockBorderWrapper div, so this rule paints EVERY keyed
   container white by default, not just the bordered content-area "cards" it
   was written for. That's invisible on a white page but shows up as a stray
   white box behind the black sidebar's own keyed containers (brand block,
   chat FAB), so those are explicitly neutralised below.

   Streamlit's own default border for st.container(border=True) is a solid
   1px line -- fine for one card on its own, but two cards in the same row
   both start at the same y, so their two independent top edges sit flush
   against each other with nothing but a plain white gap between: nothing
   visually marks where one card's border ends and the next one's begins, so
   it reads as one continuous rule spanning the whole row. Traded for a
   borderless card with a soft shadow instead -- separation now comes from
   the shadow's falloff and the gap between columns, not a hard-edged line
   that has nowhere to break. */
/* Soft blurred shadows only -- no hard 1px ring (box-shadow's `0 0 0 1px`
   trick is just a border by another name and would reproduce the exact same
   "shared line" problem across a row of cards). */
[data-testid="stVerticalBlockBorderWrapper"] {{
  background: {SURFACE}; border-radius: 10px; border: none !important;
  box-shadow: 0 1px 3px rgba(20,20,15,.05), 0 5px 16px rgba(20,20,15,.05);
}}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"],
.st-key-chat_fab [data-testid="stVerticalBlockBorderWrapper"] {{
  background: transparent !important; border-radius: 0; box-shadow: none !important;
}}
.card-h {{ font-size: 15px; font-weight: 650; color: {INK}; letter-spacing: -.008em; }}
.card-s {{ font-size: 12.5px; color: {MUTED}; margin-top: 2px; margin-bottom: 6px; }}

/* ------------------------------- notes -------------------------------- */
.note {{
  background: #f2f4fd; border-left: 3px solid {ACCENT};
  border-radius: 0 8px 8px 0; padding: 12px 16px; margin: 10px 0 4px;
  font-size: 13.5px; color: {INK_2}; line-height: 1.6;
}}
.note b {{ color: {INK}; }}
.note.warn {{ background: #fff8ea; border-left-color: {STATUS['warning']}; color: #5c4300; }}
.note.warn b {{ color: #3d2d00; }}

/* ------------------------------- filter chips ------------------------- */
.fbar {{
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  background: {SURFACE}; border-radius: 10px; padding: 12px 16px; margin-bottom: 18px;
  box-shadow: 0 1px 3px rgba(20,20,15,.05), 0 5px 16px rgba(20,20,15,.05);
}}
.fbar-l {{ font-size: 11px; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; color: {MUTED}; margin-right: 2px; }}
.chip {{
  display: inline-flex; align-items: center; gap: 7px; background: #eef1fc;
  border: 1px solid #c9d3f5; color: {ACCENT}; border-radius: 20px;
  padding: 4px 12px; font-size: 12.5px; font-weight: 600;
}}
.chip .dim {{ color: {MUTED}; font-weight: 500; text-transform: capitalize; }}
.fbar-none {{ font-size: 13px; color: {MUTED}; }}
.fbar-hint {{ font-size: 12.5px; color: {MUTED}; margin-left: auto; }}

/* ------------------------------- explicit filter pills (Overview) ----- */
/* state.filter_bar_controls() wraps its whole row in st.container(key=
   "page_filter_bar") purely so these rules can target its popover trigger
   buttons without also restyling the chat FAB's popover button, which uses
   the exact same underlying stPopoverButton element elsewhere on the page. */
.st-key-page_filter_bar {{
  background: {SURFACE}; border-radius: 10px; padding: 10px 14px; margin-bottom: 18px;
  box-shadow: 0 1px 3px rgba(20,20,15,.05), 0 5px 16px rgba(20,20,15,.05);
}}
/* st.columns() wraps EVERY cell in the same stVerticalBlockBorderWrapper testid
   the card-shadow rule above targets -- normally invisible, because a cell's
   own content (a chart card, a full-width button) fills it edge to edge and
   exactly coincides with that wrapper's box, so the redundant shadow has
   nowhere visible to show. The scope-note cell here is just short plain text,
   nowhere near as wide as its column, so the "invisible" shadow box was
   exposed as a stray empty pill floating next to it. The row already has its
   own single card shadow (above); its individual cells don't need their own. */
.st-key-page_filter_bar [data-testid="stVerticalBlockBorderWrapper"] {{
  background: transparent !important; box-shadow: none !important; border-radius: 0 !important;
}}
.st-key-page_filter_bar [data-testid="stPopoverButton"] {{
  width: 100%; justify-content: flex-start; gap: 8px;
  border: 1px solid #e2e0d9 !important; border-radius: 8px !important;
  background: {SURFACE} !important; padding: 7px 12px !important;
  font-size: 12.5px !important; font-weight: 600 !important; color: {INK} !important;
  letter-spacing: .02em;
}}
.st-key-page_filter_bar [data-testid="stPopoverButton"]:hover {{
  border-color: {ACCENT} !important;
}}
.st-key-page_filter_bar [data-testid="stPopoverButton"] p {{
  font-size: 12.5px; letter-spacing: .03em;
}}
.st-key-page_filter_bar [data-testid="stMarkdownContainer"] {{ overflow: hidden; text-overflow: ellipsis; }}
.st-key-page_filter_bar .stButton > button {{
  border: none; background: transparent; color: {ACCENT}; font-weight: 600;
  text-decoration: underline; text-underline-offset: 3px; padding: 7px 4px;
  box-shadow: none;
}}
.st-key-page_filter_bar .stButton > button:hover {{ color: {SAMSUNG_BLUE_DARK}; border: none; }}
.filter-scope-note {{
  font-size: 12px; color: {MUTED}; text-align: right; padding: 9px 4px 0 0;
  font-variant-numeric: tabular-nums;
}}

/* ------------------------------- buttons ------------------------------ */
.stButton > button {{
  border-radius: 20px; border: 1px solid #e4e2db; background: {SURFACE};
  color: {INK_2}; font-size: 13px; font-weight: 560; padding: 5px 16px;
}}
.stButton > button:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}

/* ------------------------------- tables ------------------------------- */
[data-testid="stDataFrame"] {{ border: 1px solid #e4e2db; border-radius: 8px; }}

/* charts: kill the plotly modebar, keep the cursor honest */
.modebar {{ display: none !important; }}
.js-plotly-plot .plotly .cursor-pointer {{ cursor: pointer !important; }}

/* ------------------------------- floating chat widget ------------------ */
/* .st-key-chat_fab is the CSS hook st.container(key="chat_fab") gives us --
   it wraps the st.popover trigger, so fixing ITS position is what makes the
   button hover in the corner on every page regardless of scroll or content
   length. The popover panel itself (stPopoverBody) is positioned by Streamlit
   relative to the trigger automatically, so no separate fixed rule is needed
   for it -- only its appearance is styled here.

   Streamlit gives this container its normal block width (spans nearly the
   full row), which for a `position: fixed` box means the browser computes
   `left` from `width` + `right` rather than honouring `right` alone -- the
   button then sits at that computed `left`, near the LEFT edge, even though
   `right: 26px` is correctly applied to the (now very wide) box. Forcing the
   box to shrink-wrap its content removes `left` from the computation, so
   `right` is the only thing left to anchor it. */
.st-key-chat_fab {{
  position: fixed; bottom: 26px; right: 26px; z-index: 9999;
  width: fit-content !important; left: auto !important;
  display: flex; justify-content: flex-end;
}}
.st-key-chat_fab [data-testid="stPopoverButton"] {{
  width: 56px; height: 56px; padding: 0; border-radius: 50%;
  background: {BLACK}; border: none;
  box-shadow: 0 8px 24px rgba(0,0,0,.32), 0 2px 6px rgba(0,0,0,.2);
  display: flex; align-items: center; justify-content: center;
  transition: transform .12s ease, background .12s ease;
}}
.st-key-chat_fab [data-testid="stPopoverButton"]:hover {{
  background: {BLACK_2}; transform: translateY(-2px) scale(1.04);
}}
/* the icon is a font ligature span, not an svg -- style it directly and hide
   only the popover's own auto-appended chevron indicator, which IS an svg */
.st-key-chat_fab [data-testid="stPopoverButton"] [data-testid="stIconMaterial"] {{
  color: #fff !important; font-size: 25px;
}}
.st-key-chat_fab [data-testid="stPopoverButton"] svg {{ display: none; }}
.st-key-chat_fab [data-testid="stPopoverButton"] [data-testid="stMarkdownContainer"] {{
  display: none;  /* the " " label -- icon-only button */
}}
[data-testid="stPopoverBody"] {{
  width: 380px !important; max-width: 92vw; border-radius: 14px !important;
  box-shadow: 0 16px 44px rgba(20,20,15,.2) !important; border: 1px solid #e4e2db !important;
  padding: 14px 16px 12px !important;
}}
.fab-head {{ padding-bottom: 9px; margin-bottom: 8px; border-bottom: 1px solid #e4e2db; }}
.fab-title {{ display: block; font-size: 14.5px; font-weight: 660; color: {INK}; }}
.fab-sub {{ display: block; font-size: 11.5px; color: {MUTED}; margin-top: 2px; }}
</style>
"""

# The active-state prop Streamlit's sidebar nav uses internally (`isActive`) is
# a styled-components prop, filtered out before it reaches the DOM -- there is
# no stable CSS hook (no aria-current, no data-active) to select "the current
# page's link" with plain CSS. This runs in the component iframe (same-origin,
# so window.parent.document is reachable) and tags the matching link with
# .nav-active on load and on every rerender, since Streamlit fully replaces the
# nav DOM on each script rerun.
_ACTIVE_LINK_JS = """
<script>
(function() {
  const doc = window.parent.document;
  function mark() {
    const links = doc.querySelectorAll('[data-testid="stSidebarNavLink"]');
    const here = (window.parent.location.pathname.replace(/\\/$/, '')) || '/';
    links.forEach(a => {
      let path;
      try { path = new URL(a.href).pathname.replace(/\\/$/, '') || '/'; }
      catch (e) { return; }
      a.classList.toggle('nav-active', path === here);
    });
  }
  mark();
  new MutationObserver(mark).observe(doc.body, {childList: true, subtree: true});
})();
</script>
"""


def page_setup(title: str) -> None:
    st.set_page_config(page_title=f"{title} · Samsung MENA Marketing Intelligence",
                       page_icon="📊", layout="wide",
                       initial_sidebar_state="expanded")
    install_template()
    st.markdown(CSS, unsafe_allow_html=True)


def sidebar_active_link_script() -> None:
    components.html(_ACTIVE_LINK_JS, height=0)


def sidebar_brand(meta: str = "MENA · 8 weeks") -> None:
    with st.sidebar, st.container(key="sidebar_brand"):
        st.markdown(
            f'<div class="sb-logo">{logo_svg()}</div>'
            f'<div class="sb-name">Marketing Intelligence</div>'
            f'<div class="sb-meta">{meta}</div>',
            unsafe_allow_html=True,
        )


def head(eyebrow: str, title: str, lede: str) -> None:
    st.markdown(
        f'<div class="eyebrow">{eyebrow}</div><h1 class="page-h1">{title}</h1>'
        f'<p class="lede">{lede}</p>', unsafe_allow_html=True)


def section(label: str) -> None:
    st.markdown(f'<div class="sec">{label}</div>', unsafe_allow_html=True)


def note(text: str, warn: bool = False) -> None:
    st.markdown(f'<div class="note{" warn" if warn else ""}">{text}</div>',
                unsafe_allow_html=True)


def card_head(title: str, sub: str = "") -> None:
    s = f'<div class="card-s">{sub}</div>' if sub else ""
    st.markdown(f'<div class="card-h">{title}</div>{s}', unsafe_allow_html=True)


