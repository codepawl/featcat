"""Feature browser screen: table + detail panel + search."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, Input

from ..widgets.feature_detail import FeatureDetail
from ..widgets.feature_table import FeatureTable

if TYPE_CHECKING:
    from textual.app import ComposeResult


class FeaturesScreen(Screen):
    """Browse, search, and inspect features."""

    BINDINGS = [
        ("d", "switch_screen('dashboard')", "Dashboard"),
        ("m", "switch_screen('monitoring')", "Monitor"),
        ("c", "switch_screen('chat')", "Chat"),
        ("slash", "focus_search", "Search"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Search features...", id="search-input")
        yield Horizontal(
            FeatureTable(id="feature-table"),
            FeatureDetail(id="feature-detail"),
            id="feature-browser",
        )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#feature-table", FeatureTable)
        table.setup_columns()
        self._load_features()

    def _load_features(self) -> None:
        try:
            from ...catalog.factory import get_backend

            db = get_backend()
            self._features = db.list_features()
            db.close()

            table = self.query_one("#feature-table", FeatureTable)
            table.load_features(self._features)
        except Exception:
            self._features = []

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            table = self.query_one("#feature-table", FeatureTable)
            table.filter_rows(event.value)

    def on_data_table_row_selected(self, event: FeatureTable.RowSelected) -> None:
        """Show detail when a row is selected."""
        row_key = event.row_key.value
        if row_key is None:
            return
        feature = next((f for f in self._features if f.name == row_key), None)
        if feature:
            detail = self.query_one("#feature-detail", FeatureDetail)
            # Try to load doc
            doc = None
            try:
                from ...catalog.factory import get_backend
                from ...plugins.autodoc import get_doc

                db = get_backend()
                doc = get_doc(db, feature.name)
                db.close()
            except Exception:
                pass
            detail.show_feature(feature, doc)

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_switch_screen(self, screen_name: str) -> None:
        self.app.switch_mode(screen_name)
