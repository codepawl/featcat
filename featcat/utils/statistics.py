"""Statistical utilities for quality monitoring: PSI, drift detection."""

from __future__ import annotations

import math
from typing import Any


def compute_psi(
    baseline_stats: dict[str, Any],
    current_stats: dict[str, Any],
    buckets: int = 10,
) -> float | None:
    """Compute Population Stability Index between baseline and current distributions.

    Uses a simplified PSI based on mean/std shift when full distributions are unavailable.
    PSI interpretation:
      < 0.1  : no significant change
      0.1-0.25: moderate change (warning)
      > 0.25 : significant change (critical)
    """
    b_mean: float | None = baseline_stats.get("mean")
    b_std: float | None = baseline_stats.get("std")
    c_mean: float | None = current_stats.get("mean")
    c_std: float | None = current_stats.get("std")

    if b_mean is None or b_std is None or c_mean is None or c_std is None:
        return None

    if b_std == 0 and c_std == 0:
        return 0.0

    # Simplified PSI using KL-divergence approximation for normal distributions
    if b_std == 0:
        b_std = 1e-10
    if c_std == 0:
        c_std = 1e-10

    try:
        term1 = math.log(c_std / b_std)
        term2 = (b_std**2 + (b_mean - c_mean) ** 2) / (2 * c_std**2)
        kl_bc = term1 + term2 - 0.5

        term1_r = math.log(b_std / c_std)
        term2_r = (c_std**2 + (c_mean - b_mean) ** 2) / (2 * b_std**2)
        kl_cb = term1_r + term2_r - 0.5

        psi = (kl_bc + kl_cb) / 2
        return round(max(0.0, psi), 4)
    except (ValueError, ZeroDivisionError):
        return None


def check_null_spike(
    baseline_stats: dict[str, Any],
    current_stats: dict[str, Any],
    threshold: float = 0.05,
) -> dict[str, Any] | None:
    """Detect if null ratio increased significantly vs baseline."""
    b_null: float | None = baseline_stats.get("null_ratio")
    c_null: float | None = current_stats.get("null_ratio")

    if b_null is None or c_null is None:
        return None

    delta = c_null - b_null
    if delta > threshold:
        return {
            "issue": "null_spike",
            "baseline_null_ratio": b_null,
            "current_null_ratio": c_null,
            "delta": round(delta, 4),
            "message": f"Null ratio increased by {delta:.1%} (baseline: {b_null:.1%}, current: {c_null:.1%})",
        }
    return None


def check_range_violation(
    baseline_stats: dict[str, Any],
    current_stats: dict[str, Any],
    n_std: float = 3.0,
) -> dict[str, Any] | None:
    """Detect if current min/max are outside baseline range +/- n_std."""
    b_min: float | None = baseline_stats.get("min")
    b_max: float | None = baseline_stats.get("max")
    b_std: float | None = baseline_stats.get("std")
    c_min: float | None = current_stats.get("min")
    c_max: float | None = current_stats.get("max")

    if b_min is None or b_max is None or b_std is None or c_min is None or c_max is None:
        return None

    lower_bound = b_min - n_std * b_std
    upper_bound = b_max + n_std * b_std

    violations = []
    if c_min < lower_bound:
        violations.append(f"min={c_min} below expected {lower_bound:.2f}")
    if c_max > upper_bound:
        violations.append(f"max={c_max} above expected {upper_bound:.2f}")

    if violations:
        return {
            "issue": "range_violation",
            "expected_range": [round(lower_bound, 4), round(upper_bound, 4)],
            "current_range": [c_min, c_max],
            "message": "Range violation: " + "; ".join(violations),
        }
    return None


def check_zero_variance(current_stats: dict[str, Any]) -> dict[str, Any] | None:
    """Detect if a feature has become constant (std = 0)."""
    c_std = current_stats.get("std")
    if c_std is not None and c_std == 0:
        return {
            "issue": "zero_variance",
            "message": f"Feature has zero variance (constant value: {current_stats.get('mean', '?')})",
        }
    return None


def classify_severity(psi: float | None, issues: list[dict[str, Any]]) -> str:
    """Classify overall severity for a feature.

    Returns: "healthy", "warning", or "critical"
    """
    if psi is not None and psi > 0.25:
        return "critical"

    for issue in issues:
        if issue.get("issue") == "range_violation":
            return "critical"

    if psi is not None and psi > 0.1:
        return "warning"

    if issues:
        return "warning"

    return "healthy"
