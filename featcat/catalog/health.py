"""Feature health score computation."""

from __future__ import annotations


def compute_health_score(
    has_doc: bool,
    has_hints: bool,
    drift_status: str | None,
    views_30d: int,
    queries_30d: int,
) -> dict:
    """Compute a 0-100 health score from documentation, drift, and usage signals.

    Weights:
    - Documentation: 40pts (short_description: 25, generation_hints: 15)
    - Drift: 40pts (healthy: 40, warning: 20, critical: 0, unknown: 30)
    - Usage: 20pts (queries>0: 10, views>0: 5, views>=5: +5)
    """
    doc_score = (25 if has_doc else 0) + (15 if has_hints else 0)

    drift_scores = {"healthy": 40, "warning": 20, "critical": 0}
    drift_score = drift_scores.get(drift_status, 30)  # type: ignore[arg-type]

    usage_score = 0
    if queries_30d > 0:
        usage_score += 10
    if views_30d > 0:
        usage_score += 5
    if views_30d >= 5:
        usage_score += 5

    total = doc_score + drift_score + usage_score

    if total >= 80:
        grade = "A"
    elif total >= 60:
        grade = "B"
    elif total >= 40:
        grade = "C"
    else:
        grade = "D"

    return {
        "score": total,
        "grade": grade,
        "breakdown": {
            "documentation": doc_score,
            "drift": drift_score,
            "usage": usage_score,
        },
    }
