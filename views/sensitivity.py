"""Sensitivity pillar (10 vs 15 Min tab): placeholder until it is built.

Replace the body of this file with the sensitivity analysis. `sla_data.SLA_MINUTES`
holds the current 15-minute definition; the dataset also has `ack_within_10m`
and `near_breach_10_to_15m` columns for the 10-minute comparison.
"""

from ui import coming_soon

coming_soon(
    pillar="Sensitivity",
    title="10 vs 15 Min",
    question="What changes if a breach is defined as no acknowledgement within 10 minutes instead of 15?",
    planned=[
        "Breach rate under a 10-minute vs. 15-minute definition, overall and by month",
        "Which priorities, clients and hours are most affected by the stricter cut",
        "How the predictive model's performance shifts with the new target",
        "The 10–15 minute near-miss band as an early-warning window",
    ],
    file_name="sensitivity.py",
)
