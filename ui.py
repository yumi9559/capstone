"""Shared look and feel for every tab of the SLA Breach Risk dashboard.

Import from here in any pillar page so all tabs share one palette, card style
and chart theme:

    from ui import BLUE, RED, base_layout, card_header, page_header, section_header, takeaway
"""

import re

import streamlit as st

BLUE = "#3689E6"
RED = "#EB6668"
GRID = "rgba(255,255,255,0.07)"
MUTED = "#8B949E"
MONO = "JetBrains Mono, SFMono-Regular, Menlo, Consolas, monospace"

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
.tbd {{border: 1px dashed rgba(255,255,255,.18); border-radius: 10px; padding: 3rem 1.4rem;
       background: #16181C; margin: 2rem 0; text-align: center;}}
.tbd-badge {{display: inline-block; font-family: {MONO}; font-size: .85rem; letter-spacing: .08em;
             color: #E3B341; border: 1px solid rgba(227,179,65,.4); border-radius: 999px;
             padding: .3rem .9rem;}}
</style>
"""



def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def pct(x, digits=1):
    return f"{x:.{digits}%}"


def page_header(eyebrow, title, lede=None):
    st.markdown(f"<div class='eyebrow'>{eyebrow}</div>", unsafe_allow_html=True)
    st.title(title, anchor=False)
    if lede:
        st.markdown(lede)


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
        barcornerradius=4,
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



def coming_soon():
    """Placeholder body for a pillar tab that hasn't been built yet."""
    st.markdown("<div class='tbd'><div class='tbd-badge'>TBD · WAITING TO BE BUILT</div></div>",
                unsafe_allow_html=True)
