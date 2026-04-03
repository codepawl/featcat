"""Feature detail panel widget."""

from __future__ import annotations

from textual.widgets import Static

from ...catalog.models import Feature


class FeatureDetail(Static):
    """Displays detailed info about a selected feature."""

    DEFAULT_CSS = """
    FeatureDetail {
        padding: 1;
        overflow-y: auto;
    }
    """

    def show_feature(self, feature: Feature, doc: dict | None = None) -> None:
        """Update the panel to show a feature's details."""
        lines = [
            f"[bold cyan]{feature.name}[/bold cyan]",
            "",
            f"[bold]Column:[/bold] {feature.column_name}",
            f"[bold]Dtype:[/bold] {feature.dtype}",
            f"[bold]Owner:[/bold] {feature.owner or '(none)'}",
            f"[bold]Tags:[/bold] {', '.join(feature.tags) if feature.tags else '(none)'}",
            "",
        ]

        if feature.stats:
            lines.append("[bold]Statistics:[/bold]")
            for k, v in feature.stats.items():
                lines.append(f"  {k}: {v}")
            lines.append("")

        if doc:
            lines.append("[bold]Documentation:[/bold]")
            if doc.get("short_description"):
                lines.append(f"  {doc['short_description']}")
            if doc.get("long_description"):
                lines.append(f"  {doc['long_description']}")
            if doc.get("expected_range"):
                lines.append(f"  Range: {doc['expected_range']}")
        else:
            lines.append("[dim]No documentation yet[/dim]")

        self.update("\n".join(lines))

    def clear_detail(self) -> None:
        self.update("[dim]Select a feature to view details[/dim]")
