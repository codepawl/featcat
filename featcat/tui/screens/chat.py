"""AI Chat screen: natural language queries with streaming."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.screen import Screen
from textual.widgets import Footer, Header, Input

from ..widgets.chat_messages import ChatMessages

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ChatScreen(Screen):
    """Interactive AI chat for querying the feature catalog."""

    BINDINGS = [
        ("d", "switch_screen('dashboard')", "Dashboard"),
        ("f", "switch_screen('features')", "Features"),
        ("m", "switch_screen('monitoring')", "Monitor"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield ChatMessages(id="chat-messages")
        yield Input(placeholder="Ask about features... (/discover, /search, /monitor)", id="chat-input")
        yield Footer()

    def on_mount(self) -> None:
        messages = self.query_one("#chat-messages", ChatMessages)
        messages.add_system_message("Welcome to featcat AI Chat. Ask anything about your features!")
        messages.add_system_message("Commands: /discover <use case> | /search <query> | /monitor")
        self.query_one("#chat-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "chat-input":
            return

        query = event.value.strip()
        if not query:
            return

        event.input.value = ""
        messages = self.query_one("#chat-messages", ChatMessages)
        messages.add_user_message(query)

        # Process in background
        self.run_worker(self._process_query(query), exclusive=True)

    async def _process_query(self, query: str) -> None:
        messages = self.query_one("#chat-messages", ChatMessages)

        try:
            from ...catalog.factory import get_backend
            from ...config import load_settings
            from ...llm.base import LLMConnectionError

            settings = load_settings()
            db = get_backend()

            # Route commands
            if query.startswith("/discover "):
                use_case = query[10:]
                await self._handle_discover(db, settings, use_case, messages)
            elif query.startswith("/monitor"):
                await self._handle_monitor(db, messages)
            else:
                await self._handle_ask(db, settings, query, messages)

            db.close()

        except LLMConnectionError:
            messages.add_ai_message("[red]LLM unavailable.[/red] Is Ollama running?")
        except Exception as e:
            messages.add_ai_message(f"[red]Error:[/red] {e}")

    async def _handle_ask(self, db, settings, query: str, messages: ChatMessages) -> None:
        from ...plugins.nl_query import NLQueryPlugin

        plugin = NLQueryPlugin()
        llm = self._create_llm(settings)

        msg_widget = messages.add_ai_message("Searching...")

        result = plugin.execute(db, llm, query=query, fallback_only=llm is None)

        if result.status == "error":
            messages.update_ai_message(msg_widget, f"[red]{'; '.join(result.errors)}[/red]")
            return

        data = result.data
        results = data.get("results", [])

        if not results:
            messages.update_ai_message(msg_widget, "No matching features found.")
            return

        lines = []
        for r in results[:10]:
            score = r.get("score", 0)
            lines.append(f"  {r['feature']} (score: {score:.0%}) - {r.get('reason', '')}")

        text = "\n".join(lines)
        if data.get("interpretation"):
            text += f"\n\n[dim]Interpretation: {data['interpretation']}[/dim]"

        messages.update_ai_message(msg_widget, text)

    async def _handle_discover(self, db, settings, use_case: str, messages: ChatMessages) -> None:
        from ...plugins.discovery import DiscoveryPlugin

        plugin = DiscoveryPlugin()
        llm = self._create_llm(settings)

        if llm is None:
            messages.add_ai_message("[red]Discovery requires an LLM. Start Ollama first.[/red]")
            return

        msg_widget = messages.add_ai_message("Analyzing catalog...")

        result = plugin.execute(db, llm, use_case=use_case)

        if result.status == "error":
            messages.update_ai_message(msg_widget, f"[red]{'; '.join(result.errors)}[/red]")
            return

        data = result.data
        lines = []

        existing = data.get("existing_features", [])
        if existing:
            lines.append("[bold]Relevant features:[/bold]")
            for f in existing[:10]:
                lines.append(f"  {f['name']} ({f.get('relevance', 0):.0%}) - {f.get('reason', '')}")

        suggestions = data.get("new_feature_suggestions", [])
        if suggestions:
            lines.append("\n[bold]Suggestions:[/bold]")
            for s in suggestions:
                lines.append(f"  {s.get('name', '')} from {s.get('source', '')} - {s.get('reason', '')}")

        summary = data.get("summary", "")
        if summary:
            lines.append(f"\n[dim]{summary}[/dim]")

        messages.update_ai_message(msg_widget, "\n".join(lines))

    async def _handle_monitor(self, db, messages: ChatMessages) -> None:
        from ...plugins.monitoring import MonitoringPlugin

        plugin = MonitoringPlugin()
        result = plugin.execute(db, None, action="check")
        report = result.data

        healthy = report.get("healthy", 0)
        warnings = report.get("warnings", 0)
        critical = report.get("critical", 0)

        lines = [
            f"Checked {report.get('checked', 0)} features:",
            f"  [green]Healthy: {healthy}[/green]",
            f"  [yellow]Warnings: {warnings}[/yellow]",
            f"  [red]Critical: {critical}[/red]",
        ]

        issues = [d for d in report.get("details", []) if d.get("severity") != "healthy"]
        if issues:
            lines.append("")
            for d in issues[:5]:
                sev = d["severity"]
                color = "red" if sev == "critical" else "yellow"
                lines.append(f"  [{color}]{d['feature']}[/{color}]: {sev}")

        messages.add_ai_message("\n".join(lines))

    def _create_llm(self, settings):
        try:
            from ...llm import create_llm

            llm = create_llm(
                backend=settings.llm_backend,
                model=settings.llm_model,
                base_url=settings.ollama_url if settings.llm_backend == "ollama" else settings.llamacpp_url,
            )
            if llm.health_check():
                return llm
        except Exception:
            pass
        return None

    def action_switch_screen(self, screen_name: str) -> None:
        self.app.switch_mode(screen_name)
