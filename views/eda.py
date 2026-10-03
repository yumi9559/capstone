"""EDA / Descriptive pillar: what the alert data actually shows.

Python/Streamlit port of DescriptivePillar.Rmd. Every chart is clickable.
Clicking a month on the first chart lists every alert from that month, with a
CSV download; clicking a bar on any other chart shows example alerts behind it.
"""

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
from ui import (
    BLUE, GRID, MONO, MUTED, RED,
    base_layout, card_header, page_header, pct, section_header, takeaway,
)

EXAMPLE_ROWS = 100
DEFAULT_TAGS = ["SNMP", "Network", "Critical", "Application",
                "Server", "Firewall", "Syslog", "Notified"]
EXPORT_COLUMNS = [
    "alert_record_id", "Created At Time", "Priority", "Team", "Tags", "Status",
    "Owner", "Source", "Acknowleged by", "first_ack_seconds", "close_seconds",
    "sla_breach", "created_hour", "created_day_of_week", "alerts_prior_15m",
    "team_alerts_prior_15m",
]

# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def month_label(ym):
    return pd.Timestamp(ym + "-01").strftime("%b %Y")


def hour_label(h):
    h = int(h)
    return f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"


def rate_table(df, by):
    """Alerts, breaches and breach rate per group, matching the Rmd.

    alerts counts every alert, like n() in R. breach_rate is mean(sla_breach == 1,
    na.rm = TRUE): the 32 alerts with no recorded SLA outcome count toward volume
    but not toward the rate.
    """
    out = (df[df[by].notna()].groupby(by, observed=True)["sla_breach"]
           .agg(alerts="size", breaches="sum", breach_rate="mean"))
    out["breaches"] = out["breaches"].astype(int)
    return out.reset_index()


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


def drilldown(df, data_id, section, hint, default=None, full=False):
    """Raw alerts for whatever was last clicked in this section.

    full=True lists every matching alert and adds a CSV download (monthly chart);
    otherwise it shows the EXAMPLE_ROWS most recent matches as examples.
    """
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
        + (f"{n:,} of {len(df):,} alerts · scroll to see all" if full else
           f"{n:,} of {len(df):,} alerts match · showing {min(n, EXAMPLE_ROWS):,} most recent")
        + "</span></div>",
        unsafe_allow_html=True,
    )

    preview = pd.DataFrame({
        "Time": sub["Created At Time"],
        "Pri": sub["Priority"],
        "Team": sub["Team"],
        "Tags": sub["tags_clean"],
        "Ack (min)": sub["first_ack_seconds"] / 60,
        "SLA": sub["sla_status"].astype(str),
    })
    if not full:
        preview = preview.head(EXAMPLE_ROWS)

    st.dataframe(
        preview.style.map(_style_sla, subset=["SLA"]),
        hide_index=True,
        width="stretch",
        height=320,
        column_config={
            "Time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
            "Ack (min)": st.column_config.NumberColumn(format="%.1f m",
                                                       help="Minutes to first acknowledgement"),
            "Team": st.column_config.TextColumn(width="medium"),
            "Tags": st.column_config.TextColumn(width="large"),
        },
    )
    if not full:
        return
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
page_header(
    "Descriptive pillar",
    "What the alert data actually shows",
    f"{len(df):,} alerts across {len(monthly)} months ({month_label(first_month)}–"
    f"{month_label(last_month)}), {n_teams} client/internal teams. This is the shape of the "
    "problem before any model.",
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
recent = monthly["breach_rate"].tail(3)
falling_since_peak = peak["month"] < monthly["month"].iloc[-3] and (recent < baseline).all()
section_header(
    1, "The breach rate is a moving target",
    f"Monthly breach rate ranges from **{pct(low['breach_rate'])} to {pct(peak['breach_rate'])}**, "
    f"a {peak['breach_rate'] / max(low['breach_rate'], 1e-9):.0f}x swing, peaking in "
    f"**{pd.Timestamp(peak['month'] + '-01'):%B %Y}**"
    + (", then dropping sharply through the most recent months "
       f"({month_label(last['month'])}: {pct(last['breach_rate'])})." if falling_since_peak else
       f". The latest month, {month_label(last['month'])}, sits at {pct(last['breach_rate'])}."),
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
                           label=f"{peak['month']} (peak month)", source=None), full=True)
