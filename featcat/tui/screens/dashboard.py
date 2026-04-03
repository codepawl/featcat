"""Dashboard screen: home view with stats, alerts, and quick actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..widgets.alert_list import AlertList
from ..widgets.stats_bar import StatsBar

if TYPE_CHECKING:
    from textual.app import ComposeResult


class DashboardScreen(Screen):
    """Home dashboard showing overview stats and recent alerts."""

    BINDINGS = [
        ("f", "switch_screen('features')", "Features"),
        ("m", "switch_screen('monitoring')", "Monitor"),
        ("c", "switch_screen('chat')", "Chat"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatsBar(id="stats-bar")
        yield Vertical(
            Static("[bold]Welcome to featcat[/bold]", id="welcome"),
            AlertList(id="alert-list"),
            id="dashboard",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Load stats from the catalog DB."""
        try:
            from ...catalog.db import CatalogDB
            from ...config import load_settings
            from ...plugins.autodoc import get_doc_stats

            settings = load_settings()
            db = CatalogDB(settings.catalog_db_path)

            features = db.list_features()
            sources = db.list_sources()
            doc_stats = get_doc_stats(db)

            stats_bar = self.query_one("#stats-bar", StatsBar)
            stats_bar.update_stats(
                total_features=len(features),
                total_sources=len(sources),
                doc_coverage=doc_stats["coverage"],
                alerts=0,
            )

            # Try to load monitoring alerts
            alert_list = self.query_one("#alert-list", AlertList)
            try:
                from ...plugins.monitoring import MonitoringPlugin

                plugin = MonitoringPlugin()
                result = plugin.execute(db, None, action="check")
                details = result.data.get("details", [])
                alerts = [d for d in details if d.get("severity") != "healthy"]
                alert_list.show_alerts(alerts[:5])

                stats_bar.update_stats(
                    total_features=len(features),
                    total_sources=len(sources),
                    doc_coverage=doc_stats["coverage"],
                    alerts=len(alerts),
                )
            except Exception:
                alert_list.show_alerts([])

            db.close()
        except Exception as e:
            welcome = self.query_one("#welcome", Static)
            welcome.update(f"[red]Error loading catalog:[/red] {e}")

    def action_switch_screen(self, screen_name: str) -> None:
        self.app.switch_mode(screen_name)
