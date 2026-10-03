"""Shared data loading for the SLA Breach Pilot Streamlit app.

The CSV is ~229k rows x 161 columns, so we only read the columns the dashboard
uses (plus every tag_* flag) and cache the result for the whole session.
"""

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_FILENAME = "joined_anonymized_engineered.csv"
APP_DIR = Path(__file__).resolve().parent

# Where to look for the data, in order. Set SLA_DATA_PATH to override.
CANDIDATE_PATHS = [
    APP_DIR / "data" / DATA_FILENAME,
    APP_DIR / DATA_FILENAME,
    APP_DIR / "data" / "joined_anonymized_engineered.zip",  # committed copy, used when deployed
    APP_DIR / "data" / "sample_alerts.csv",  # synthetic, from scripts/make_sample_data.py
]

# Columns needed for charts, the drill-down tables and the CSV export.
# Anything missing from the file is simply skipped.
KEEP_COLUMNS = {
    "alert_record_id",
    "Created At Time",
    "Priority",
    "Team",
    "Tags",
    "Status",
    "Owner",
    "Source",
    "Acknowleged by",
    "first_ack_seconds",
    "close_seconds",
    "sla_breach",
    "created_hour",
    "created_day_of_week",
    "alerts_prior_15m",
    "team_alerts_prior_15m",
}

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Same bins as DescriptivePillar.Rmd (left-closed, like cut(..., right = FALSE)).
WORKLOAD_BREAKS = [0, 1, 2, 3, 5, 8, 12, 20, float("inf")]
WORKLOAD_LABELS = ["0", "1", "2", "3–4", "5–7", "8–11", "12–19", "20+"]
TEAM_WORKLOAD_BREAKS = [0, 1, 2, 3, 5, 8, 12, float("inf")]
TEAM_WORKLOAD_LABELS = ["0", "1", "2", "3–4", "5–7", "8–11", "12+"]

# Minutes; right-closed with the lowest edge included, like the Rmd.
ACK_BREAKS = [0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 45, 60]
ACK_LABELS = ["0–1", "1–2", "2–3", "3–5", "5–7", "7–10", "10–15",
              "15–20", "20–30", "30–45", "45–60"]
SLA_MINUTES = 15


def find_data_path():
    env = os.environ.get("SLA_DATA_PATH")
    if env and Path(env).exists():
        return Path(env)
    for path in CANDIDATE_PATHS:
        if path.exists():
            return path
    return None


def _keep(col):
    return col in KEEP_COLUMNS or col.startswith("tag_")


def _clean_tags(raw):
    """'["Server", "Windows"]' -> 'Server, Windows'."""
    if not isinstance(raw, str):
        return ""
    try:
        return ", ".join(json.loads(raw))
    except (ValueError, TypeError):
        return raw.strip("[]").replace('"', "")


def _read_slim(source, chunksize=20_000):
    """Read only the needed columns, in chunks.

    Reading the 141 MB CSV in one go peaks near 1 GB of memory, which is enough
    for Streamlit Community Cloud to kill the app. Chunked reading with
    compact tag columns peaks around 250 MB and gives the same DataFrame.
    """
    columns = [c for c in pd.read_csv(source, nrows=0).columns if _keep(c)]
    if hasattr(source, "seek"):  # uploaded file: rewind after reading the header
        source.seek(0)
    parts = []
    for chunk in pd.read_csv(source, usecols=columns, chunksize=chunksize):
        tag_cols = [c for c in chunk.columns if c.startswith("tag_")]
        chunk[tag_cols] = chunk[tag_cols].fillna(0).astype("int8")
        parts.append(chunk)
    return pd.concat(parts, ignore_index=True)


# cache_resource keeps ONE shared copy for all visitors (cache_data would hand
# every rerun its own ~60 MB copy). Pages must treat the result as read-only.
@st.cache_resource(show_spinner="Loading alert data…", max_entries=1)
def load_alerts(source, modified=None):
    """Read the CSV or zipped CSV (path or uploaded file) and add the derived columns.

    `modified` is the file's mtime; it is only part of the cache key, so the
    cache refreshes when the CSV on disk is replaced.
    """
    df = _read_slim(source)

    df["Created At Time"] = pd.to_datetime(df["Created At Time"], errors="coerce")
    df = df[df["Created At Time"].notna()].reset_index(drop=True)
    df["month"] = df["Created At Time"].dt.strftime("%Y-%m")

    if "created_hour" not in df:
        df["created_hour"] = df["Created At Time"].dt.hour
    if "created_day_of_week" not in df:
        df["created_day_of_week"] = df["Created At Time"].dt.dayofweek  # 0 = Monday
    df["day_name"] = df["created_day_of_week"].map(dict(enumerate(DAY_LABELS)))

    df["sla_status"] = df["sla_breach"].map({0: "ON TIME", 1: "BREACHED"}).fillna("Unknown")
    df["tags_clean"] = df["Tags"].map(_clean_tags) if "Tags" in df else ""

    if "alerts_prior_15m" in df:
        df["workload_bin"] = pd.cut(df["alerts_prior_15m"], WORKLOAD_BREAKS,
                                    labels=WORKLOAD_LABELS, right=False).astype(str)
    if "team_alerts_prior_15m" in df:
        df["team_workload_bin"] = pd.cut(df["team_alerts_prior_15m"], TEAM_WORKLOAD_BREAKS,
                                         labels=TEAM_WORKLOAD_LABELS, right=False).astype(str)

    ack_min = df["first_ack_seconds"] / 60
    df["ack_bin"] = pd.cut(ack_min.where(ack_min.between(0, 60)), ACK_BREAKS,
                           labels=ACK_LABELS, right=True, include_lowest=True).astype(str)

    tag_cols = [c for c in df.columns if c.startswith("tag_")]
    df[tag_cols] = df[tag_cols].fillna(0).astype("int8")
    for col in ["Priority", "Team", "Status", "Source", "sla_status", "day_name"]:
        if col in df:
            df[col] = df[col].astype("category")
    return df
