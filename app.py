"""SLA Breach Pilot: Streamlit entry point.

    streamlit run app.py
"""

import streamlit as st

st.set_page_config(page_title="SLA Breach Pilot", page_icon="🚨", layout="wide")

pages = [
    st.Page("views/eda.py", title="EDA", url_path="eda", default=True),
    st.Page("views/coming_soon.py", title="Model Journey", url_path="model-journey"),
    st.Page("views/coming_soon.py", title="10 vs 15 Min", url_path="ten-vs-fifteen"),
    st.Page("views/coming_soon.py", title="Tree & Causal", url_path="tree-causal"),
]
st.navigation(pages, position="top").run()
