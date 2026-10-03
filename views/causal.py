"""Causal pillar (Tree & Causal tab): placeholder until it is built.

Replace the body of this file with the tree and causal analysis. Load the data
with `sla_data.load_alerts` and style it with the helpers in `ui.py`.
"""

from ui import coming_soon

coming_soon(
    pillar="Causal",
    title="Tree & Causal",
    question="Which factors actually drive breaches, beyond what merely correlates with them?",
    planned=[
        "Decision-tree view of the main breach pathways",
        "Causal estimates for levers the team controls (staffing at peak hours, workload)",
        "Checks for confounding, e.g. client mix vs. time of day",
        "Fairness view: how one global risk threshold affects different clients",
    ],
    file_name="causal.py",
)
