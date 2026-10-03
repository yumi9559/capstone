"""EDA / Descriptive pillar: what the alert data actually shows.

Python/Streamlit port of DescriptivePillar.Rmd. Every chart is clickable: a
click filters the table under that section to the raw alerts behind the point
or bar, and the table's full result can be downloaded as CSV.
"""

import re
from functools import partial

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from sla_data import (
    ACK_LABELS,
    DAY_LABELS,
    SLA_MINUTES,
    TEAM_WORKLOAD_LABELS,
    WORKLOAD_LABELS,
    find_data_path,
    load_alerts,
)

BLUE = "#3689E6"
RED = "#EB6668"
GRID = "rgba(255,255,255,0.07)"
MUTED = "#8B949E"
MONO = "JetBrains Mono, SFMono-Regular, Menlo, Consolas, monospace"

PREVIEW_ROWS = 100
DEFAULT_TAGS = ["SNMP", "Network", "Critical", "Application",
                "Server", "Firewall", "Syslog", "Notified"]
EXPORT_COLUMNS = [
    "alert_record_id", "Created At Time", "Priority", "Team", "Tags", "Status",
    "Owner", "Source", "Acknowleged by", "first_ack_seconds", "close_seconds",
    "sla_breach", "created_hour", "created_day_of_week", "alerts_prior_15m",
    "team_alerts_prior_15m",
]

CSS = f"""
<style>
.block-container {{max-width: 1180px; padding-top: 2.5rem;}}
.eyebrow {{font-family: {MONO}; font-size: .75rem; letter-spacing: .08em;
          color: {BLUE}; text-transform: uppercase; margin-bottom: .25rem;}}
.section-num {{font-family: {MONO}; font-size: .75rem; color: {MUTED};
              margin-top: 1.5rem;}}
.kpi-strip {{display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            border: 1px solid rgba(255,255,255,.12); border-radius: 10px;
            background: #16181C; overflow: hidden; margin: 1rem 0 1.5rem;}}
.kpi {{padding: 1rem 1.1rem; border-right: 1px solid rgba(255,255,255,.06);}}
.kpi:last-child {{border-right: none;}}
.kpi-label {{font-family: {MONO}; font-size: .68rem; letter-spacing: .08em;
            color: {MUTED}; text-transform: uppercase;}}
.kpi-value {{font-family: {MONO}; font-size: 1.45rem; font-weight: 600;
            margin-top: .6rem; color: #F0F3F6;}}
.kpi-value.accent {{color: {BLUE};}}
.kpi-sub {{font-family: {MONO}; font-size: .8rem; color: {MUTED};}}
.chart-title {{font-weight: 600; font-size: .95rem; margin-bottom: 0;}}
.chart-sub {{font-size: .8rem; color: {MUTED}; margin-bottom: .25rem;}}
.takeaway {{border-left: 3px solid {BLUE}; padding: .5rem .9rem; margin: .5rem 0 1rem;
           background: rgba(54,137,230,.07); border-radius: 0 6px 6px 0; font-size: .9rem;}}
</style>
"""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def pct(x, digits=1):
    return f"{x:.{digits}%}"


def month_label(ym):
    return pd.Timestamp(ym + "-01").strftime("%b %Y")


def hour_label(h):
    h = int(h)
    return f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"


def rate_table(df, by):
    """Alerts, breaches and breach rate per group (rows with a known SLA outcome)."""
    known = df[df["sla_breach"].notna() & df[by].notna()]
    out = known.groupby(by, observed=True)["sla_breach"].agg(alerts="size", breaches="sum")
    out["breach_rate"] = out["breaches"] / out["alerts"]
    return out.reset_index()


def base_layout(fig, height=300, y_format=".0%", x_title=None, y_title=None):
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=MONO, size=11, color=MUTED),
        showlegend=False,
        hoverlabel=dict(bgcolor="#1F2328", bordercolor="#30363D",
                        font=dict(family=MONO, size=12, color="#F0F3F6")),
        clickmode="event+select",
        dragmode=False,
        bargap=0.25,
    )
    fig.update_xaxes(showgrid=False, title=x_title, fixedrange=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickformat=y_format,
                     title=y_title, rangemode="tozero", fixedrange=True)
    return fig


