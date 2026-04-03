"""Quality Monitoring plugin: detect drift, anomalies, and data staleness."""

from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..utils.catalog_context import get_feature_detail
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
    from ..catalog.db import CatalogDB
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
        catalog_db: CatalogDB,
        llm: BaseLLM,
        **kwargs: Any,
    ) -> PluginResult:
        """Run monitoring checks.

        Args:
            action: "baseline" | "check" (required kwarg).
            feature_name: Optional, check only this feature.
            refresh_baseline: If True, update baseline after check.
            use_llm: If True, get LLM analysis for issues.
        """
        action: str = kwargs.get("action", "check")

        if action == "baseline":
            return self._compute_baseline(catalog_db, kwargs.get("feature_name"))
        elif action == "check":
            return self._run_check(
                catalog_db,
                llm,
                feature_name=kwargs.get("feature_name"),
                refresh_baseline=kwargs.get("refresh_baseline", False),
                use_llm=kwargs.get("use_llm", False),
            )
        else:
            return PluginResult(status="error", errors=[f"Unknown action: {action}"])

    def _compute_baseline(
        self,
        db: CatalogDB,
        feature_name: str | None = None,
    ) -> PluginResult:
        """Save current feature stats as baselines."""
        if feature_name:
            features = [db.get_feature_by_name(feature_name)]
            features = [f for f in features if f is not None]
        else:
            features = db.list_features()

        saved = 0
        for f in features:
            if not f.stats:
                continue
            now = datetime.now(timezone.utc)
            db.conn.execute("DELETE FROM monitoring_baselines WHERE feature_id = ?", (f.id,))
            db.conn.execute(
                "INSERT INTO monitoring_baselines (feature_id, baseline_stats, computed_at) VALUES (?, ?, ?)",
                (f.id, json.dumps(f.stats), now),
            )
            saved += 1
        db.conn.commit()

        return PluginResult(
            status="success",
            data={"baselines_saved": saved, "total_features": len(features)},
        )

    def _run_check(
        self,
        db: CatalogDB,
        llm: BaseLLM,
        feature_name: str | None = None,
        refresh_baseline: bool = False,
        use_llm: bool = False,
    ) -> PluginResult:
        """Compare current stats against baselines."""
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
            baseline = self._get_baseline(db, f.id)
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

        # LLM analysis for issues
        issues = [d for d in details if d["severity"] != "healthy"]
        if use_llm and issues:
            with contextlib.suppress(Exception):
                self._add_llm_analysis(db, llm, issues)

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

    def _get_baseline(self, db: CatalogDB, feature_id: str) -> dict | None:
        """Retrieve baseline stats for a feature."""
        row = db.conn.execute(
            "SELECT baseline_stats FROM monitoring_baselines WHERE feature_id = ?",
            (feature_id,),
        ).fetchone()
        if row is None:
            return None
        stats = row[0]
        return json.loads(stats) if isinstance(stats, str) else stats

    def _check_feature(self, feature: Feature, baseline: dict) -> dict:
        """Check a single feature against its baseline."""
        current = feature.stats
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

    def _add_llm_analysis(
        self,
        db: CatalogDB,
        llm: BaseLLM,
        issues: list[dict],
    ) -> None:
        """Add LLM analysis to issue details."""
        drift_report = json.dumps(issues, indent=2)
        feature_context = "\n\n".join(get_feature_detail(db, issue["feature"]) for issue in issues)

        prompt = MONITORING_ANALYSIS_PROMPT.format(
            drift_report=drift_report,
            feature_context=feature_context,
        )

        try:
            analysis = llm.generate_json(prompt, system=MONITORING_SYSTEM)
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
