"""Predictive pillar (Model Journey tab): placeholder until it is built.

Replace the body of this file with the predictive work. Load the data with
`sla_data.load_alerts` and style it with the helpers in `ui.py` so it matches
the EDA tab.
"""

from ui import coming_soon

coming_soon(
    pillar="Predictive",
    title="Model Journey",
    question="Can we flag which alerts are likely to breach the SLA before they do?",
    planned=[
        "Baseline vs. candidate models (e.g. logistic regression, tree ensembles)",
        "Time-ordered train/test split, since the breach rate drifts month to month",
        "Precision/recall at the chosen risk threshold and per-client performance",
        "Feature importance for the signals surfaced in EDA (priority, hour, tags, workload)",
    ],
    file_name="predictive.py",
)
