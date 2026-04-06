"""Monitoring screen: display quality check results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class MonitoringScreen(Screen):
    """View feature quality monitoring results."""

    BINDINGS = [
        ("d", "switch_screen('dashboard')", "Dashboard"),
        ("f", "switch_screen('features')", "Features"),
        ("c", "switch_screen('chat')", "Chat"),
        ("r", "run_check", "Run Check"),
        ("b", "compute_baseline", "Baseline"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="monitor-summary")
        yield DataTable(id="monitor-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#monitor-table", DataTable)
        table.add_column("Feature", key="feature", width=35)
        table.add_column("Severity", key="severity", width=10)
        table.add_column("PSI", key="psi", width=10)
        table.add_column("Issues", key="issues")
        self._refresh_data()

    def _refresh_data(self) -> None:
        try:
            from ...catalog.factory import get_backend
            from ...plugins.monitoring import MonitoringPlugin

            db = get_backend()
            plugin = MonitoringPlugin()
            result = plugin.execute(db, None, action="check")
            db.close()

            report = result.data
            summary = self.query_one("#monitor-summary", Static)
            checked = report.get("checked", 0)
            healthy = report.get("healthy", 0)
            warnings = report.get("warnings", 0)
            critical = report.get("critical", 0)

            summary.update(
                f" Checked: {checked} | "
                f"[green]Healthy: {healthy}[/green] | "
                f"[yellow]Warning: {warnings}[/yellow] | "
                f"[red]Critical: {critical}[/red]"
            )

            table = self.query_one("#monitor-table", DataTable)
            table.clear()

            for d in report.get("details", []):
                sev = d.get("severity", "unknown")
                sev_color = {"healthy": "green", "warning": "yellow", "critical": "red"}.get(sev, "dim")
                psi = d.get("psi")
                psi_str = f"{psi:.4f}" if psi is not None else "-"
                issues = "; ".join(i.get("message", "") for i in d.get("issues", []))
                table.add_row(
                    d["feature"],
                    f"[{sev_color}]{sev}[/{sev_color}]",
                    psi_str,
                    issues or "-",
                )
        except Exception as e:
            summary = self.query_one("#monitor-summary", Static)
            summary.update(f"[red]Error:[/red] {e}")

    def action_run_check(self) -> None:
        self._refresh_data()

    def action_compute_baseline(self) -> None:
        try:
            from ...catalog.factory import get_backend
            from ...plugins.monitoring import MonitoringPlugin

            db = get_backend()
            plugin = MonitoringPlugin()
            plugin.execute(db, None, action="baseline")
            db.close()
            self.notify("Baseline computed successfully")
            self._refresh_data()
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def action_switch_screen(self, screen_name: str) -> None:
        self.app.switch_mode(screen_name)
