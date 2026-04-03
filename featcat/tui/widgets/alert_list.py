"""Alert list widget for monitoring results."""

from __future__ import annotations

from textual.widgets import Static


class AlertList(Static):
    """Displays recent monitoring alerts."""

    DEFAULT_CSS = """
    AlertList {
        height: auto;
        max-height: 15;
        padding: 1;
    }
    """

    def show_alerts(self, alerts: list[dict]) -> None:
        """Display a list of monitoring alerts."""
        if not alerts:
            self.update("[green]No alerts. All features healthy.[/green]")
            return

        lines = ["[bold]Recent Alerts:[/bold]", ""]
        for a in alerts[:10]:
            severity = a.get("severity", "unknown")
            feature = a.get("feature", "?")
            color = "red" if severity == "critical" else "yellow"
            issues = "; ".join(i.get("message", "") for i in a.get("issues", []))
            psi = a.get("psi")
            psi_str = f" PSI={psi:.4f}" if psi is not None else ""
            lines.append(f"[{color}]{severity.upper()}[/{color}] {feature}{psi_str}")
            if issues:
                lines.append(f"  {issues}")

        self.update("\n".join(lines))