def card_header(title, subtitle):
    st.markdown(f"<div class='chart-title'>{title}</div>"
                f"<div class='chart-sub'>{subtitle}</div>", unsafe_allow_html=True)


def section_header(num, title, lede):
    st.divider()
    st.markdown(f"<div class='section-num'>{num:02d}</div>", unsafe_allow_html=True)
    st.subheader(title, anchor=False)
    st.markdown(lede)


def takeaway(text):
    # Raw HTML blocks don't render markdown, so convert **bold** / *italic* by hand.
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    html = re.sub(r"\*(.+?)\*", r"<i>\1</i>", html)
    st.markdown(f"<div class='takeaway'><b>Takeaway.</b> {html}</div>",
                unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Click-to-drill-down plumbing
#
# Every trace carries customdata = [column, value, label, ...]. When a point is
# clicked we store that (column, value) for the section, and the section's
# table filters the raw data with df[column] == value.
# --------------------------------------------------------------------------- #
def _on_select(chart_key, section):
    state_key = f"drill_{section}"
    points = st.session_state[chart_key]["selection"]["points"]
    if points:
        column, value, label = points[0]["customdata"][:3]
        st.session_state[state_key] = dict(column=column, value=value,
                                           label=label, source=chart_key)
    elif st.session_state.get(state_key, {}).get("source") == chart_key:
        # Selection on this chart was cleared (double-click on empty space).
        st.session_state.pop(state_key)


def clickable_chart(fig, chart_key, section):
    st.plotly_chart(
        fig,
        key=chart_key,
        on_select=partial(_on_select, chart_key, section),
        selection_mode="points",
        width="stretch",
        config={"displayModeBar": False},
    )


@st.cache_data(show_spinner="Preparing CSV…", max_entries=32)
def _csv_bytes(_df, data_id, column, value):
    sub = _df.loc[_df[column] == value]
    cols = [c for c in EXPORT_COLUMNS if c in sub.columns]
    return sub.sort_values("Created At Time", ascending=False)[cols].to_csv(index=False).encode()


def _style_sla(v):
    return {"BREACHED": f"color: {RED}; font-weight: 600",
            "ON TIME": "color: #3FB950; font-weight: 600"}.get(v, "")


def drilldown(df, data_id, section, hint, default=None):
    """Raw-alert table for whatever was last clicked in this section."""
    sel = st.session_state.get(f"drill_{section}", default)
    if not sel:
        st.caption(f"*{hint}*")
        return

    sub = df.loc[df[sel["column"]] == sel["value"]].sort_values("Created At Time", ascending=False)
    n = len(sub)
    st.markdown(
        f"<div style='display:flex; justify-content:space-between; align-items:baseline;"
        f" flex-wrap:wrap; gap:.5rem; margin:.5rem 0 1.6rem'>"
        f"<b>Alerts from {sel['label']}</b>"
        f"<span style='font-family:{MONO}; font-size:.8rem; color:{MUTED}'>"
        f"{n:,} of {len(df):,} alerts match · showing {min(n, PREVIEW_ROWS):,}</span></div>",
        unsafe_allow_html=True,
    )

    preview = pd.DataFrame({
        "Time": sub["Created At Time"],
        "Pri": sub["Priority"],
        "Team": sub["Team"],
        "Tags": sub["tags_clean"],
        "Ack (min)": sub["first_ack_seconds"] / 60,
        "SLA": sub["sla_status"].astype(str),
    }).head(PREVIEW_ROWS)

    st.dataframe(
        preview.style.map(_style_sla, subset=["SLA"]),
        hide_index=True,
        width="stretch",
        height=320,
        column_config={
            "Time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
            "Ack (min)": st.column_config.NumberColumn(format="%.1f m",
                                                       help="Minutes to first acknowledgement"),
            "Tags": st.column_config.TextColumn(width="large"),
        },
    )
    st.download_button(
        f"Download all {n:,} as CSV",
        data=_csv_bytes(df, data_id, sel["column"], sel["value"]),
        file_name=f"alerts_{sel['column']}_{sel['value']}.csv".replace(" ", "_"),
        mime="text/csv",
        type="primary",
        on_click="ignore",
        key=f"dl_{section}",
    )


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def get_data():
    path = find_data_path()
    if path is not None:
        return load_alerts(str(path), path.stat().st_mtime), path.name

    st.info(
        "Couldn't find `joined_anonymized_engineered.csv`. Put it in the `data/` "
        "folder, set the `SLA_DATA_PATH` environment variable, or upload it below."
    )
    upload = st.file_uploader("Upload joined_anonymized_engineered.csv", type="csv")
    if upload is None:
        st.stop()
    return load_alerts(upload), upload.name


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
st.markdown(CSS, unsafe_allow_html=True)
df, data_name = get_data()
data_id = f"{data_name}:{len(df)}"
df = df[df["Created At Time"].notna()]

if "sample" in data_name:
    st.warning("Showing **synthetic sample data** from `scripts/make_sample_data.py`. "
               "Numbers are random. Add the real CSV to `data/` to see actual findings.")

known = df[df["sla_breach"].notna()]
baseline = known["sla_breach"].mean()
monthly = rate_table(df, "month").sort_values("month")
peak = monthly.loc[monthly["breach_rate"].idxmax()]
low = monthly.loc[monthly["breach_rate"].idxmin()]
first_month, last_month = monthly["month"].iloc[0], monthly["month"].iloc[-1]
n_teams = df["Team"].nunique()

# ---- Header + KPIs --------------------------------------------------------- #
st.markdown(f"<div class='eyebrow'>Descriptive pillar · {data_name}</div>", unsafe_allow_html=True)
st.title("What the alert data actually shows", anchor=False)
st.markdown(
    f"{len(df):,} alerts across {len(monthly)} months ({month_label(first_month)}–"
    f"{month_label(last_month)}), {n_teams} client/internal teams. This is the shape of the "
    "problem before any model."
)

kpis = [
    ("Total alerts", f"{len(df):,}", "", ""),
    ("Overall breach rate", pct(baseline, 2), "accent", f"{int(known['sla_breach'].sum()):,} breaches"),
    ("Client / internal teams", f"{n_teams}", "", ""),
    ("Peak month", pd.Timestamp(peak["month"] + "-01").strftime("%b '%y"), "accent",
     pct(peak["breach_rate"])),
    ("Lowest month", pd.Timestamp(low["month"] + "-01").strftime("%b '%y"), "",
     pct(low["breach_rate"])),
]
st.markdown(
    "<div class='kpi-strip'>" + "".join(
        f"<div class='kpi'><div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value {cls}'>{value}</div><div class='kpi-sub'>{sub}</div></div>"
        for label, value, cls, sub in kpis
    ) + "</div>",
    unsafe_allow_html=True,
)

# ---- 01 Monthly breach rate ------------------------------------------------ #
last = monthly.iloc[-1]
recent_dir = "below" if last["breach_rate"] < baseline else "above"
section_header(
    1, "The breach rate is a moving target",
    f"Monthly breach rate ranges from **{pct(low['breach_rate'])} to {pct(peak['breach_rate'])}** "
    f"(a {peak['breach_rate'] / max(low['breach_rate'], 1e-9):.0f}x swing), peaking in "
    f"**{month_label(peak['month'])}**. The latest month, {month_label(last['month'])}, sits at "
    f"{pct(last['breach_rate'])}, {recent_dir} the {pct(baseline, 2)} overall rate.",
)
with st.container(border=True):
    card_header("Breach rate by month",
                f"{month_label(first_month)}–{month_label(last_month)} · click a point to list that month's alerts")
    fig = go.Figure(go.Scatter(
        x=pd.to_datetime(monthly["month"] + "-01"),
        y=monthly["breach_rate"],
        mode="lines+markers",
        line=dict(color=BLUE, width=2),
        marker=dict(size=8, color=BLUE, line=dict(width=1.5, color="#0E1117")),
        customdata=list(zip(["month"] * len(monthly), monthly["month"],
                            monthly["month"].map(month_label),
                            monthly["breaches"], monthly["alerts"])),
        hovertemplate=("<b>%{customdata[2]}</b><br>Breach rate: %{y:.1%}<br>"
                       "%{customdata[3]:,} breaches of %{customdata[4]:,} alerts"
                       "<extra></extra>"),
    ))
    fig.add_hline(y=baseline, line=dict(color=MUTED, dash="dot", width=1),
                  annotation_text=f"overall {pct(baseline)}", annotation_position="top left",
                  annotation_font=dict(color=MUTED, size=10))
    base_layout(fig, height=320)
    fig.update_xaxes(dtick="M2", tickformat="%y-%m")
    clickable_chart(fig, "chart_month", 1)
    drilldown(df, data_id, 1, "Click a point to see that month's alerts.",
              default=dict(column="month", value=peak["month"],
                           label=f"{peak['month']} (peak month)", source=None))
takeaway(
    "The base rate itself drifts over time. A model trained on one period will meet a different "
    "breach rate in the next, so evaluate on time-ordered splits and keep watching calibration "
    "after deployment, not just accuracy."
)

# ---- 02 Priority ----------------------------------------------------------- #
pri = rate_table(df[df["Priority"].isin(["P1", "P2"])], "Priority")
pri["Priority"] = pri["Priority"].astype(str)
ack = (df[df["Priority"].isin(["P1", "P2"]) & df["first_ack_seconds"].notna()]
       .groupby("Priority", observed=True)["first_ack_seconds"]
       .agg(median="median", p90=lambda s: s.quantile(0.9), alerts="size").reset_index())
ack["Priority"] = ack["Priority"].astype(str)
p = pri.set_index("Priority")
a = ack.set_index("Priority")
pri_colors = [RED if x == "P1" else BLUE for x in pri["Priority"]]

if {"P1", "P2"} <= set(p.index):
    ratio = a.loc["P1", "median"] / max(a.loc["P2", "median"], 1e-9)
    p2_share = p.loc["P2", "breaches"] / p["breaches"].sum()
    section_header(
        2, "Priority is a real, partial signal",
        f"P1 alerts breach at **{pct(p.loc['P1', 'breach_rate'])}** vs P2's "
        f"**{pct(p.loc['P2', 'breach_rate'])}**, and take **{ratio:.1f}x longer** to acknowledge "
        "at the median.",
    )
else:
    p2_share = None
    section_header(2, "Priority is a real, partial signal", "Breach rate and acknowledgement time by priority.")

c1, c2 = st.columns(2)
with c1, st.container(border=True):
    card_header("Breach rate by priority",
                " · ".join(f"{r.Priority}: {r.alerts:,}" for r in pri.itertuples()))
    fig = go.Figure(go.Bar(
        x=pri["Priority"], y=pri["breach_rate"], marker_color=pri_colors, width=0.6,
        customdata=list(zip(["Priority"] * len(pri), pri["Priority"],
                            [f"priority {x}" for x in pri["Priority"]],
                            pri["breaches"], pri["alerts"])),
        hovertemplate=("<b>%{x}</b><br>Breach rate: %{y:.1%}<br>"
                       "%{customdata[3]:,} breaches of %{customdata[4]:,} alerts<extra></extra>"),
    ))
    clickable_chart(base_layout(fig), "chart_priority_rate", 2)
with c2, st.container(border=True):
    card_header("Median time to acknowledge", "Seconds · hover for the 90th percentile")
    fig = go.Figure(go.Bar(
        x=ack["Priority"], y=ack["median"],
        marker_color=[RED if x == "P1" else BLUE for x in ack["Priority"]], width=0.6,
        customdata=list(zip(["Priority"] * len(ack), ack["Priority"],
                            [f"priority {x}" for x in ack["Priority"]],
                            ack["p90"] / 60, ack["alerts"])),
        hovertemplate=("<b>%{x}</b><br>Median: %{y:,.0f}s<br>90th pct: %{customdata[3]:.1f} min"
                       "<br>%{customdata[4]:,} alerts<extra></extra>"),
    ))
    clickable_chart(base_layout(fig, y_format=",.0f", y_title=None).update_yaxes(ticksuffix="s"),
                    "chart_priority_ack", 2)
drilldown(df, data_id, 2, "Click a bar to see example alerts.")
takeaway(
    "Priority separates risk but doesn't decide it. "
    + (f"P2 alerts still account for **{pct(p2_share, 0)} of all breaches** simply because there are "
       "so many of them, so a model that only watches P1 would miss most breaches. "
       if p2_share is not None else "")
    + "Priority belongs in the model as one feature among several."
)

# ---- 03 Hour and day ------------------------------------------------------- #
hourly = rate_table(df, "created_hour").sort_values("created_hour")
hourly["created_hour"] = hourly["created_hour"].astype(int)
daily = rate_table(df, "created_day_of_week").sort_values("created_day_of_week")
daily["created_day_of_week"] = daily["created_day_of_week"].astype(int)
daily["day"] = daily["created_day_of_week"].map(dict(enumerate(DAY_LABELS)))
ph = hourly.loc[hourly["breach_rate"].idxmax()]
pd_ = daily.loc[daily["breach_rate"].idxmax()]
title3 = ("Risk spikes right before the workday starts" if 5 <= ph["created_hour"] <= 8
          else f"Risk spikes at {hour_label(ph['created_hour'])}")
section_header(
    3, title3,
    f"Breach rate peaks at **{hour_label(ph['created_hour'])} ({pct(ph['breach_rate'])})**, "
    f"{ph['breach_rate'] / baseline:.1f}x the overall average. By weekday it is highest on "
    f"**{DAY_LABELS[int(pd_['created_day_of_week'])]} ({pct(pd_['breach_rate'])})**.",
)
c1, c2 = st.columns(2)
with c1, st.container(border=True):
    card_header("By hour of day", "24-hour cycle · red = highest hour")
    fig = go.Figure(go.Bar(
        x=hourly["created_hour"], y=hourly["breach_rate"],
        marker_color=[RED if h == ph["created_hour"] else BLUE for h in hourly["created_hour"]],
        customdata=list(zip(["created_hour"] * len(hourly), hourly["created_hour"],
                            [f"{hour_label(h)} ({h:02d}:00–{h:02d}:59)" for h in hourly["created_hour"]],
                            hourly["breaches"], hourly["alerts"],
                            [hour_label(h) for h in hourly["created_hour"]])),
        hovertemplate=("<b>%{customdata[5]}</b><br>Breach rate: %{y:.1%}<br>"
                       "%{customdata[3]:,} breaches of %{customdata[4]:,} alerts<extra></extra>"),
    ))
    base_layout(fig).update_xaxes(tickmode="linear", dtick=3)
    clickable_chart(fig, "chart_hour", 3)
with c2, st.container(border=True):
    card_header("By day of week", "Monday–Sunday · red = highest day")
    fig = go.Figure(go.Bar(
        x=daily["day"], y=daily["breach_rate"],
        marker_color=[RED if d == pd_["created_day_of_week"] else BLUE
                      for d in daily["created_day_of_week"]],
        customdata=list(zip(["created_day_of_week"] * len(daily), daily["created_day_of_week"],
                            [f"{d}s" for d in daily["day"]],
                            daily["breaches"], daily["alerts"])),
        hovertemplate=("<b>%{x}</b><br>Breach rate: %{y:.1%}<br>"
                       "%{customdata[3]:,} breaches of %{customdata[4]:,} alerts<extra></extra>"),
    ))
    base_layout(fig).update_xaxes(categoryorder="array", categoryarray=DAY_LABELS)
    clickable_chart(fig, "chart_day", 3)
drilldown(df, data_id, 3, "Click a bar to see example alerts.")
takeaway(
    f"Time of arrival carries signal. The {hour_label(ph['created_hour'])} spike points to a "
    "likely coverage gap (shift handover or thin staffing), which would be a staffing fix as "
    "much as a modelling one. Hour and weekday are worth keeping as features."
)

# ---- 04 Clients ------------------------------------------------------------ #
min_alerts = st.session_state.get("min_client_alerts", 5000)
teams = rate_table(df, "Team")
teams["Team"] = teams["Team"].astype(str)
big = teams[teams["alerts"] >= min_alerts].sort_values("breach_rate")
if len(big):
    lo_t, hi_t = big.iloc[0], big.iloc[-1]
    lede4 = (f"Across clients with at least {min_alerts:,} alerts, breach rate ranges from "
             f"**{pct(lo_t['breach_rate'])} ({lo_t['Team']})** to "
             f"**{pct(hi_t['breach_rate'])} ({hi_t['Team']})**. This is the same disparity the "
             "fairness investigation traced to a global risk threshold.")
else:
    lede4 = "No client meets the minimum alert count. Lower it below."
section_header(4, "Client breach rates span a wide range", lede4)
with st.container(border=True):
    card_header(f"Breach rate by client (n ≥ {min_alerts:,} alerts)",
                "Label = breach rate (alert volume) · dotted line = overall rate")
    fig = go.Figure(go.Bar(
        x=big["breach_rate"], y=big["Team"], orientation="h", marker_color=BLUE, width=0.7,
        text=[f"{r:.1%} ({n:,})" for r, n in zip(big["breach_rate"], big["alerts"])],
        textposition="outside", textfont=dict(family=MONO, size=11, color="#C9D1D9"),
        customdata=list(zip(["Team"] * len(big), big["Team"], big["Team"],
                            big["breaches"], big["alerts"], big["breach_rate"] / baseline)),
        hovertemplate=("<b>%{y}</b><br>Breach rate: %{x:.1%} (%{customdata[5]:.2f}x overall)<br>"
                       "%{customdata[3]:,} breaches of %{customdata[4]:,} alerts<extra></extra>"),
    ))
    base_layout(fig, height=max(220, 38 * len(big) + 40))
    fig.update_xaxes(tickformat=".0%", showgrid=True, gridcolor=GRID,
                     range=[0, (big["breach_rate"].max() if len(big) else 0.1) * 1.3])
    fig.update_yaxes(showgrid=False, tickformat=None, autorange="reversed")
    fig.add_vline(x=baseline, line=dict(color=MUTED, dash="dot", width=1))
    clickable_chart(fig, "chart_client", 4)
    st.slider("Minimum alerts per client", 0, 20000, 5000, step=500, key="min_client_alerts",
              help="Small clients have noisy breach rates; raise this to focus on volume clients.")
    drilldown(df, data_id, 4, "Click a bar to see example alerts from that client.")
takeaway(
    "Clients start from very different baselines. A single global threshold will flag "
    "high-baseline clients far more often than low-baseline ones, so client identity (or "
    "per-client calibration) needs to be part of the decision, not an afterthought."
)

# ---- 05 Tags --------------------------------------------------------------- #
tag_cols = sorted(c for c in df.columns if c.startswith("tag_"))
all_tags = [c.removeprefix("tag_") for c in tag_cols]
if all_tags:
    chosen = st.session_state.get("chosen_tags",
                                  [t for t in DEFAULT_TAGS if t in all_tags] or all_tags[:8])
    rows = []
    for t in chosen:
        has = known[known[f"tag_{t}"] == 1]
        if len(has):
            rows.append(dict(tag=t, alerts=len(has), breaches=int(has["sla_breach"].sum()),
                             breach_rate=has["sla_breach"].mean()))
    tags = pd.DataFrame(rows, columns=["tag", "alerts", "breaches", "breach_rate"])
    tags["lift"] = tags["breach_rate"] / baseline
    tags = tags.sort_values("lift")
    if len(tags):
        hi, lo = tags.iloc[-1], tags.iloc[0]
        lede5 = (f"Alerts tagged **{hi['tag']}** breach at **{hi['lift']:.1f}x** the "
                 f"{pct(baseline)} baseline; **{lo['tag']}** alerts at only **{lo['lift']:.1f}x**. "
                 "Tags describe what kind of alert this is, and some kinds are much harder to "
                 "acknowledge in time.")
    else:
        lede5 = "Pick at least one tag below."
    section_header(5, "Some tags flag risk, others signal safety", lede5)
    with st.container(border=True):
        card_header(f"Breach-rate lift by tag, vs. {pct(baseline)} baseline",
                    "Lift = breach rate with the tag ÷ overall rate · below 1.0x = safer, above = riskier")
        fig = go.Figure(go.Bar(
            x=tags["tag"], y=tags["lift"], width=0.7,
            marker_color=[RED if l > 1 else BLUE for l in tags["lift"]],
            customdata=list(zip("tag_" + tags["tag"], [1] * len(tags),
                                [f"tag “{t}”" for t in tags["tag"]],
                                tags["breach_rate"], tags["alerts"], tags["breaches"])),
            hovertemplate=("<b>%{x}</b><br>Lift: %{y:.2f}x<br>Breach rate: %{customdata[3]:.1%}"
                           "<br>%{customdata[5]:,} breaches of %{customdata[4]:,} tagged alerts"
                           "<extra></extra>"),
        ))
        fig.add_hline(y=1, line=dict(color=MUTED, dash="dash", width=1))
        base_layout(fig, height=320, y_format=".1f").update_yaxes(ticksuffix="×")
        clickable_chart(fig, "chart_tags", 5)
        st.multiselect("Tags to compare", all_tags, key="chosen_tags",
                       default=[t for t in DEFAULT_TAGS if t in all_tags] or all_tags[:8])
        drilldown(df, data_id, 5, "Click a bar to see example alerts with that tag.")
    takeaway(
        "Tags are among the most informative descriptive features. Check when each one is "
        "applied, though: a tag like **Notified** may be added *after* an alert has already gone "
        "unacknowledged, which would make it a symptom of a breach (leakage) rather than a "
        "predictor of one."
    )

# ---- 06 Workload ----------------------------------------------------------- #
def workload_chart(column, labels, title, subtitle, key):
    w = rate_table(df[df[column].isin(labels)], column)
    w[column] = pd.Categorical(w[column], labels, ordered=True)
    w = w.sort_values(column)
    w[column] = w[column].astype(str)
    with st.container(border=True):
        card_header(title, subtitle)
        fig = go.Figure(go.Bar(
            x=w[column], y=w["breach_rate"], width=0.75,
            marker_color=[RED if b == labels[-1] else BLUE for b in w[column]],
            customdata=list(zip([column] * len(w), w[column],
                                [f"{b} prior alerts ({title.lower()})" for b in w[column]],
                                w["breaches"], w["alerts"])),
            hovertemplate=("<b>%{x} prior alerts</b><br>Breach rate: %{y:.1%}<br>"
                           "%{customdata[3]:,} breaches of %{customdata[4]:,} alerts<extra></extra>"),
        ))
        base_layout(fig, x_title="Number of prior alerts")
        fig.update_xaxes(categoryorder="array", categoryarray=labels, title_font=dict(size=11))
        clickable_chart(fig, key, 6)
    return w.set_index(column)


if {"workload_bin", "team_workload_bin"} <= set(df.columns):
    w_all = rate_table(df[df["workload_bin"].isin(WORKLOAD_LABELS)], "workload_bin").set_index("workload_bin")
    w_all = w_all.reindex([b for b in WORKLOAD_LABELS if b in w_all.index])
    top_bin = w_all["breach_rate"].idxmax()
    low_bin = w_all["breach_rate"].idxmin()
    middle = w_all["breach_rate"].iloc[1:-1].mean()
    u_shape = w_all["breach_rate"].iloc[0] > middle and w_all["breach_rate"].iloc[-1] > middle
    section_header(
        6, "Workload matters most at the extremes" if u_shape else "Workload's effect on breaches",
        f"Breach rate is highest when **{top_bin}** alerts arrived in the prior 15 minutes "
        f"(**{pct(w_all.loc[top_bin, 'breach_rate'])}**) and lowest at **{low_bin}** "
        f"({pct(w_all.loc[low_bin, 'breach_rate'])}). "
        + ("The pattern is not a straight line: very quiet and very busy queues both run hotter "
           "than moderate ones." if u_shape else
           "Compare both views: overall volume and same-team volume can tell different stories."),
    )
    c1, c2 = st.columns(2)
    with c1:
        workload_chart("workload_bin", WORKLOAD_LABELS, "By recent alert volume",
                       "All alerts in prior 15 min · red = busiest bucket", "chart_workload")
    with c2:
        workload_chart("team_workload_bin", TEAM_WORKLOAD_LABELS, "By team workload",
                       "Same-team alerts in prior 15 min · red = busiest bucket", "chart_team_workload")
    drilldown(df, data_id, 6, "Click a bar to see example alerts.")
    takeaway(
        "Load has a non-linear, U-shaped relationship with breaches. Bursts overwhelm analysts, "
        "but lone alerts in quiet periods (often off-hours) also get missed. Tree-based models "
        "capture this shape far better than a linear term would." if u_shape else
        "Workload is not a simple more-alerts-more-breaches story. Keep it as a binned or "
        "tree-friendly feature rather than assuming a linear effect."
    )

# ---- 07 Time-to-acknowledge distribution ----------------------------------- #
ackd = df[df["ack_bin"].isin(ACK_LABELS)]
counts = ackd["ack_bin"].value_counts().reindex(ACK_LABELS, fill_value=0)
past_sla = [lab for lab, lo_edge in zip(ACK_LABELS, [0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 45])
            if lo_edge >= SLA_MINUTES]
secs = df["first_ack_seconds"].dropna()
within_1 = (secs <= 60).mean()
over_sla = (secs > SLA_MINUTES * 60).mean()
over_60 = int((secs > 3600).sum())
near_miss = counts.get("10–15", 0) / max(len(secs), 1)
section_header(
    7, "Most alerts are acknowledged in minutes; breaches live in the long tail",
    f"**{pct(within_1, 0)}** of alerts are acknowledged within a minute (median "
    f"{secs.median() / 60:.1f} min), while **{pct(over_sla)}** take longer than {SLA_MINUTES} "
    f"minutes. Another **{pct(near_miss)}** land in the 10–15 minute near-miss window.",
)
with st.container(border=True):
    card_header("Time-to-acknowledge distribution",
                f"Capped at 60 min ({over_60:,} slower alerts not shown) · red = past the "
                f"{SLA_MINUTES}-minute mark")
    fig = go.Figure(go.Bar(
        x=ACK_LABELS, y=counts.values, width=0.8,
        marker_color=[RED if lab in past_sla else BLUE for lab in ACK_LABELS],
        customdata=list(zip(["ack_bin"] * len(ACK_LABELS), ACK_LABELS,
                            [f"{lab} min to acknowledge" for lab in ACK_LABELS],
                            counts.values / max(len(secs), 1))),
        hovertemplate=("<b>%{x} min</b><br>%{y:,} alerts<br>%{customdata[3]:.1%} of all "
                       "acknowledged alerts<extra></extra>"),
    ))
    base_layout(fig, height=320, y_format=",.0f", x_title="Time to acknowledge (minutes)")
    fig.update_xaxes(title_font=dict(size=11))
    clickable_chart(fig, "chart_ack", 7)
    drilldown(df, data_id, 7, "Click a bar to see example alerts in that time window.")
takeaway(
    "The target is defined by a thin tail of a heavily skewed distribution, which is why breach "
    "prediction is an imbalanced-class problem. The 10–15 minute near-miss band is where an early "
    "warning has the most room to help (see the *10 vs 15 Min* tab)."
)
