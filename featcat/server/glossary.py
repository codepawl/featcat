"""Glossary of catalog terms — definitions for scores, severities, and metrics.

Surfaced via `GET /api/docs/glossary` and the frontend ScoreTooltip + Help page.
Translations live in `web/src/locales/{en,vi}/glossary.json` for UI use; this
module returns the canonical English structure for clients that don't load i18n.
"""

from __future__ import annotations

GLOSSARY: dict[str, dict] = {
    "health_score": {
        "label": "Health Score",
        "description": (
            "0–100 composite score that reflects how well a feature is documented, used, "
            "and behaving. Higher is better."
        ),
        "formula": "documentation 40% + drift 30% + usage 20% + hints 10%",
        "thresholds": [
            {"grade": "A", "min": 90, "label": "Excellent"},
            {"grade": "B", "min": 75, "label": "Good"},
            {"grade": "C", "min": 60, "label": "Needs attention"},
            {"grade": "D", "min": 0, "label": "Poor"},
        ],
    },
    "health_grade": {
        "label": "Health Grade",
        "description": "Letter grade derived from health_score.",
        "values": {
            "A": "score ≥ 90 — fully documented, healthy, used recently",
            "B": "score 75–89 — minor gaps",
            "C": "score 60–74 — needs attention soon",
            "D": "score < 60 — poor, likely undocumented or drifting",
        },
    },
    "psi": {
        "label": "Population Stability Index (PSI)",
        "description": ("Measures distribution shift between baseline and current data. Higher PSI ⇒ more drift."),
        "thresholds": [
            {"range": "< 0.1", "severity": "healthy", "meaning": "stable"},
            {"range": "0.1 – 0.25", "severity": "warning", "meaning": "moderate drift"},
            {"range": "> 0.25", "severity": "critical", "meaning": "significant drift"},
        ],
    },
    "drift_severity": {
        "label": "Drift Severity",
        "description": "Severity bucket assigned to a monitoring check.",
        "values": {
            "healthy": "no significant drift detected",
            "warning": "moderate PSI drift, null spike, or range violation",
            "critical": "large PSI drift, multiple anomalies, or a hard failure",
            "unknown": "no baseline / no recent check available",
        },
    },
    "completeness": {
        "label": "Completeness",
        "description": (
            "Share of non-null values in the current data window vs. the baseline. Used to detect null spikes."
        ),
    },
    "quality_score": {
        "label": "Quality Score",
        "description": (
            "Discovery-time signal of how rich a feature's metadata is "
            "(naming, dtype, sample stats). Drives the Discovery plugin's ranking."
        ),
    },
    "monitoring_status": {
        "label": "Monitoring Status",
        "description": (
            "Aggregate status across recent monitoring runs for a feature or group: healthy / warning / critical."
        ),
    },
    "action_item": {
        "label": "Action Item",
        "description": (
            "Recommended action persisted in the catalog. Sources: drift_alert (auto from "
            "monitoring), chat (AI suggestion), autodoc (doc gap), manual (user-added). "
            "Status flow: pending → applied / dismissed / snoozed."
        ),
    },
}


def get_glossary() -> dict:
    return {"terms": GLOSSARY}
