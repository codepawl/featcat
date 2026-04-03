"""CLI entry point for featcat using Typer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .catalog.db import CatalogDB, DEFAULT_DB
from .catalog.models import DataSource, Feature
from .catalog.scanner import scan_source
from .config import load_settings

app = typer.Typer(name="featcat", help="Lightweight AI-powered Feature Catalog")
source_app = typer.Typer(help="Manage data sources")
feature_app = typer.Typer(help="Manage features")
doc_app = typer.Typer(help="AI-generated feature documentation")
monitor_app = typer.Typer(help="Feature quality monitoring")
cache_app = typer.Typer(help="Manage LLM response cache")
app.add_typer(source_app, name="source")
app.add_typer(feature_app, name="feature")
app.add_typer(doc_app, name="doc")
app.add_typer(monitor_app, name="monitor")
app.add_typer(cache_app, name="cache")

console = Console()


def _get_db() -> CatalogDB:
    settings = load_settings()
    return CatalogDB(settings.catalog_db_path)


def _get_llm(use_cache: bool = True):
    """Create an LLM instance. Wraps with caching if use_cache is True."""
    from .llm import create_llm

    settings = load_settings()
    try:
        llm = create_llm(
            backend=settings.llm_backend,
            model=settings.llm_model,
            base_url=settings.ollama_url if settings.llm_backend == "ollama" else settings.llamacpp_url,
            timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries,
        )
        if use_cache:
            from .llm.cached import CachedLLM
            from .utils.cache import ResponseCache
            cache = ResponseCache(settings.catalog_db_path)
            return CachedLLM(llm, cache)
        return llm
    except Exception:
        return None


# =========================================================================
# Top-level commands
# =========================================================================


@app.command()
def init() -> None:
    """Initialize the catalog database."""
    db = CatalogDB(DEFAULT_DB)
    db.init_db()
    # Also create cache table
    from .utils.cache import ResponseCache
    ResponseCache(DEFAULT_DB).close()
    db.close()
    console.print(f"[green]Catalog initialized:[/green] {DEFAULT_DB}")


@app.command()
def doctor() -> None:
    """Check system health and report status."""
    settings = load_settings()
    all_ok = True

    # Python version
    py_ver = sys.version_info
    ok = py_ver >= (3, 10)
    _print_check(ok, f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if not ok:
        all_ok = False

    # Catalog DB
    db_exists = Path(settings.catalog_db_path).exists()
    _print_check(db_exists, f"SQLite catalog exists ({settings.catalog_db_path})")
    if not db_exists:
        all_ok = False
        console.print()
        return

    # Feature count
    db = CatalogDB(settings.catalog_db_path)
    try:
        features = db.list_features()
        sources = db.list_sources()
        _print_check(True, f"{len(features)} features registered from {len(sources)} sources")

        # Doc coverage
        from .plugins.autodoc import get_doc_stats
        doc_stats = get_doc_stats(db)
        has_docs = doc_stats["documented"] > 0
        _print_check(has_docs, f"{doc_stats['documented']} features have docs ({doc_stats['coverage']:.1f}%)")

        # Monitoring alerts
        from .plugins.monitoring import MonitoringPlugin
        plugin = MonitoringPlugin()
        result = plugin.execute(db, None, action="check")
        warnings = result.data.get("warnings", 0)
        critical = result.data.get("critical", 0)
        alert_count = warnings + critical
        if alert_count > 0:
            _print_check(False, f"{alert_count} features have drift alerts ({critical} critical, {warnings} warnings)")
            all_ok = False
        else:
            checked = result.data.get("checked", 0)
            if checked > 0:
                _print_check(True, f"All {checked} monitored features healthy")
            else:
                _print_check(True, "No monitoring baselines yet (run: featcat monitor baseline)")
    finally:
        db.close()

    # Ollama
    try:
        from .llm.ollama import OllamaLLM
        ollama = OllamaLLM(model=settings.llm_model, base_url=settings.ollama_url)
        reachable = ollama.health_check()
        _print_check(reachable, f"Ollama running at {settings.ollama_url}")
        if reachable:
            # Check model availability
            import json
            from urllib.request import urlopen
            resp = urlopen(f"{settings.ollama_url}/api/tags", timeout=5)
            data = json.loads(resp.read())
            model_names = [m.get("name", "") for m in data.get("models", [])]
            model_found = any(settings.llm_model in n for n in model_names)
            _print_check(model_found, f"Model {settings.llm_model} available")
            if not model_found:
                all_ok = False
        else:
            all_ok = False
            _print_check(False, f"Model {settings.llm_model} (Ollama not running)")
    except Exception:
        _print_check(False, f"Ollama at {settings.ollama_url}")
        _print_check(False, f"Model {settings.llm_model}")
        all_ok = False

    # Cache stats
    try:
        from .utils.cache import ResponseCache
        cache = ResponseCache(settings.catalog_db_path)
        cs = cache.stats()
        cache.close()
        _print_check(True, f"Cache: {cs['active']} active entries, {cs['expired']} expired")
    except Exception:
        pass

    console.print()
    if all_ok:
        console.print("[green]All checks passed![/green]")
    else:
        console.print("[yellow]Some checks failed. See above for details.[/yellow]")


@app.command()
def stats() -> None:
    """Show catalog overview statistics."""
    db = _get_db()

    features = db.list_features()
    sources = db.list_sources()

    from .plugins.autodoc import get_doc_stats
    doc_stats = get_doc_stats(db)

    from .plugins.monitoring import MonitoringPlugin
    plugin = MonitoringPlugin()
    result = plugin.execute(db, None, action="check")
    report = result.data

    db.close()

    console.print("\n[bold]featcat Catalog Overview[/bold]")
    console.print(f"  Sources:      {len(sources)}")
    console.print(f"  Features:     {len(features)}")

    cov = doc_stats["coverage"]
    cov_color = "green" if cov >= 80 else "yellow" if cov >= 50 else "red"
    console.print(f"  Doc coverage: [{cov_color}]{cov:.1f}%[/{cov_color}] ({doc_stats['documented']}/{doc_stats['total_features']})")

    checked = report.get("checked", 0)
    healthy = report.get("healthy", 0)
    warnings = report.get("warnings", 0)
    critical = report.get("critical", 0)

    if checked > 0:
        console.print(f"  Monitoring:   [green]{healthy}[/green] healthy, [yellow]{warnings}[/yellow] warnings, [red]{critical}[/red] critical")
    else:
        console.print("  Monitoring:   [dim]no baselines[/dim]")

    # Sources table
    if sources:
        console.print()
        table = Table(title="Sources")
        table.add_column("Name", style="cyan")
        table.add_column("Type")
        table.add_column("Features", justify="right")
        for s in sources:
            feat_count = len(db.list_features(source_name=s.name)) if False else len([f for f in features if f.name.startswith(s.name + ".")])
            table.add_row(s.name, s.storage_type, str(feat_count))
        console.print(table)

    console.print()


@app.command(name="export")
def export_catalog(
    format: str = typer.Option("json", help="Output format: json, csv, markdown"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
    """Export catalog data."""
    db = _get_db()
    features = db.list_features()
    db.close()

    if format == "json":
        data = [
            {
                "name": f.name,
                "column_name": f.column_name,
                "dtype": f.dtype,
                "tags": f.tags,
                "owner": f.owner,
                "description": f.description,
                "stats": f.stats,
            }
            for f in features
        ]
        text = json.dumps(data, indent=2, default=str)

    elif format == "csv":
        lines = ["name,column_name,dtype,tags,owner,null_ratio"]
        for f in features:
            tags = "|".join(f.tags)
            null_ratio = f.stats.get("null_ratio", "")
            lines.append(f"{f.name},{f.column_name},{f.dtype},{tags},{f.owner},{null_ratio}")
        text = "\n".join(lines)

    elif format == "markdown":
        lines = ["# Feature Catalog Export", ""]
        lines.append(f"| Name | Dtype | Tags | Owner | Null Ratio |")
        lines.append("|------|-------|------|-------|------------|")
        for f in features:
            tags = ", ".join(f.tags) if f.tags else ""
            nr = f.stats.get("null_ratio", "")
            nr_str = f"{nr:.1%}" if isinstance(nr, (int, float)) else str(nr)
            lines.append(f"| {f.name} | {f.dtype} | {tags} | {f.owner} | {nr_str} |")
        text = "\n".join(lines)
    else:
        console.print(f"[red]Unknown format:[/red] {format}. Use json, csv, or markdown.")
        raise typer.Exit(1)

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text)
        console.print(f"[green]Exported to:[/green] {output}")
    else:
        console.print(text)


# =========================================================================
# Source commands
# =========================================================================


@source_app.command("add")
def source_add(
    name: str = typer.Argument(help="Unique name for this data source"),
    path: str = typer.Argument(help="Local path or s3:// URI"),
    format: str = typer.Option("parquet", help="File format: parquet or csv"),
    description: str = typer.Option("", help="Optional description"),
) -> None:
    """Register a new data source."""
    storage_type = "s3" if path.startswith("s3://") else "local"

    if storage_type == "local":
        path = str(Path(path).resolve())

    source = DataSource(
        name=name,
        path=path,
        storage_type=storage_type,
        format=format,
        description=description,
    )
    db = _get_db()
    try:
        db.add_source(source)
        console.print(f"[green]Source added:[/green] {name} -> {path}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        db.close()


@source_app.command("list")
def source_list() -> None:
    """List all registered data sources."""
    db = _get_db()
    sources = db.list_sources()
    db.close()

    if not sources:
        console.print("[dim]No data sources registered. Use 'featcat source add' first.[/dim]")
        return

    table = Table(title="Data Sources")
    table.add_column("Name", style="cyan")
    table.add_column("Path")
    table.add_column("Type")
    table.add_column("Format")
    table.add_column("Description")

    for s in sources:
        table.add_row(s.name, s.path, s.storage_type, s.format, s.description)

    console.print(table)


@source_app.command("scan")
def source_scan(
    name: str = typer.Argument(help="Name of the data source to scan"),
) -> None:
    """Scan a data source and auto-register features."""
    db = _get_db()
    source = db.get_source_by_name(name)
    if source is None:
        console.print(f"[red]Source not found:[/red] {name}")
        db.close()
        raise typer.Exit(1)

    console.print(f"[blue]Scanning:[/blue] {source.path}")

    try:
        columns = scan_source(source.path)
    except Exception as e:
        console.print(f"[red]Scan failed:[/red] {e}")
        db.close()
        raise typer.Exit(1)

    registered = 0
    for col in columns:
        feature_name = f"{source.name}.{col.column_name}"
        feature = Feature(
            name=feature_name,
            data_source_id=source.id,
            column_name=col.column_name,
            dtype=col.dtype,
            stats=col.stats,
        )
        db.upsert_feature(feature)
        registered += 1

    db.close()
    console.print(
        f"[green]Done:[/green] {registered} features registered from [cyan]{name}[/cyan]"
    )


# =========================================================================
# Feature commands
# =========================================================================


@feature_app.command("list")
def feature_list(
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Filter by source name"),
) -> None:
    """List all features."""
    db = _get_db()
    features = db.list_features(source_name=source)
    db.close()

    if not features:
        console.print("[dim]No features found. Use 'featcat source scan' first.[/dim]")
        return

    table = Table(title="Features")
    table.add_column("Name", style="cyan")
    table.add_column("Column")
    table.add_column("Dtype")
    table.add_column("Tags")
    table.add_column("Nulls", justify="right")

    for f in features:
        null_ratio = f.stats.get("null_ratio", "")
        null_str = f"{null_ratio:.1%}" if isinstance(null_ratio, (int, float)) else str(null_ratio)
        tags_str = ", ".join(f.tags) if f.tags else ""
        table.add_row(f.name, f.column_name, f.dtype, tags_str, null_str)

    console.print(table)


@feature_app.command("info")
def feature_info(
    name: str = typer.Argument(help="Feature name (e.g. source.column)"),
) -> None:
    """Show detailed information about a feature."""
    db = _get_db()
    feature = db.get_feature_by_name(name)
    db.close()

    if feature is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{feature.name}[/bold cyan]")
    console.print(f"  Column:      {feature.column_name}")
    console.print(f"  Dtype:       {feature.dtype}")
    console.print(f"  Description: {feature.description or '(none)'}")
    console.print(f"  Owner:       {feature.owner or '(none)'}")
    console.print(f"  Tags:        {', '.join(feature.tags) if feature.tags else '(none)'}")
    console.print(f"  Source ID:   {feature.data_source_id}")
    console.print(f"  Created:     {feature.created_at}")
    console.print(f"  Updated:     {feature.updated_at}")

    if feature.stats:
        console.print("\n  [bold]Statistics:[/bold]")
        for k, v in feature.stats.items():
            console.print(f"    {k}: {v}")
    console.print()


@feature_app.command("tag")
def feature_tag(
    name: str = typer.Argument(help="Feature name"),
    tags: list[str] = typer.Argument(help="Tags to add"),
) -> None:
    """Add tags to a feature."""
    db = _get_db()
    feature = db.get_feature_by_name(name)
    if feature is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        db.close()
        raise typer.Exit(1)

    merged = list(set(feature.tags + tags))
    db.update_feature_tags(feature.id, merged)
    db.close()
    console.print(f"[green]Tags updated:[/green] {name} -> {merged}")


@feature_app.command("search")
def feature_search(
    query: str = typer.Argument(help="Keyword to search for"),
) -> None:
    """Search features by keyword (name, description, tags, column)."""
    db = _get_db()
    results = db.search_features(query)
    db.close()

    if not results:
        console.print(f"[dim]No features matching '{query}'[/dim]")
        return

    table = Table(title=f"Search results for '{query}'")
    table.add_column("Name", style="cyan")
    table.add_column("Column")
    table.add_column("Dtype")
    table.add_column("Tags")

    for f in results:
        tags_str = ", ".join(f.tags) if f.tags else ""
        table.add_row(f.name, f.column_name, f.dtype, tags_str)

    console.print(table)


# =========================================================================
# Discover command
# =========================================================================


@app.command()
def discover(
    use_case: str = typer.Argument(help="Description of the use case"),
) -> None:
    """Discover relevant features for a use case using AI."""
    llm = _get_llm(use_cache=False)  # Discovery: no cache
    if llm is None:
        console.print("[red]LLM unavailable.[/red] Ensure Ollama is running: ollama serve")
        raise typer.Exit(1)

    db = _get_db()
    settings = load_settings()

    from .plugins.discovery import DiscoveryPlugin
    plugin = DiscoveryPlugin()

    with console.status("[blue]Analyzing catalog..."):
        result = plugin.execute(
            db, llm, use_case=use_case, max_features=settings.max_context_features,
        )
    db.close()

    if result.status == "error":
        console.print(f"[red]Error:[/red] {'; '.join(result.errors)}")
        raise typer.Exit(1)

    data = result.data

    existing = data.get("existing_features", [])
    if existing:
        table = Table(title="Relevant Existing Features")
        table.add_column("Feature", style="cyan")
        table.add_column("Relevance", justify="right")
        table.add_column("Reason")
        for f in existing:
            score = f.get("relevance", 0)
            color = "green" if score >= 0.8 else "yellow" if score >= 0.5 else "dim"
            table.add_row(f["name"], f"[{color}]{score:.0%}[/{color}]", f.get("reason", ""))
        console.print(table)

    suggestions = data.get("new_feature_suggestions", [])
    if suggestions:
        console.print()
        table = Table(title="New Feature Suggestions")
        table.add_column("Name", style="green")
        table.add_column("Source")
        table.add_column("How to Compute")
        table.add_column("Reason")
        for s in suggestions:
            table.add_row(s.get("name", ""), s.get("source", ""), s.get("column_expression", ""), s.get("reason", ""))
        console.print(table)

    summary = data.get("summary", "")
    if summary:
        console.print()
        console.print(Panel(summary, title="Strategy Summary", border_style="blue"))


# =========================================================================
# Ask command (Natural Language Query)
# =========================================================================


@app.command()
def ask(
    query: str = typer.Argument(help="Natural language query about features"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass response cache"),
) -> None:
    """Search features using natural language."""
    db = _get_db()
    llm = _get_llm(use_cache=not no_cache)

    from .plugins.nl_query import NLQueryPlugin
    plugin = NLQueryPlugin()
    fallback = llm is None

    if fallback:
        console.print("[dim]LLM unavailable, using keyword search.[/dim]")

    with console.status("[blue]Searching..."):
        result = plugin.execute(db, llm, query=query, fallback_only=fallback)
    db.close()

    if result.status == "error":
        console.print(f"[red]Error:[/red] {'; '.join(result.errors)}")
        raise typer.Exit(1)

    data = result.data
    results = data.get("results", [])

    if not results:
        console.print("[dim]No matching features found.[/dim]")
        return

    table = Table(title="Search Results")
    table.add_column("Feature", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Reason")

    for r in results:
        score = r.get("score", 0)
        color = "green" if score >= 0.8 else "yellow" if score >= 0.5 else "dim"
        table.add_row(r["feature"], f"[{color}]{score:.0%}[/{color}]", r.get("reason", ""))

    console.print(table)

    interpretation = data.get("interpretation")
    if interpretation:
        console.print(f"\n[dim]Interpretation: {interpretation}[/dim]")

    follow_up = data.get("follow_up")
    if follow_up:
        console.print(f"[dim]Try also: {follow_up}[/dim]")


# =========================================================================
# Doc commands
# =========================================================================


@doc_app.command("generate")
def doc_generate(
    name: Optional[str] = typer.Argument(None, help="Feature name (or omit for all)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass response cache"),
) -> None:
    """Generate AI documentation for features."""
    llm = _get_llm(use_cache=not no_cache)
    if llm is None:
        console.print("[red]LLM unavailable.[/red] Ensure Ollama is running: ollama serve")
        raise typer.Exit(1)

    db = _get_db()

    from rich.progress import Progress
    from .plugins.autodoc import AutodocPlugin
    plugin = AutodocPlugin()

    if name:
        with console.status(f"[blue]Generating doc for {name}..."):
            result = plugin.execute(db, llm, feature_name=name)
    else:
        with Progress(console=console) as progress:
            task = progress.add_task("[blue]Generating docs...", total=None)

            def on_progress(current: int, total: int) -> None:
                progress.update(task, completed=current, total=total)

            result = plugin.execute(db, llm, progress_callback=on_progress)

    db.close()

    if result.status == "error":
        console.print(f"[red]Error:[/red] {'; '.join(result.errors)}")
        raise typer.Exit(1)

    documented = result.data.get("documented", 0)
    console.print(f"[green]Done:[/green] {documented} features documented")

    if result.errors:
        for err in result.errors:
            console.print(f"[yellow]Warning:[/yellow] {err}")


@doc_app.command("show")
def doc_show(
    name: str = typer.Argument(help="Feature name"),
) -> None:
    """Display documentation for a feature."""
    db = _get_db()
    from .plugins.autodoc import get_doc
    doc = get_doc(db, name)
    db.close()

    if doc is None:
        console.print(f"[dim]No documentation for '{name}'. Run 'featcat doc generate {name}' first.[/dim]")
        return

    console.print(f"\n[bold cyan]{name}[/bold cyan]")
    console.print(f"  {doc.get('short_description', '')}")
    console.print()
    if doc.get("long_description"):
        console.print(f"  {doc['long_description']}")
        console.print()
    if doc.get("expected_range"):
        console.print(f"  [bold]Expected range:[/bold] {doc['expected_range']}")
    if doc.get("potential_issues"):
        console.print(f"  [bold]Potential issues:[/bold] {doc['potential_issues']}")
    if doc.get("model_used"):
        console.print(f"\n  [dim]Generated by: {doc['model_used']}[/dim]")
    console.print()


@doc_app.command("export")
def doc_export(
    output: str = typer.Option("docs/features.md", help="Output file path"),
) -> None:
    """Export all feature documentation to Markdown."""
    db = _get_db()
    from .plugins.autodoc import export_docs_markdown
    markdown = export_docs_markdown(db)
    db.close()

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown)
    console.print(f"[green]Exported to:[/green] {output}")


@doc_app.command("stats")
def doc_stats() -> None:
    """Show documentation coverage statistics."""
    db = _get_db()
    from .plugins.autodoc import get_doc_stats
    s = get_doc_stats(db)
    db.close()

    console.print(f"\n[bold]Documentation Coverage[/bold]")
    console.print(f"  Total features:  {s['total_features']}")
    console.print(f"  Documented:      {s['documented']}")
    console.print(f"  Undocumented:    {s['undocumented']}")

    coverage = s["coverage"]
    color = "green" if coverage >= 80 else "yellow" if coverage >= 50 else "red"
    console.print(f"  Coverage:        [{color}]{coverage:.1f}%[/{color}]")
    console.print()


# =========================================================================
# Monitor commands
# =========================================================================


@monitor_app.command("baseline")
def monitor_baseline() -> None:
    """Compute and save baseline statistics for all features."""
    db = _get_db()
    from .plugins.monitoring import MonitoringPlugin
    plugin = MonitoringPlugin()
    result = plugin.execute(db, None, action="baseline")
    db.close()
    console.print(f"[green]Baseline saved:[/green] {result.data.get('baselines_saved', 0)} features")


@monitor_app.command("check")
def monitor_check(
    name: Optional[str] = typer.Argument(None, help="Feature name (or omit for all)"),
    refresh_baseline: bool = typer.Option(False, "--refresh-baseline", help="Update baseline after check"),
    use_llm: bool = typer.Option(False, "--llm", help="Include LLM analysis for issues"),
) -> None:
    """Check features for quality issues and drift."""
    db = _get_db()
    llm = _get_llm() if use_llm else None

    from .plugins.monitoring import MonitoringPlugin
    plugin = MonitoringPlugin()

    with console.status("[blue]Running quality checks..."):
        result = plugin.execute(
            db, llm, action="check", feature_name=name,
            refresh_baseline=refresh_baseline,
            use_llm=use_llm and llm is not None,
        )
    db.close()

    report = result.data
    checked = report.get("checked", 0)
    healthy = report.get("healthy", 0)
    warnings = report.get("warnings", 0)
    critical = report.get("critical", 0)

    console.print(f"\n[bold]Quality Check Results[/bold]")
    console.print(f"  Checked:  {checked}")
    console.print(f"  [green]Healthy:  {healthy}[/green]")
    if warnings:
        console.print(f"  [yellow]Warnings: {warnings}[/yellow]")
    if critical:
        console.print(f"  [red]Critical: {critical}[/red]")

    details = report.get("details", [])
    issues = [d for d in details if d.get("severity") != "healthy"]

    if issues:
        console.print()
        table = Table(title="Issues Detected")
        table.add_column("Feature", style="cyan")
        table.add_column("Severity")
        table.add_column("PSI", justify="right")
        table.add_column("Issues")
        for d in issues:
            sev = d["severity"]
            sev_color = "red" if sev == "critical" else "yellow"
            psi_str = f"{d['psi']:.4f}" if d.get("psi") is not None else "-"
            issue_msgs = "; ".join(i.get("message", "") for i in d.get("issues", []))
            table.add_row(d["feature"], f"[{sev_color}]{sev}[/{sev_color}]", psi_str, issue_msgs)
        console.print(table)
    elif checked > 0:
        console.print("\n  [green]All features are healthy.[/green]")
    else:
        console.print("\n  [dim]No baselines found. Run 'featcat monitor baseline' first.[/dim]")
    console.print()


@monitor_app.command("report")
def monitor_report(
    output: str = typer.Option("docs/monitoring_report.md", help="Output file path"),
) -> None:
    """Export monitoring report to Markdown."""
    db = _get_db()
    from .plugins.monitoring import MonitoringPlugin, export_monitoring_report
    plugin = MonitoringPlugin()
    result = plugin.execute(db, None, action="check")
    db.close()

    markdown = export_monitoring_report(result.data)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown)
    console.print(f"[green]Report exported to:[/green] {output}")


# =========================================================================
# Cache commands
# =========================================================================


@cache_app.command("stats")
def cache_stats() -> None:
    """Show cache statistics."""
    settings = load_settings()
    from .utils.cache import ResponseCache
    cache = ResponseCache(settings.catalog_db_path)
    s = cache.stats()
    cache.close()
    console.print(f"\n[bold]LLM Response Cache[/bold]")
    console.print(f"  Total entries: {s['total']}")
    console.print(f"  Active:        {s['active']}")
    console.print(f"  Expired:       {s['expired']}")
    console.print()


@cache_app.command("clear")
def cache_clear() -> None:
    """Clear all cached LLM responses."""
    settings = load_settings()
    from .utils.cache import ResponseCache
    cache = ResponseCache(settings.catalog_db_path)
    count = cache.clear()
    cache.close()
    console.print(f"[green]Cleared {count} cache entries.[/green]")


# =========================================================================
# TUI command
# =========================================================================


@app.command()
def ui() -> None:
    """Launch the Terminal UI."""
    try:
        from .tui.app import FeatcatApp
        app_instance = FeatcatApp()
        app_instance.run()
    except ImportError:
        console.print("[red]TUI requires textual.[/red] Install with: pip install 'featcat[tui]'")
        raise typer.Exit(1)


# =========================================================================
# Helpers
# =========================================================================


def _print_check(ok: bool, message: str) -> None:
    marker = "[green][x][/green]" if ok else "[red][ ][/red]"
    console.print(f"  {marker} {message}")


if __name__ == "__main__":
    app()
