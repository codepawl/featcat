"""Main Textual application for featcat TUI."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from .screens.chat import ChatScreen
from .screens.dashboard import DashboardScreen
from .screens.features import FeaturesScreen
from .screens.monitoring import MonitoringScreen

CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"


class FeatcatApp(App):
    """featcat Terminal UI Application."""

    TITLE = "featcat | Feature Catalog"
    CSS_PATH = CSS_PATH

    MODES = {
        "dashboard": DashboardScreen,
        "features": FeaturesScreen,
        "monitoring": MonitoringScreen,
        "chat": ChatScreen,
    }

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("question_mark", "help", "Help"),
    ]

    def on_mount(self) -> None:
        self.switch_mode("dashboard")

    def action_help(self) -> None:
        self.notify(
            "Keybindings: [D]ashboard [F]eatures [M]onitor [C]hat [Q]uit [/]Search [?]Help",
            title="Help",
            timeout=5,
        )
