# SLA Breach Risk: Streamlit dashboard

Interactive dashboard for the SLA-breach capstone. The **EDA** tab is the
descriptive pillar, a Python port of `DescriptivePillar.Rmd`, and is the first
tab of the final dashboard. The other tabs (Model Journey, 10 vs 15 Min,
Tree & Causal) show a "TBD · waiting to be built" page until their pillar is added.

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
app.py                       entry point: page config, logo, top navigation
ui.py                        shared palette, CSS, chart theme, headers, cards
sla_data.py                  cached data loading + derived columns (bins, labels)
views/eda.py                 Tab 1, EDA / descriptive pillar (done)
views/predictive.py          Tab 2, Model Journey (placeholder)
views/sensitivity.py         Tab 3, 10 vs 15 Min (placeholder)
views/causal.py              Tab 4, Tree & Causal (placeholder)
assets/logo.svg              "SLA Breach Risk" title shown top left
data/                        zipped dataset
scripts/make_sample_data.py  synthetic data generator
.streamlit/config.toml       dark theme, 1 GB upload limit
```

## Adding your pillar

Each tab is one file, so pillars can be built in parallel without touching
each other's code. To build one, replace the placeholder in its file:

```python
# views/sensitivity.py
import plotly.graph_objects as go
import streamlit as st

from sla_data import find_data_path, load_alerts
from ui import BLUE, RED, base_layout, card_header, page_header, section_header, takeaway

path = find_data_path()
df = load_alerts(str(path), path.stat().st_mtime)   # cached; shared with the EDA tab

page_header("Sensitivity pillar", "What if the SLA were 10 minutes?",
            "One-sentence summary of the finding.")

section_header(1, "Headline finding", "Caption with the key numbers.")
with st.container(border=True):
    card_header("Chart title", "What the chart shows")
    fig = go.Figure(...)
    st.plotly_chart(base_layout(fig), width="stretch")
takeaway("What the team should do with this.")
```

- **Data:** `load_alerts` returns the cleaned alerts DataFrame with derived
  columns (`month`, `sla_status`, `tags_clean`, workload and ack bins). Every
  tab shares one cached copy. If you need a column it doesn't load yet, add it to
  `KEEP_COLUMNS` in `sla_data.py`.
- **Style:** use `ui.py` so every tab matches. `BLUE` for the normal series,
  `RED` for the highlighted or risky one, `base_layout()` for charts,
  `section_header()` and `takeaway()` for the numbered sections.
- **Dependencies:** add any new packages (e.g. `scikit-learn`, `shap`) to
  `requirements.txt`, or the deployed app will fail to build.
- **Models:** train offline and commit the saved model (e.g. with `joblib`),
  then load it with `@st.cache_resource`. Don't train inside the app on every visit.
- **New tab:** add a file in `views/` and a matching `st.Page(...)` line in `app.py`.
