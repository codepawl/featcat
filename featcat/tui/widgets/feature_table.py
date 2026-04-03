"""Feature DataTable widget with search/filter."""

from __future__ import annotations

from textual.widgets import DataTable


class FeatureTable(DataTable):
    """DataTable displaying features with sortable columns."""

    def __init__(self) -> None:
        super().__init__(cursor_type="row")
        self._all_rows: list[tuple] = []

    def setup_columns(self) -> None:
        self.add_column("Name", key="name", width=35)
        self.add_column("Source", key="source", width=20)
        self.add_column("Dtype", key="dtype", width=10)
        self.add_column("Tags", key="tags", width=25)
        self.add_column("Nulls", key="nulls", width=8)

    def load_features(self, features: list) -> None:
        """Load features into the table."""
        self._all_rows = []
        for f in features:
            source = f.name.split(".")[0] if "." in f.name else ""
            tags = ", ".join(f.tags) if f.tags else ""
            null_ratio = f.stats.get("null_ratio", "")
            nulls = f"{null_ratio:.1%}" if isinstance(null_ratio, (int, float)) else str(null_ratio)
            self._all_rows.append((f.name, source, f.dtype, tags, nulls))

        self._refresh_rows(self._all_rows)

    def filter_rows(self, query: str) -> None:
        """Filter table rows by search query."""
        if not query:
            self._refresh_rows(self._all_rows)
            return

        q = query.lower()
        filtered = [
            row for row in self._all_rows
            if any(q in str(cell).lower() for cell in row)
        ]
        self._refresh_rows(filtered)

    def _refresh_rows(self, rows: list[tuple]) -> None:
        self.clear()
        for row in rows:
            self.add_row(*row, key=row[0])
