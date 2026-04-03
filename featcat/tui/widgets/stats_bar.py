"""Stats overview bar widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class StatsBar(Static):
    """Displays summary statistics in a horizontal bar."""

    DEFAULT_CSS = """
    StatsBar {
        height: 3;
        layout: horizontal;
        background: $primary-darken-1;
        padding: 0 2;
    }
    StatsBar .stat {
        width: 1fr;
        content-align: center middle;
    }
    """

    def __init__(
        self,
        total_features: int = 0,
        total_sources: int = 0,
        doc_coverage: float = 0.0,
        alerts: int = 0,
    ) -> None:
        super().__init__()
        self.total_features = total_features
        self.total_sources = total_sources
        self.doc_coverage = doc_coverage
        self.alerts = alerts

    def compose(self) -> ComposeResult:
        yield Static(
            f"Features: [bold]{self.total_features}[/bold]",
            classes="stat",
        )
        yield Static(
            f"Sources: [bold]{self.total_sources}[/bold]",
            classes="stat",
        )
        yield Static(
            f"Docs: [bold]{self.doc_coverage:.0f}%[/bold]",
            classes="stat",
        )
        alert_color = "red" if self.alerts > 0 else "green"
        yield Static(
            f"Alerts: [{alert_color}][bold]{self.alerts}[/bold][/{alert_color}]",
            classes="stat",
        )

    def update_stats(
        self,
        total_features: int,
        total_sources: int,
        doc_coverage: float,
        alerts: int,
    ) -> None:
        self.total_features = total_features
        self.total_sources = total_sources
        self.doc_coverage = doc_coverage
        self.alerts = alerts
        self.refresh(layout=True)
