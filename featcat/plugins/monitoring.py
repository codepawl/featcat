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
    compute_psi,
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
        llm: BaseLLM,
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
        llm: BaseLLM,
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
                else:
                    critical += 1
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

        issues = [d for d in details if d["severity"] != "healthy"]
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
            "details": details,
        }

        return PluginResult(status="success", data=report)

    def _check_feature(self, feature: Feature, baseline: dict) -> dict:
        current = feature.stats or {}
        if not current:
            return {
                "feature": feature.name,
                "severity": "healthy",
                "psi": None,
                "issues": [],
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
                        break
        except Exception:
            pass


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
        "",
    ]

    details = report.get("details", [])
    issues = [d for d in details if d.get("severity") != "healthy"]

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
