"""SLA Breach Risk dashboard: Streamlit entry point.

    streamlit run app.py

Each tab is one pillar of the capstone and lives in its own file under views/.
To build out a pillar, replace the placeholder in its file; the navigation
below doesn't need to change.
"""

from pathlib import Path

import streamlit as st

from ui import inject_css

APP_DIR = Path(__file__).resolve().parent

st.set_page_config(page_title="SLA Breach Risk", page_icon="🚨", layout="wide")
st.logo(str(APP_DIR / "assets" / "logo.svg"), size="large")
inject_css()

pages = [
    st.Page("views/eda.py", title="EDA", url_path="eda", default=True),
    st.Page("views/predictive.py", title="Model Journey", url_path="model-journey"),
    st.Page("views/sensitivity.py", title="10 vs 15 Min", url_path="ten-vs-fifteen"),
    st.Page("views/causal.py", title="Tree & Causal", url_path="tree-causal"),
]
st.navigation(pages, position="top").run()
