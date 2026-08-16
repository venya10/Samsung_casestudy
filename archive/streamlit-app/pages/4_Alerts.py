"""Alerts — the Early Warning Marketing System."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme as T
from data_access import load

T.page_setup("Alerts", "🚨")
st.title("Early Warning System")

alerts = load("alerts")
current = load("alerts_current")

markets = st.multiselect("Markets", sorted(alerts["market"].dropna().unique()),
                         default=sorted(alerts["market"].dropna().unique()),
                         key="alert_market")
if markets:
    alerts = alerts[alerts["market"].isin(markets)]
    current = current[current["market"].isin(markets)]

counts = current["severity"].value_counts().to_dict()
T.kpi_tiles([
    {"label": "Open now", "value": f"{len(current)}"},
    {"label": "Critical", "value": f"{counts.get('critical', 0)}"},
    {"label": "High", "value": f"{counts.get('high', 0)}"},
    {"label": "Medium", "value": f"{counts.get('medium', 0)}"},
    {"label": "Fired all year", "value": f"{len(alerts)}",
     "sub": "back-tested across 52 weeks"},
])

# --------------------------------------------------------------------------
# Open alerts
# --------------------------------------------------------------------------
st.markdown("## Open alerts")

if current.empty:
    st.success("No alerts open. Every monitored metric is inside its expected range.")
else:
    for _, r in current.sort_values("severity_rank").iterrows():
        color = T.SEVERITY_COLOR.get(r["severity"], T.MUTED)
        glyph = T.SEVERITY_GLYPH.get(r["severity"], "•")
        when = "roster-level" if pd.isna(r["week"]) else f"w/c {pd.Timestamp(r['week']).date()}"
        st.markdown(
            f'<div class="alert-card" style="border-left-color:{color}">'
            f'<div class="alert-meta" style="color:{color}">'
            f'{glyph} {r["severity"]} · {r["category"]} · {r["rule_id"]}</div>'
            f'<div class="alert-head">{r["rule"]}</div>'
            f'<div class="alert-body"><b>{r["entity"]}</b> · {when}<br>'
            f'{r["detail"]}<br><br>'
            f'<b>Owner:</b> {r["owner"]}<br>'
            f'<b>Recommended action:</b> {r["action"]}</div></div>',
            unsafe_allow_html=True,
        )

T.note(
    "Severity is shown by a glyph and the word as well as the colour, so the "
    "priority is readable without relying on colour vision. Every alert carries an "
    "owner and a next step — an alert nobody owns is noise, and an alert without an "
    "action is just a number going red."
)

# --------------------------------------------------------------------------
# Back-test
# --------------------------------------------------------------------------
st.markdown("## What the system would have caught")

dated = alerts[alerts["week"].notna()].copy()
if not dated.empty:
    hist = (
        dated.groupby([pd.Grouper(key="week", freq="W-MON"), "severity"])
        .size().reset_index(name="n")
    )
    fig = go.Figure()
    for sev in ["critical", "high", "medium"]:
        sub = hist[hist["severity"] == sev]
        if sub.empty:
            continue
        fig.add_trace(go.Bar(
            x=sub["week"], y=sub["n"], name=sev.title(),
            marker=dict(color=T.SEVERITY_COLOR[sev],
                        line=dict(color=T.SURFACE, width=2)),
            hovertemplate=f"%{{x|%d %b %Y}}<br>{sev.title()} %{{y}}<extra></extra>",
        ))
    fig.update_layout(title="Alerts fired per week, by severity", barmode="stack",
                      bargap=0.25)
    T.chart(fig, height=360, table=hist)

    T.note(
        "Running the rules over the full 52 weeks is a back-test, not decoration: it "
        "shows whether the thresholds would have fired at the right moments or "
        "buried the team in noise. The clusters line up with the events that "
        "actually mattered — the post-launch sentiment collapse, the cost-per-click "
        "climb, and the Egypt divergence."
    )

# --------------------------------------------------------------------------
# Rule catalogue
# --------------------------------------------------------------------------
st.markdown("## Rule catalogue")

cat = (
    alerts.groupby(["rule_id", "rule", "category", "severity", "owner"], as_index=False)
    .size().rename(columns={"size": "times_fired"})
    .sort_values(["severity", "times_fired"], ascending=[True, False])
)
st.dataframe(cat, use_container_width=True, hide_index=True)

st.markdown("## How it would run in production")
st.markdown(
    """
| Layer | Design |
|---|---|
| **Sources** | The same eight weekly feeds. Paid media and site analytics land via API; TV GRPs, PR share of voice and brand tracking arrive as agency files. |
| **Schedule** | Pipeline runs every Monday 06:00 GST, after the weekend's data settles. `generate → model → insights → alerts` is one command and is idempotent. |
| **Detection** | Rules in `config/rules.yaml`. Thresholds are relative to each market's own trailing 8 weeks, so one rule set works across UAE, KSA and Egypt without per-market tuning. Robust z-scores (median/MAD) mean a White Friday spike does not desensitise the detector for the weeks after it. |
| **Routing** | Critical → Slack channel plus email to the Marketing Director, same day. High → owner's Slack DM, 24h SLA. Medium → weekly digest. |
| **Suppression** | An alert that fired last week and has not changed severity is folded into the digest rather than re-sent, so a slow-moving problem does not generate a daily nag. |
| **Feedback** | Each alert can be marked acted-on / false positive. False-positive rate per rule is reviewed monthly, and thresholds tuned against it — a rule that cries wolf gets retired. |
| **Escalation** | Any critical alert unacknowledged after 48h escalates to the regional lead. |
"""
)

T.note(
    "The part most early-warning systems get wrong is the last three rows. "
    "Detection is the easy half; suppression, a false-positive review loop, and a "
    "named owner per rule are what stop the alerts being ignored within a month."
)
