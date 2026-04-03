"""Chat message list widget with streaming support."""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static


class ChatMessages(VerticalScroll):
    """Scrollable container for chat messages."""

    DEFAULT_CSS = """
    ChatMessages {
        height: 1fr;
        padding: 1;
    }
    """

    def add_user_message(self, text: str) -> None:
        """Add a user message to the chat."""
        msg = Static(
            f"[bold cyan]You:[/bold cyan] {text}",
            classes="user-message",
        )
        self.mount(msg)
        self.scroll_end(animate=False)

    def add_ai_message(self, text: str) -> Static:
        """Add an AI message and return the widget for streaming updates."""
        msg = Static(
            f"[bold green]AI:[/bold green] {text}",
            classes="ai-message",
        )
        self.mount(msg)
        self.scroll_end(animate=False)
        return msg

    def update_ai_message(self, widget: Static, text: str) -> None:
        """Update an AI message widget (for streaming)."""
        widget.update(f"[bold green]AI:[/bold green] {text}")
        self.scroll_end(animate=False)

    def add_system_message(self, text: str) -> None:
        """Add a system/info message."""
        msg = Static(f"[dim]{text}[/dim]")
        self.mount(msg)
        self.scroll_end(animate=False)
