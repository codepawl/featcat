"""Quality Monitoring plugin: detect drift, anomalies, and data staleness."""

from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..utils.catalog_context import get_feature_detail
from ..utils.lang import localize_system_prompt
from ..utils.prompts import MONITORING_ANALYSIS_PROMPT, MONITORING_SYSTEM
from ..utils.statistics import (
    check_null_spike,
    check_range_violation,
    check_zero_variance,
    classify_severity,
    compute_kl_divergence,
    compute_psi,
    compute_wasserstein,
)
from .base import BasePlugin, PluginResult

if TYPE_CHECKING:
    from ..catalog.backend import CatalogBackend
    from ..catalog.models import Feature
    from ..llm.base import BaseLLM


class MonitoringPlugin(BasePlugin):
    """Monitor feature quality by comparing current stats against baselines."""

    @property
    def name(self) -> str:
        return "monitoring"

    @property
    def description(self) -> str:
        return "Monitor feature quality and detect drift"

    def execute(
        self,
        catalog_db: CatalogBackend,
        llm: BaseLLM | None,
        **kwargs: Any,
    ) -> PluginResult:
        action: str = kwargs.get("action", "check")
        language: str = kwargs.get("language", "en")

        if action == "baseline":
            return self._compute_baseline(catalog_db, kwargs.get("feature_name"))
        elif action == "check":
            return self._run_check(
                catalog_db,
                llm,
                feature_name=kwargs.get("feature_name"),
                refresh_baseline=kwargs.get("refresh_baseline", False),
                use_llm=kwargs.get("use_llm", False),
                language=language,
            )
        else:
            return PluginResult(status="error", errors=[f"Unknown action: {action}"])

    def _compute_baseline(self, db: CatalogBackend, feature_name: str | None = None) -> PluginResult:
        if feature_name:
            features = [db.get_feature_by_name(feature_name)]
            features = [f for f in features if f is not None]
        else:
            features = db.list_features()

        saved = 0
        for f in features:
            if not f.stats:
                continue
            db.save_baseline(f.id, f.stats)
            saved += 1

        return PluginResult(
            status="success",
            data={"baselines_saved": saved, "total_features": len(features)},
        )

    def _run_check(
        self,
        db: CatalogBackend,
        llm: BaseLLM | None,
        feature_name: str | None = None,
        refresh_baseline: bool = False,
        use_llm: bool = False,
        language: str = "en",
    ) -> PluginResult:
        if feature_name:
            features = [db.get_feature_by_name(feature_name)]
            features = [f for f in features if f is not None]
        else:
            features = db.list_features()

        details: list[dict] = []
        healthy = 0
        warnings = 0
        critical = 0
        unknown = 0

        for f in features:
            try:
                baseline = db.get_baseline(f.id)
                if baseline is None:
                    continue

                result = self._check_feature(f, baseline)
                details.append(result)

                severity = result["severity"]
                if severity == "healthy":
                    healthy += 1
                elif severity == "warning":
                    warnings += 1
                elif severity == "unknown":
                    unknown += 1
                else:
                    critical += 1

                # Save result for history tracking — including the auxiliary
                # metrics the multi-metric chart needs. Each is best-effort:
                # current_stats may not carry them on legacy rows or non-numeric
                # features (e.g. mean_z_score requires baseline.std > 0).
                current = result.get("current_stats") or {}
                baseline_stats = result.get("baseline_stats") or {}
                null_ratio = current.get("null_ratio")
                sample_size = current.get("total_count")
                mean_z_score: float | None = None
                b_mean = baseline_stats.get("mean")
                b_std = baseline_stats.get("std")
                c_mean = current.get("mean")
                if (
                    isinstance(b_mean, (int, float))
                    and isinstance(b_std, (int, float))
                    and isinstance(c_mean, (int, float))
                    and b_std
                ):
                    mean_z_score = round((c_mean - b_mean) / b_std, 4)

                kl_value, wasserstein_value = _supplementary_distribution_metrics(baseline_stats, current)
                # Annotate the in-memory result so the API payload exposes the
                # same supplementary signals the chart reads from history.
                result["kl_divergence"] = kl_value
                result["wasserstein"] = wasserstein_value

                with contextlib.suppress(Exception):
                    db.save_monitoring_result(
                        f.id,
                        f.name,
                        result.get("psi"),
                        severity,
                        null_ratio=null_ratio if isinstance(null_ratio, (int, float)) else None,
                        mean_z_score=mean_z_score,
                        sample_size=int(sample_size) if isinstance(sample_size, (int, float)) else None,
                        kl_divergence=kl_value,
                        wasserstein=wasserstein_value,
                    )

                # T2.1 — emit an in-app notification on warning/critical drift.
                # Best-effort: a notification-table outage shouldn't fail
                # the monitoring run.
                if severity in ("warning", "critical"):
                    psi = result.get("psi")
                    psi_str = f", PSI={psi:.3f}" if isinstance(psi, (int, float)) else ""
                    with contextlib.suppress(Exception):
                        db.create_notification(
                            kind="drift",
                            title=f"{severity.capitalize()} drift on {f.name}",
                            body=f"Drift detected on {f.name}{psi_str}.",
                            severity=severity,
                            feature_id=f.id,
                            link=f"/features/{f.name}",
                        )
            except Exception as e:
                details.append(
                    {
                        "feature": f.name,
                        "severity": "error",
                        "psi": None,
                        "issues": [{"issue": "check_failed", "message": str(e)}],
                    }
                )
                critical += 1

        # "unknown" rows have no PSI / no issues — they are gaps in data,
        # not actionable issues. Exclude from the LLM analysis fan-out so
        # the model is not asked to interpret nothing.
        issues = [d for d in details if d["severity"] not in ("healthy", "unknown")]
        if use_llm and issues:
            with contextlib.suppress(Exception):
                self._add_llm_analysis(db, llm, issues, language=language)

        if refresh_baseline:
            self._compute_baseline(db)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_features": len(features),
            "checked": len(details),
            "healthy": healthy,
            "warnings": warnings,
            "critical": critical,
            "unknown": unknown,
            "details": details,
        }

        return PluginResult(status="success", data=report)

    def _check_feature(self, feature: Feature, baseline: dict) -> dict:
        current = feature.stats or {}
        if not current:
            # No current stats to evaluate against the baseline — return
            # "unknown" (not "healthy") so the data gap is visible on
            # dashboards. Persisting "healthy" here was the root of UAT
            # finding "monitoring rows missing PSI" and the parallel "score
            # present but label unknown / healthy-while-grade-C" reports.
            return {
                "feature": feature.name,
                "severity": "unknown",
                "psi": None,
                "issues": [],
                "baseline_stats": baseline,
                "current_stats": {},
            }

        issues: list[dict] = []

        psi = compute_psi(baseline, current)

        null_issue = check_null_spike(baseline, current)
        if null_issue:
            issues.append(null_issue)

        range_issue = check_range_violation(baseline, current)
        if range_issue:
            issues.append(range_issue)

        variance_issue = check_zero_variance(current)
        if variance_issue:
            issues.append(variance_issue)

        severity = classify_severity(psi, issues)

        result: dict[str, Any] = {
            "feature": feature.name,
            "severity": severity,
            "psi": psi,
            "issues": issues,
            "baseline_stats": baseline,
            "current_stats": current,
        }

        if psi is not None and psi > 0.1:
            result["psi_message"] = f"PSI {psi:.4f} exceeds threshold 0.1"

        return result

    def _add_llm_analysis(self, db: CatalogBackend, llm: BaseLLM, issues: list[dict], language: str = "en") -> None:
        drift_report = json.dumps(issues, indent=2)
        feature_context = "\n\n".join(get_feature_detail(db, issue["feature"]) for issue in issues)

        prompt = MONITORING_ANALYSIS_PROMPT.format(
            drift_report=drift_report,
            feature_context=feature_context,
        )

        try:
            system = localize_system_prompt(MONITORING_SYSTEM, language)
            analysis = llm.generate_json(prompt, system=system, think=True)
            analyses = analysis.get("analyses", [])
            for a in analyses:
                fname = a.get("feature", "")
                for issue in issues:
                    if issue["feature"] == fname:
                        issue["llm_analysis"] = a
                        self._persist_llm_outcome(db, issue, a)
                        break
        except Exception:
            pass

    def _persist_llm_outcome(self, db: CatalogBackend, issue: dict, analysis: dict) -> None:
        """Save LLM analysis to monitoring_checks and auto-create pending action_items."""
        feat = db.get_feature_by_name(issue["feature"])
        if feat is None:
            return

        with contextlib.suppress(Exception):
            db.save_monitoring_llm_analysis(feat.id, analysis)

        actions = analysis.get("recommended_actions") or []
        ctx_base = {
            "severity": issue.get("severity"),
            "psi": issue.get("psi"),
            "likely_cause": analysis.get("likely_cause"),
            "issues": issue.get("issues", []),
        }
        for raw in actions:
            title, recommendation = self._normalize_action_text(raw)
            if not title:
                continue
            with contextlib.suppress(Exception):
                if db.find_pending_action(feat.id, "drift_alert", title) is not None:
                    continue
                db.create_action_item(
                    feature_id=feat.id,
                    source="drift_alert",
                    title=title,
                    recommendation=recommendation,
                    context=ctx_base,
                    created_by="monitoring_plugin",
                )

    @staticmethod
    def _normalize_action_text(raw: Any) -> tuple[str, str]:
        """Return (title, recommendation) from a recommended_action entry (str or dict)."""
        if isinstance(raw, dict):
            title = str(raw.get("title") or raw.get("action") or raw.get("summary") or "").strip()
            rec = raw.get("description") or raw.get("detail") or raw.get("recommendation") or title
            recommendation = str(rec).strip()
            return title, recommendation or title
        text = str(raw).strip()
        if not text:
            return "", ""
        first_line = text.splitlines()[0].strip()
        title = first_line[:120]
        return title, text