recent6, earlier = monthly.tail(6), monthly.iloc[:-6]
recent_rate = recent6["breaches"].sum() / df[df["month"].isin(recent6["month"]) & df["sla_breach"].notna()].shape[0]
earlier_rate = earlier["breaches"].sum() / df[df["month"].isin(earlier["month"]) & df["sla_breach"].notna()].shape[0]
takeaway(
    f"The breach rate is not stable over time. The last six months "
    f"({month_label(recent6['month'].iloc[0])}–{month_label(recent6['month'].iloc[-1])}) breached "
    f"at **{pct(recent_rate)}**, versus **{pct(earlier_rate)}** across the "
    f"{len(earlier)} months before. Any figure quoted for the whole period mixes these regimes."
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
        f"**{pct(p.loc['P2', 'breach_rate'])}**, taking **{ratio:.1f}x longer** to acknowledge "
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
if p2_share is not None:
    takeaway(
        f"P1 alerts breach about **{p.loc['P1', 'breach_rate'] / p.loc['P2', 'breach_rate']:.1f}x** as "
        f"often as P2, yet P2 alerts make up **{pct(p2_share, 0)} of all breaches** because they are "
        f"{p.loc['P2', 'alerts'] / p.loc['P1', 'alerts']:.0f}x more numerous. Priority separates risk, "
        "but most breaches come from the lower-priority queue."
    )

# ---- 03 Hour and day ------------------------------------------------------- #
hourly = rate_table(df, "created_hour").sort_values("created_hour")
hourly["created_hour"] = hourly["created_hour"].astype(int)
daily = rate_table(df, "created_day_of_week").sort_values("created_day_of_week")
daily["created_day_of_week"] = daily["created_day_of_week"].astype(int)
daily["day"] = daily["created_day_of_week"].map(dict(enumerate(DAY_LABELS)))
ph = hourly.loc[hourly["breach_rate"].idxmax()]
pd_ = daily.loc[daily["breach_rate"].idxmax()]
title3 = f"Breach risk spikes at {hour_label(ph['created_hour'])}"
section_header(
    3, title3,
    f"Breach rate peaks at **{hour_label(ph['created_hour'])} ({pct(ph['breach_rate'])})**, "
    + ("more than double the daily average" if ph["breach_rate"] >= 2 * baseline
       else f"{ph['breach_rate'] / baseline:.1f}x the daily average")
    + f", and is highest on **{pd.Timestamp('2024-01-01') + pd.Timedelta(days=int(pd_['created_day_of_week'])):%A} "
    f"({pct(pd_['breach_rate'])})** across the week, against a low of "
    f"{pct(daily['breach_rate'].min())} on {daily.loc[daily['breach_rate'].idxmin(), 'day']}.",
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
second = hourly.drop(hourly["breach_rate"].idxmax()).sort_values("breach_rate").iloc[-1]
takeaway(
    f"The {hour_label(ph['created_hour'])} hour stands alone: the next-highest hour, "
    f"{hour_label(second['created_hour'])}, is at {pct(second['breach_rate'])}. Day-of-week "
    f"differences are much smaller ({pct(daily['breach_rate'].min())} to "
    f"{pct(daily['breach_rate'].max())}), so time of day varies more than day of week."
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
             f"**{pct(hi_t['breach_rate'])} ({hi_t['Team']})**, with "
             f"{int((big['breach_rate'] > baseline).sum())} of {len(big)} above the "
             f"{pct(baseline)} overall rate.")
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
if len(big) >= 2:
    largest = big.loc[big["alerts"].idxmax()]
    takeaway(
        f"{hi_t['Team']} breaches **{hi_t['breach_rate'] / max(lo_t['breach_rate'], 1e-9):.0f}x** as "
        f"often as {lo_t['Team']}. The largest client, {largest['Team']} "
        f"({int(largest['alerts']):,} alerts), sits at {pct(largest['breach_rate'])}, so the overall "
        "rate hides very different experiences from one client to the next."
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
        common = tags.loc[tags["alerts"].idxmax()]
        cover = lambda r: pct(r["alerts"] / len(known), 0)
        lede5 = (f"**tag_{common['tag']}** covers {cover(common)} of alerts and moves risk to "
                 f"**{common['lift']:.2f}x** baseline"
                 + (f"; **tag_{hi['tag']}** is rare ({cover(hi)} of alerts) but carries "
                    f"**{hi['lift']:.1f}x** the risk." if hi["tag"] != common["tag"] else ".")
                 + f" (Baseline = {pct(baseline)} overall breach rate.)")
        title5 = ("One tag dominates — and it points the right way"
                  if common["lift"] < 1 and common["alerts"] / len(known) >= 0.25
                  else "Tags carry real risk signal")
    else:
        lede5, title5 = "Pick at least one tag below.", "Tags carry real risk signal"
    section_header(5, title5, lede5)
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
        drilldown(df, data_id, 5, "Click a bar to see example alerts carrying that tag.")
    if len(tags):
        above = tags[tags["lift"] > 1].sort_values("lift", ascending=False)
        below = tags[tags["lift"] < 1].sort_values("lift")
        fmt = lambda d: " and ".join(f"{r.tag} ({r.lift:.2f}x)" for r in d.head(2).itertuples())
        takeaway(
            f"{len(above)} of the {len(tags)} tags shown are above baseline. "
            + (f"The strongest risk markers are {fmt(above)}" if len(above) else "")
            + ("; " if len(above) and len(below) else "")
            + (f"the tags most associated with on-time handling are {fmt(below)}" if len(below) else "")
            + ". These are associations, not causes."
        )

# ---- 06 Workload ----------------------------------------------------------- #
def workload_chart(column, labels, title, subtitle, key, scope):
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
                                [f"{b} prior {scope} alerts in 15 min" for b in w[column]],
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
    others = w_all["breach_rate"].drop(top_bin)
    w_team = rate_table(df[df["team_workload_bin"].isin(TEAM_WORKLOAD_LABELS)], "team_workload_bin")
    w_team = w_team.set_index("team_workload_bin").reindex(
        [b for b in TEAM_WORKLOAD_LABELS if b in set(w_team["team_workload_bin"])])
    t_top = w_team["breach_rate"].idxmax()
    t_mid = w_team["breach_rate"].iloc[1:-1].mean()
    t_u = w_team["breach_rate"].iloc[0] > t_mid and w_team["breach_rate"].iloc[-1] > t_mid
    top_is_last = top_bin == WORKLOAD_LABELS[-1]
    section_header(
        6, "Breach rate is U-shaped in workload" if (u_shape and t_u)
        else "Breach rate is highest at the busiest moments" if (top_is_last and w_team.index[-1] == t_top)
        else "Workload and breach rate don't move in a straight line",
        f"Across all sources, breach rate is highest when **{top_bin}** alerts arrived in the prior "
        f"15 minutes (**{pct(w_all.loc[top_bin, 'breach_rate'])}**, vs {pct(others.min())}–"
        f"{pct(others.max())} for every other bucket). For same-team workload the highest bucket is "
        f"**{t_top}** ({pct(w_team.loc[t_top, 'breach_rate'])}), with "
        f"{TEAM_WORKLOAD_LABELS[-1]} at {pct(w_team['breach_rate'].iloc[-1])}.",
    )
    c1, c2 = st.columns(2)
    with c1:
        workload_chart("workload_bin", WORKLOAD_LABELS, "vs. alerts in prior 15 min (all sources)",
                       "Binned · red = busiest bucket", "chart_workload", "(all sources)")
    with c2:
        workload_chart("team_workload_bin", TEAM_WORKLOAD_LABELS, "vs. same-team alerts in prior 15 min",
                       "Binned · red = busiest bucket", "chart_team_workload", "same-team")
    drilldown(df, data_id, 6, "Click a bar to see example alerts.")
    shape = [name for name, flag in [("all-source", u_shape), ("same-team", t_u)] if flag]
    takeaway(
        "Having more recent alerts does not steadily mean more breaches. "
        + (f"In the {' and '.join(shape)} view{'s' if len(shape) > 1 else ''}, both the quietest "
           "(0 prior alerts) and the busiest bucket breach more often than the middle buckets, "
           "a U-shape rather than a straight line." if shape else
           "The middle buckets move up and down without a consistent trend.")
    )

# ---- 07 Time-to-acknowledge distribution ----------------------------------- #
ackd = df[df["ack_bin"].isin(ACK_LABELS)]
counts = ackd["ack_bin"].value_counts().reindex(ACK_LABELS, fill_value=0)
past_sla = [lab for lab, lo_edge in zip(ACK_LABELS, [0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 45])
            if lo_edge >= SLA_MINUTES]
secs = df["first_ack_seconds"].dropna()
within_3 = (secs <= 180).mean()
over_sla = (secs > SLA_MINUTES * 60).mean()
over_60 = int((secs > 3600).sum())
near_miss = counts.get("10–15", 0) / max(len(secs), 1)
# Does sla_breach exactly equal "acknowledged after 15 minutes"?
both = df[df["sla_breach"].notna() & df["first_ack_seconds"].notna()]
agree = ((both["first_ack_seconds"] > SLA_MINUTES * 60) == (both["sla_breach"] == 1)).mean()
clean_cut = agree == 1
section_header(
    7, "The target is a clean threshold cut" if clean_cut else "Breaches live in the long tail",
    f"**{pct(within_3, 0)}** of alerts are handled within 3 minutes (median "
    f"{secs.median():.0f}s); **{pct(over_sla)}** take longer than {SLA_MINUTES} minutes. "
    + (f"Breach status is a hard cut at {SLA_MINUTES} minutes with no boundary artifacts: every "
       f"breach was acknowledged after {SLA_MINUTES} min and every on-time alert before."
       if clean_cut else
       f"Breach status matches the {SLA_MINUTES}-minute cut for {pct(agree)} of alerts."),
)
with st.container(border=True):
    card_header("Time-to-acknowledge distribution",
                f"Capped at 60 min ({over_60:,} slower alerts not shown) · red = past SLA")
    fig = go.Figure(go.Bar(
        x=ACK_LABELS, y=counts.values, width=0.8,
        marker_color=[RED if lab in past_sla else BLUE for lab in ACK_LABELS],
        customdata=list(zip(["ack_bin"] * len(ACK_LABELS), ACK_LABELS,
                            [f"{lab} min to acknowledge" for lab in ACK_LABELS],
                            counts.values / max(len(secs), 1))),
        hovertemplate=("<b>%{x} min</b><br>%{y:,} alerts<br>%{customdata[3]:.1%} of all "
                       "acknowledged alerts<extra></extra>"),
    ))
    base_layout(fig, height=320, y_format="~s", x_title="Time to acknowledge (minutes)")
    fig.update_xaxes(title_font=dict(size=11))
    clickable_chart(fig, "chart_ack", 7)
    drilldown(df, data_id, 7, "Click a bar to see example alerts.")
takeaway(
    (f"<code>sla_breach</code> is exactly \"acknowledged after {SLA_MINUTES} minutes\", so the target is "
     "fully determined by time to acknowledge. " if clean_cut else "")
    + f"Breaches are a small minority ({pct(over_sla)} of alerts) in a heavily right-skewed "
    f"distribution, and another {pct(near_miss)} of alerts land just under the line, in the "
    "10–15 minute band."
)
