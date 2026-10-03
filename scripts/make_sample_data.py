"""Generate a synthetic stand-in for joined_anonymized_engineered.csv.

The real file is too large (and too sensitive) to commit. This script writes a
small fake dataset with the same column names the dashboard uses, so anyone can
run the Streamlit app end to end without the real data.

    python scripts/make_sample_data.py            # 60,000 rows -> data/sample_alerts.csv
    python scripts/make_sample_data.py --rows 228881 --out data/joined_anonymized_engineered.csv

The numbers it produces are random; never quote them as findings.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

TAGS = [
    "SNMP", "Network", "Critical", "Application", "Server", "Firewall",
    "Syslog", "Notified", "Windows", "SMTP", "Camera", "SOC",
]
TEAMS = [f"Client_{i:03d}" for i in range(1, 19)] + ["Internal_Team_001"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=60_000)
    parser.add_argument("--out", default="data/sample_alerts.csv")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    n = args.rows

    start = pd.Timestamp("2025-01-01")
    span = (pd.Timestamp("2026-08-31 23:59:59") - start).total_seconds()
    created = start + pd.to_timedelta(rng.uniform(0, span, n), unit="s")

    team_weights = rng.dirichlet(np.full(len(TEAMS), 0.6))
    team = rng.choice(TEAMS, n, p=team_weights)
    team_risk = dict(zip(TEAMS, rng.uniform(0.3, 1.8, len(TEAMS))))

    priority = np.where(rng.random(n) < 0.086, "P1", "P2")
    hour = created.hour.to_numpy()
    dow = created.dayofweek.to_numpy()  # 0 = Monday

    tag_flags = {t: rng.random(n) < p for t, p in zip(TAGS, rng.uniform(0.05, 0.35, len(TAGS)))}
    tag_risk = dict(zip(TAGS, [0.5, 0.6, 1.0, 1.1, 1.15, 1.35, 1.8, 3.0, 1.0, 1.0, 0.9, 1.0]))

    risk = np.full(n, 0.08)
    risk *= np.vectorize(team_risk.get)(team)
    risk *= np.where(priority == "P1", 2.1, 1.0)
    risk *= np.where(hour == 7, 2.2, 1.0)
    risk *= 1 + 0.4 * np.sin((created.month.to_numpy() / 12) * 2 * np.pi)
    for t in TAGS:
        risk *= np.where(tag_flags[t], tag_risk[t] ** 0.5, 1.0)
    breach = rng.random(n) < np.clip(risk, 0, 0.9)

    ack_ok = np.where(rng.random(n) < 0.55, rng.uniform(0, 60, n), rng.exponential(200, n))
    ack_ok = np.clip(ack_ok, 0, 899)
    ack_bad = 900 + rng.exponential(900, n)
    ack = np.where(breach, ack_bad, ack_ok).round()
    ack[rng.random(n) < 0.01] = np.nan

    tags_json = [
        json.dumps([t for t in TAGS if tag_flags[t][i]] or ["Network"]) for i in range(n)
    ]

    df = pd.DataFrame({
        "alert_record_id": np.arange(1, n + 1),
        "Priority": priority,
        "Tags": tags_json,
        "Created At Time": created.strftime("%Y-%m-%d %H:%M:%S"),
        "Status": rng.choice(["Closed", "Resolved"], n),
        "Owner": rng.choice([f"Analyst_{i:03d}" for i in range(1, 40)], n),
        "Source": rng.choice(["Email", "API", "Integration"], n),
        "Team": team,
        "first_ack_seconds": ack,
        "close_seconds": (ack + rng.exponential(3600, n)).round(),
        "sla_breach": np.where(np.isnan(ack), np.nan, breach.astype(float)),
        "created_hour": hour,
        "created_day_of_week": dow,
        "alerts_prior_15m": rng.poisson(rng.choice([1, 4, 15], n)),
        "team_alerts_prior_15m": rng.poisson(rng.choice([0.5, 3, 10], n)),
    })
    for t in TAGS:
        df[f"tag_{t}"] = tag_flags[t].astype(int)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.sort_values("Created At Time").to_csv(out, index=False)
    print(f"Wrote {len(df):,} rows x {df.shape[1]} columns to {out}")


if __name__ == "__main__":
    main()