def _stats_to_samples(stats: dict, n: int = 500) -> list[float] | None:
    """Deterministic Gaussian proxy samples for KL + Wasserstein.

    The baseline + current dicts carry only summary stats (mean / std / etc.),
    not raw values. We synthesize a deterministic sample set using even
    quantile spacing through the Gaussian inverse CDF — matches the
    Gaussian assumption PSI already makes (`utils/statistics.compute_psi`)
    so all three metrics describe the same distribution proxy.

    Returns ``None`` when ``mean``/``std`` aren't usable numbers.
    """
    import numpy as np
    from scipy.stats import norm

    mean = stats.get("mean")
    std = stats.get("std")
    if not isinstance(mean, (int, float)) or not isinstance(std, (int, float)):
        return None
    if std <= 0:
        return [float(mean)] * n
    quantiles = np.linspace(1.0 / (n + 1), 1.0 - 1.0 / (n + 1), n)
    return list(norm.ppf(quantiles, loc=float(mean), scale=float(std)))


def _supplementary_distribution_metrics(baseline: dict, current: dict) -> tuple[float | None, float | None]:
    """Compute (kl_divergence, wasserstein) alongside PSI from summary stats.

    Returns ``(None, None)`` when either side lacks the mean/std needed to
    build the Gaussian proxy. Severity is unchanged — these are
    supplementary signals only (see `classify_severity` docstring).
    """
    import numpy as np

    base_samples = _stats_to_samples(baseline)
    curr_samples = _stats_to_samples(current)
    if base_samples is None or curr_samples is None:
        return None, None

    base_arr = np.asarray(base_samples, dtype=float)
    curr_arr = np.asarray(curr_samples, dtype=float)
    edges = np.linspace(
        float(min(base_arr.min(), curr_arr.min())),
        float(max(base_arr.max(), curr_arr.max())),
        21,  # 20 bins, matching the PSI bucket count convention
    )
    if edges[0] == edges[-1]:
        # Degenerate: both samples sit on the same constant → no shift.
        return 0.0, 0.0
    base_hist, _ = np.histogram(base_arr, bins=edges)
    curr_hist, _ = np.histogram(curr_arr, bins=edges)
    return (
        compute_kl_divergence(base_hist, curr_hist),
        compute_wasserstein(base_arr, curr_arr),
    )


