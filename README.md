# SLA Breach Pilot: Streamlit app

Interactive dashboard for the SLA-breach capstone. The **EDA** tab is the
descriptive pillar, a Python port of `DescriptivePillar.Rmd`. The other tabs
(Model Journey, 10 vs 15 Min, Tree & Causal) are placeholders for the other pillars.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

The dataset is committed as `data/joined_anonymized_engineered.zip` (the raw
141 MB CSV is over GitHub's 100 MB file limit; the zip is 13 MB). pandas reads
the zip directly, so there is nothing to unzip. The app looks for data in this
order:

1. the path in the `SLA_DATA_PATH` environment variable
2. `data/joined_anonymized_engineered.csv`
3. `joined_anonymized_engineered.csv` next to `app.py`
4. `data/joined_anonymized_engineered.zip` (the committed copy)
5. `data/sample_alerts.csv` (synthetic, see below)

If none of these exist, the page shows an upload box.

**Synthetic data for testing:** `python scripts/make_sample_data.py` writes a
fake `data/sample_alerts.csv` with the same columns. The app shows a banner
while it's using it.

## Deploy (Streamlit Community Cloud)

1. share.streamlit.io → **Create app** → **Deploy a public app from GitHub**.
2. Repository `yumi9559/capstone`, branch `main` (or the feature branch before
   it's merged), main file `app.py`. Pick a custom subdomain.
3. **Advanced settings** → Python 3.11 or 3.12. Dependencies come from
   `requirements.txt`.
4. **Deploy.** Every push to that branch redeploys the app.

## What's on the EDA tab

KPI strip (total alerts, overall breach rate, teams, peak and lowest month),
then seven sections. Each has a headline, a caption with numbers computed from
the data, the chart(s), and a takeaway.

| # | Section | Chart(s) |
|---|---------|----------|
| 01 | Breach rate over time | Monthly line |
| 02 | Priority | Breach rate by priority · median time to acknowledge (side by side) |
| 03 | Timing | By hour of day · by day of week (side by side) |
| 04 | Clients | Breach rate by client, with a minimum-volume slider |
| 05 | Tags | Breach-rate lift vs. baseline, with a tag picker |
| 06 | Workload | All alerts in prior 15 min · same-team alerts in prior 15 min (side by side) |
| 07 | Time to acknowledge | Distribution, capped at 60 min |

**Interactivity:** hover any point or bar for alerts, breaches and rates.
Every chart is clickable:

- **Breach rate by month (01):** click a month to list *every* alert from that
  month; **Download all N as CSV** exports them. Opens on the peak month.
- **All other charts:** click a bar to preview the 100 most recent example
  alerts behind it (no download).

Double-click empty chart space to clear a selection. Section 04 also has a
minimum-volume slider and section 05 a tag picker.

## Layout

```
app.py                       entry point + top navigation
views/eda.py                 EDA / descriptive pillar
views/coming_soon.py         placeholder for the other pillars
sla_data.py                  cached CSV loading + derived columns (bins, labels)
scripts/make_sample_data.py  synthetic data generator
.streamlit/config.toml       dark theme, 1 GB upload limit
```

To add a pillar, create `views/<name>.py` and point its `st.Page(...)` in
`app.py` at the new file.
