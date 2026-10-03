# SLA Breach Pilot: Streamlit app

Interactive dashboard for the SLA-breach capstone. The **EDA** tab is the
descriptive pillar, a Python port of `DescriptivePillar.Rmd`. The other tabs
(Model Journey, 10 vs 15 Min, Tree & Causal) are placeholders for the other pillars.

## Run it

```bash
pip install -r requirements.txt
mkdir -p data
cp /path/to/joined_anonymized_engineered.csv data/
streamlit run app.py
```

The app looks for the data in this order:

1. the path in the `SLA_DATA_PATH` environment variable
2. `data/joined_anonymized_engineered.csv`
3. `joined_anonymized_engineered.csv` next to `app.py`
4. `data/sample_alerts.csv` (synthetic, see below)

If none of these exist, the page shows an upload box. `data/` and all `*.csv`
files are git-ignored, so the real data never gets committed.

**No access to the real file?** Generate a fake one with the same columns:

```bash
python scripts/make_sample_data.py        # writes data/sample_alerts.csv
```

The app shows a "synthetic sample data" banner while it's using this file.

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
**Click** a point or bar to open the raw alerts behind it in a table under that
section (newest first, first 100 shown). **Download all N as CSV** exports every
matching alert, not just the preview. Double-click empty chart space to clear
the selection.

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