def export_monitoring_report(report: dict) -> str:
    """Export a monitoring report to Markdown."""
    lines = [
        "# Feature Quality Report",
        "",
        f"**Timestamp:** {report.get('timestamp', 'N/A')}",
        f"**Total features:** {report.get('total_features', 0)}",
        f"**Checked:** {report.get('checked', 0)}",
        "",
        "| Status | Count |",
        "|--------|-------|",
        f"| Healthy | {report.get('healthy', 0)} |",
        f"| Warning | {report.get('warnings', 0)} |",
        f"| Critical | {report.get('critical', 0)} |",
        f"| Unknown | {report.get('unknown', 0)} |",
        "",
    ]

    details = report.get("details", [])
    # Issues = warnings + critical only. "unknown" rows are data gaps, not
    # actionable issues; the dashboard surfaces them separately.
    issues = [d for d in details if d.get("severity") not in ("healthy", "unknown")]

    if issues:
        lines.append("## Issues")
        lines.append("")
        for d in issues:
            severity = d.get("severity", "unknown").upper()
            lines.append(f"### {d['feature']} [{severity}]")
            if d.get("psi") is not None:
                lines.append(f"- **PSI:** {d['psi']:.4f}")
            for issue in d.get("issues", []):
                lines.append(f"- {issue.get('message', '')}")
            if d.get("llm_analysis"):
                a = d["llm_analysis"]
                lines.append(f"- **Likely cause:** {a.get('likely_cause', 'N/A')}")
                actions = a.get("recommended_actions", [])
                if actions:
                    lines.append("- **Recommended actions:**")
                    for act in actions:
                        lines.append(f"  - {act}")
            lines.append("")
    else:
        lines.append("All features are healthy.")

    return "\n".join(lines)
