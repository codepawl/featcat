"""Statistical utilities for quality monitoring: PSI, drift detection."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy as np


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

    Returns one of:
      "critical"  — PSI > 0.25 or a hard data-quality violation
      "warning"   — PSI in (0.1, 0.25] or any softer data-quality issue
      "healthy"   — PSI <= 0.1 and no issues (genuine "evaluated and fine")
      "unknown"   — no PSI signal and no issues to evaluate (no data,
                    not "evaluated and fine"). Callers MUST surface this
                    distinctly so a feature that has never been measured
                    is not silently bucketed as healthy on dashboards.
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

    if psi is None:
        return "unknown"

    return "healthy"


def compute_kl_divergence(
    baseline_hist: Sequence[float] | np.ndarray,
    current_hist: Sequence[float] | np.ndarray,
    epsilon: float = 1e-6,
) -> float | None:
    """KL divergence D_KL(current || baseline) on two same-shaped histograms.

    Applies Laplace smoothing (``epsilon``) so empty bins don't blow up the
    log term, then normalises each histogram to a probability distribution
    before calling ``scipy.stats.entropy``. Returns a non-negative float
    (already in nats), or ``None`` on shape mismatch / empty input / non-
    finite result.

    Unlike PSI's symmetric two-direction KL, this is the one-direction
    "how surprised would the baseline be by the current?" reading — a
    supplementary signal to PSI, never a severity driver on its own.
    """
    import numpy as np
    from scipy.stats import entropy

    base = np.asarray(baseline_hist, dtype=float)
    curr = np.asarray(current_hist, dtype=float)
    if base.shape != curr.shape or base.size == 0:
        return None

    base = base + epsilon
    curr = curr + epsilon
    base_sum = base.sum()
    curr_sum = curr.sum()
    if base_sum <= 0 or curr_sum <= 0:
        return None
    base = base / base_sum
    curr = curr / curr_sum
    kl = float(entropy(curr, base))
    if not np.isfinite(kl):
        return None
    return round(max(0.0, kl), 4)


def compute_wasserstein(
    baseline_values: Sequence[float] | np.ndarray,
    current_values: Sequence[float] | np.ndarray,
) -> float | None:
    """1-Wasserstein (earth-mover's) distance between two value samples.

    Returned in the original units of the values, so the operator can read
    "the mean shifted by ~X" directly from the chart — PSI's unitless
    score never gives that. Wrapper around
    ``scipy.stats.wasserstein_distance``; returns ``None`` on empty input
    or a non-finite result.
    """
    import numpy as np
    from scipy.stats import wasserstein_distance

    base = np.asarray(baseline_values, dtype=float)
    curr = np.asarray(current_values, dtype=float)
    if base.size == 0 or curr.size == 0:
        return None
    distance = float(wasserstein_distance(base, curr))
    if not np.isfinite(distance):
        return None
    return round(max(0.0, distance), 4)
