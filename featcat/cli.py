"""CLI entry point for featcat using Typer."""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import text

from .catalog.factory import get_backend
from .catalog.local import DEFAULT_DB, LocalBackend
from .catalog.models import DataSource, Feature, FeatureGroup, OnlineFeatureWrite
from .catalog.scanner import detect_file_format, discover_files, scan_source
from .catalog.storage import is_s3_uri
from .catalog.usage import log_feature_usage, resolve_user
from .config import load_settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from .diagnostics import AggregateReport, GroupReport

app = typer.Typer(name="featcat", help="Lightweight AI-powered Feature Catalog")
source_app = typer.Typer(help="Manage data sources")
feature_app = typer.Typer(help="Manage features")
doc_app = typer.Typer(help="AI-generated feature documentation")
monitor_app = typer.Typer(help="Feature quality monitoring")
cache_app = typer.Typer(help="Manage LLM response cache")
config_app = typer.Typer(help="Configuration management")
job_app = typer.Typer(help="Scheduled job management")
group_app = typer.Typer(help="Feature groups management")
dataset_app = typer.Typer(help="Training dataset building")
dataset_builds_app = typer.Typer(help="Training dataset build audit history")
usage_app = typer.Typer(help="Feature usage analytics")
actions_app = typer.Typer(help="Recommended actions (lifecycle loop)")
online_app = typer.Typer(help="Online feature store read/write commands")
online_materializations_app = typer.Typer(help="Online materialization audit history")
online_materialization_schedules_app = typer.Typer(help="Online materialization schedules")
lineage_app = typer.Typer(help="Lineage management (T1.1)")
lineage_edge_app = typer.Typer(help="Manage individual lineage edges")
lineage_app.add_typer(lineage_edge_app, name="edge")
dataset_app.add_typer(dataset_builds_app, name="builds")
online_app.add_typer(online_materializations_app, name="materializations")
online_materializations_app.add_typer(online_materialization_schedules_app, name="schedules")
demo_app = typer.Typer(help="Demo catalog data: seed and clear")
backup_app = typer.Typer(
    name="backup",
    help="Catalog backup utilities.",
    invoke_without_command=True,
)
app.add_typer(source_app, name="source")
app.add_typer(feature_app, name="feature")
app.add_typer(doc_app, name="doc")
app.add_typer(monitor_app, name="monitor")
app.add_typer(cache_app, name="cache")
app.add_typer(config_app, name="config")
app.add_typer(job_app, name="job")
app.add_typer(group_app, name="group")
app.add_typer(dataset_app, name="dataset")
app.add_typer(usage_app, name="usage")
app.add_typer(actions_app, name="actions")
app.add_typer(online_app, name="online")
app.add_typer(lineage_app, name="lineage")
app.add_typer(demo_app, name="demo")
app.add_typer(backup_app, name="backup")

console = Console()


def _get_db():
    return get_backend()


def _emit(payload: object, render_table: Callable[[], None], *, json_mode: bool) -> None:
    """Print ``payload`` as JSON when ``json_mode`` is true, else call ``render_table``.

    Keeps the existing rich/table rendering path the default while making
    list/get commands scriptable with ``--json``.
    """
    if json_mode:
        print(json.dumps(payload, indent=2, default=str))
        return
    render_table()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _parse_csv_option(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _read_jsonl(path: Path) -> list[object]:
    if not path.exists():
        console.print(f"[red]Input file not found:[/red] {path}")
        raise typer.Exit(1)
    if not path.is_file():
        console.print(f"[red]Input path is not a file:[/red] {path}")
        raise typer.Exit(1)

    rows: list[object] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line_number, raw_line in enumerate(fh, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    console.print(f"[red]Invalid JSONL:[/red] {path}:{line_number}: {exc.msg}")
                    raise typer.Exit(1) from None
    except OSError as exc:
        console.print(f"[red]Could not read input file:[/red] {path}: {exc}")
        raise typer.Exit(1) from None
    return rows


def _read_jsonl_objects(path: Path, *, label: str) -> list[dict[str, Any]]:
    rows = _read_jsonl(path)
    objects: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            console.print(f"[red]Invalid JSONL:[/red] {label} row {index} must be a JSON object")
            raise typer.Exit(1)
        objects.append(row)
    return objects


def _confirm_typing(name: str, impact_summary: str, *, skip: bool = False) -> bool:
    """Type-to-confirm prompt for high-impact destructive ops.

    Prints ``impact_summary`` (a few lines describing the cascade), then asks
    the operator to type the resource name back. Returns True on match, False
    otherwise. ``skip=True`` (passed when ``--yes`` is set) returns True
    without prompting.
    """
    if skip:
        return True
    console.print(impact_summary)
    typed = typer.prompt(f"Type '{name}' to confirm", default="", show_default=False)
    return typed.strip() == name


def _get_llm(use_cache: bool = True):
    """Create an LLM instance. Wraps with caching if use_cache is True."""
    from .llm import create_llm

    settings = load_settings()
    try:
        llm = create_llm(
            backend=settings.llm_backend,
            model=settings.llm_model,
            base_url=settings.llamacpp_url,
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
    db = LocalBackend(DEFAULT_DB)
    db.init_db()
    # Also create cache table
    from .utils.cache import ResponseCache

    ResponseCache(DEFAULT_DB).close()
    db.close()
    console.print(f"[green]Catalog initialized:[/green] {DEFAULT_DB}")


@app.command("quickstart")
def quickstart_cmd(
    target: Path = typer.Option(  # noqa: B008
        Path("./featcat-deploy"),
        "--target",
        "-t",
        help="Directory to write the generated deployment files into.",
    ),
) -> None:
    """Non-interactive setup: write a default deployment directory."""
    from .setup import run_quickstart

    try:
        run_quickstart(target_dir=target, console=console)
    except FileExistsError as e:
        console.print(f"[red]Target is not empty:[/red] {e}")
        raise typer.Exit(1) from None

    console.print(f"\n[bold]Next steps:[/bold]\n  cd {target}\n  docker compose up -d\n  featcat doctor   # verify")


@app.command("setup")
def setup_cmd(
    target: Path = typer.Option(  # noqa: B008
        Path("./featcat-deploy"),
        "--target",
        "-t",
        help="Directory to write the generated deployment files into.",
    ),
) -> None:
    """Interactive setup wizard."""
    from .setup import run_wizard

    try:
        run_wizard(target_dir=target, console=console)
    except FileExistsError as e:
        console.print(f"[red]Target is not empty:[/red] {e}")
        raise typer.Exit(1) from None

    console.print(f"\n[bold]Next steps:[/bold]\n  cd {target}\n  docker compose up -d\n  featcat doctor   # verify")


@app.command()
def add(
    path: str = typer.Argument(help="Path to data file (Parquet/CSV) or directory"),
    name: str | None = typer.Option(None, "--name", "-n", help="Source name (auto from filename if omitted)"),
    owner: str = typer.Option("", "--owner", "-o", help="Owner name"),
    tags: str | None = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
    skip_docs: bool = typer.Option(False, "--skip-docs", help="Skip auto documentation"),
    description: str = typer.Option("", "--desc", "-d", help="Source description"),
    fmt: str | None = typer.Option(None, "--format", help="File format: parquet or csv (auto-detected if omitted)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass LLM response cache"),
) -> None:
    """Add a data source: register, scan, and optionally generate docs in one step."""
    # 1. Auto-generate name from filename
    if name is None:
        name = Path(path).stem

    # 2. Resolve path and storage type
    storage_type = "s3" if is_s3_uri(path) else "local"
    if storage_type == "local":
        resolved = Path(path).resolve()
        if not resolved.exists():
            console.print(f"[red]Path not found:[/red] {path}")
            raise typer.Exit(1)
        path = str(resolved)

    # 3. Register source
    source = DataSource(
        name=name,
        path=path,
        storage_type=storage_type,
        format=fmt or detect_file_format(path),
        description=description,
    )
    db = _get_db()
    try:
        db.add_source(source)
        console.print(f"[green]\u2713[/green] Source [cyan]{name}[/cyan] registered")
    except Exception as e:
        console.print(f"[red]Error registering source:[/red] {e}")
        db.close()
        raise typer.Exit(1) from None

    # 4. Scan source
    console.print(f"[blue]Scanning:[/blue] {path}")
    try:
        columns = scan_source(path)
    except Exception as e:
        console.print(f"[red]Scan failed:[/red] {e}")
        db.close()
        raise typer.Exit(1) from None

    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    registered = 0
    for col in columns:
        feature_name = f"{name}.{col.column_name}"
        feature = Feature(
            name=feature_name,
            data_source_id=source.id,
            column_name=col.column_name,
            dtype=col.dtype,
            stats=col.stats,
            owner=owner,
            tags=tag_list,
        )
        db.upsert_feature(feature)
        registered += 1

    console.print(f"[green]\u2713[/green] {registered} features discovered")

    # 5. Optionally generate docs
    documented = 0
    if not skip_docs:
        llm = _get_llm(use_cache=not no_cache)
        if llm is None:
            console.print("[yellow]Docs skipped (LLM server not running). Run 'featcat doc generate' later.[/yellow]")
        else:
            from .plugins.autodoc import AutodocPlugin

            plugin = AutodocPlugin()
            console.print("[blue]Generating documentation...[/blue]")
            result = plugin.execute(db, llm)
            if result.status == "error":
                console.print(f"[yellow]Doc generation errors:[/yellow] {'; '.join(result.errors)}")
            else:
                documented = result.data.get("documented", 0)
                console.print(f"[green]\u2713[/green] Docs generated for {documented} features")

    db.close()

    # 6. Print summary
    summary_lines = [
        f"[bold]{name}[/bold]",
        f"  Path:     {path}",
        f"  Features: {registered}",
    ]
    if documented:
        summary_lines.append(f"  Docs:     {documented}")
    if owner:
        summary_lines.append(f"  Owner:    {owner}")
    if tag_list:
        summary_lines.append(f"  Tags:     {', '.join(tag_list)}")

    console.print(Panel("\n".join(summary_lines), title="Source Added", border_style="green"))


doctor_app = typer.Typer(
    name="doctor",
    help="System diagnostics: reachability, schema, coverage, deploy state",
    invoke_without_command=True,
)
app.add_typer(doctor_app, name="doctor")


_DOCTOR_GLYPHS = {
    "pass": "[green]✓[/green]",
    "warn": "[yellow]⚠[/yellow]",
    "fail": "[red]✗[/red]",
    "skip": "[dim]⊘[/dim]",
}


def _doctor_status_glyph(status: str) -> str:
    return _DOCTOR_GLYPHS.get(status, " ")


def _doctor_print_group(group_report: GroupReport) -> None:
    console.print(f"\n[bold]▸ {group_report.group.capitalize()}[/bold]")
    if not group_report.checks:
        console.print("  [dim](no checks registered)[/dim]")
        return
    for check in group_report.checks:
        glyph = _doctor_status_glyph(check.status.value)
        console.print(f"  {glyph} {check.name}: {check.detail}")
        if check.resolution and check.status.value in {"warn", "fail"}:
            console.print(f"    [dim]Resolution: {check.resolution}[/dim]")


def _doctor_print_aggregate(agg: AggregateReport) -> None:
    s = agg.summary
    parts = [
        f"[green]{s.get('pass', 0)} pass[/green]",
        f"[yellow]{s.get('warn', 0)} warn[/yellow]",
        f"[red]{s.get('fail', 0)} fail[/red]",
        f"[dim]{s.get('skip', 0)} skip[/dim]",
    ]
    console.print(f"\n[bold]Summary:[/bold] {' · '.join(parts)}")


def _doctor_run(group: str | None, json_output: bool) -> None:
    """Shared body for all doctor invocations."""
    from .diagnostics import aggregate, run_all, run_group

    settings = load_settings()

    # Always-on pre-check: Python version. Lives outside the group system because it
    # can't possibly run if the interpreter is broken anyway, and we never want it
    # parallelized with anything.
    py_ver = sys.version_info
    py_ok = py_ver >= (3, 10)
    if not json_output:
        glyph = "[green]✓[/green]" if py_ok else "[red]✗[/red]"
        console.print(f"{glyph} Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
        if settings.server_url:
            console.print(f"[dim]Mode: remote (FEATCAT_SERVER_URL={settings.server_url})[/dim]")

    reports = run_all(settings=settings) if group is None else {group: run_group(group, settings=settings)}
    agg = aggregate(reports)

    if json_output:
        print(json.dumps(agg.model_dump(mode="json"), indent=2))
        if agg.exit_code or not py_ok:
            raise typer.Exit(agg.exit_code or 1)
        return

    for name in sorted(reports):
        _doctor_print_group(reports[name])
    _doctor_print_aggregate(agg)
    exit_code = agg.exit_code or (0 if py_ok else 1)
    if exit_code:
        raise typer.Exit(exit_code)


@doctor_app.callback()
def doctor_root(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON envelope to stdout"),
) -> None:
    """Run every diagnostic group when invoked without a subcommand."""
    if ctx.invoked_subcommand is not None:
        return
    _doctor_run(group=None, json_output=json_output)


@doctor_app.command("deploy")
def doctor_deploy(
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON envelope to stdout"),
) -> None:
    """Git, Docker, compose validity."""
    _doctor_run(group="deploy", json_output=json_output)


@doctor_app.command("db")
def doctor_db(
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON envelope to stdout"),
) -> None:
    """DB reachability, version, migrations, catalog stats."""
    _doctor_run(group="db", json_output=json_output)


@doctor_app.command("llm")
def doctor_llm(
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON envelope to stdout"),
) -> None:
    """LLM reachability, model identity, context size, slot availability."""
    _doctor_run(group="llm", json_output=json_output)


@doctor_app.command("network")
def doctor_network(
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON envelope to stdout"),
) -> None:
    """TCP probes, proxy correctness, S3 endpoint."""
    _doctor_run(group="network", json_output=json_output)


@doctor_app.command("data")
def doctor_data(
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON envelope to stdout"),
) -> None:
    """Sources, stats coverage, doc coverage, drift recency, lineage coverage."""
    _doctor_run(group="data", json_output=json_output)


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
    documented = doc_stats["documented"]
    total = doc_stats["total_features"]
    console.print(f"  Doc coverage: [{cov_color}]{cov:.1f}%[/{cov_color}] ({documented}/{total})")

    checked = report.get("checked", 0)
    healthy = report.get("healthy", 0)
    warnings = report.get("warnings", 0)
    critical = report.get("critical", 0)

    if checked > 0:
        console.print(
            f"  Monitoring:   [green]{healthy}[/green] healthy,"
            f" [yellow]{warnings}[/yellow] warnings,"
            f" [red]{critical}[/red] critical"
        )
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
            feat_count = sum(1 for f in features if f.name.startswith(s.name + "."))
            table.add_row(s.name, s.storage_type, str(feat_count))
        console.print(table)

    console.print()


@app.command(name="export")
def export_catalog(
    fmt: str = typer.Option("json", "--format", help="Output format: json, csv, markdown, parquet"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    group: str | None = typer.Option(None, "--group", "-g", help="Export data from a feature group"),
    features: str | None = typer.Option(None, "--features", "-f", help="Comma-separated feature specs to export"),
    join_on: str | None = typer.Option(None, "--join-on", help="Join column for multi-source export"),
) -> None:
    """Export catalog metadata or feature data.

    Without --group/--features: exports catalog metadata (json/csv/markdown).
    With --group or --features: exports actual parquet/csv data from source files.
    """
    # Data export mode
    if group or features:
        _export_data(group=group, features=features, output=output, fmt=fmt, join_on=join_on)
        return

    # Metadata export mode (original behavior)
    db = _get_db()
    all_features = db.list_features()
    db.close()

    if fmt == "json":
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
            for f in all_features
        ]
        text = json.dumps(data, indent=2, default=str)

    elif fmt == "csv":
        lines = ["name,column_name,dtype,tags,owner,null_ratio"]
        for f in all_features:
            tags = "|".join(f.tags)
            null_ratio = f.stats.get("null_ratio", "")
            lines.append(f"{f.name},{f.column_name},{f.dtype},{tags},{f.owner},{null_ratio}")
        text = "\n".join(lines)

    elif fmt == "markdown":
        lines = ["# Feature Catalog Export", ""]
        lines.append("| Name | Dtype | Tags | Owner | Null Ratio |")
        lines.append("|------|-------|------|-------|------------|")
        for f in all_features:
            tags = ", ".join(f.tags) if f.tags else ""
            nr = f.stats.get("null_ratio", "")
            nr_str = f"{nr:.1%}" if isinstance(nr, int | float) else str(nr)
            lines.append(f"| {f.name} | {f.dtype} | {tags} | {f.owner} | {nr_str} |")
        text = "\n".join(lines)
    else:
        console.print(f"[red]Unknown format:[/red] {fmt}. Use json, csv, or markdown.")
        raise typer.Exit(1)

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text)
        console.print(f"[green]Exported to:[/green] {output}")
    else:
        console.print(text)


def _export_data(
    group: str | None,
    features: str | None,
    output: str | None,
    fmt: str,
    join_on: str | None,
) -> None:
    """Export actual feature data from source parquet files."""
    from .catalog.exporter import export_features

    db = _get_db()

    # Resolve feature specs
    specs: list[str] = []
    if group:
        grp = db.get_group_by_name(group)
        if grp is None:
            db.close()
            console.print(f"[red]Group not found:[/red] {group}")
            raise typer.Exit(1)
        members = db.list_group_members(grp.id)
        specs = [m.name for m in members]
        console.print(f"Exporting [bold]{len(specs)}[/bold] features from group [cyan]{group}[/cyan]...")
    elif features:
        specs = [s.strip() for s in features.split(",") if s.strip()]
        console.print(f"Exporting [bold]{len(specs)}[/bold] features...")

    if not specs:
        db.close()
        console.print("[red]No features to export.[/red]")
        raise typer.Exit(1)

    # Default format for data export
    if fmt in ("json", "markdown"):
        fmt = "parquet"

    try:
        result = export_features(
            feature_specs=specs,
            db=db,
            output_path=output,
            join_on=join_on,
            fmt=fmt,
        )
    except ValueError as e:
        db.close()
        console.print(f"[red]Export failed:[/red] {e}")
        raise typer.Exit(1) from e
    finally:
        db.close()

    for src in result.sources_used:
        console.print(f"  [green]\u2713[/green] {src}")
    if result.join_column:
        console.print(f"Join column: [cyan]{result.join_column}[/cyan]")
    for w in result.warnings:
        console.print(f"  [yellow]\u26a0[/yellow] {w}")

    size_mb = result.file_size / (1024 * 1024)
    console.print(f"\n[green]Export complete:[/green] {result.output_path}")
    console.print(f"Features: {result.feature_count}  |  Rows: {result.row_count:,}  |  Size: {size_mb:.1f} MB")
    console.print("\n[dim]Python snippet:[/dim]")
    console.print(f"[cyan]{result.code_snippet}[/cyan]")


# =========================================================================
# Dataset commands
# =========================================================================


@dataset_app.command("build")
def dataset_build(
    entities: str = typer.Option(..., "--entities", help="Local parquet entity dataframe path"),
    source: str | None = typer.Option(None, "--source", help="Local parquet source dataframe path"),
    source_name: str | None = typer.Option(None, "--source-name", help="Registered DataSource name"),
    entity_key: str | None = typer.Option(None, "--entity-key", help="Entity/join key column"),
    entity_timestamp: str | None = typer.Option(
        None,
        "--entity-timestamp",
        help="Entity timestamp column",
    ),
    source_timestamp: str | None = typer.Option(
        None,
        "--source-timestamp",
        help="Source event timestamp column",
    ),
    features: str = typer.Option(..., "--features", help="Comma-separated feature columns"),
    output: str | None = typer.Option(None, "--output", "-o", help="Local parquet output path"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Build a local point-in-time training dataset."""
    from .catalog.dataset_audit import record_dataset_build_audit, record_dataset_build_error_audit
    from .catalog.training_dataset import (
        TrainingDatasetBuildResult,
        TrainingDatasetValidationIssue,
        build_training_dataset,
        training_dataset_result_to_dict,
    )

    data_source = None
    db = None
    parsed_features = _parse_csv_option(features)
    try:
        db = _get_db()
        db.init_db()
        if source_name:
            data_source = db.get_source_by_name(source_name)
            if data_source is None:
                result = TrainingDatasetBuildResult(
                    is_valid=False,
                    errors=[
                        TrainingDatasetValidationIssue(
                            code="source_not_found",
                            message=f"DataSource not found: {source_name}",
                            field="source_name",
                        )
                    ],
                    entity_df_path=entities,
                    source_path=source,
                    entity_key=entity_key,
                    entity_timestamp_column=entity_timestamp,
                    source_event_timestamp_column=source_timestamp,
                    feature_columns=parsed_features,
                    feature_count=len(parsed_features),
                )
            else:
                try:
                    result = build_training_dataset(
                        entity_df_path=entities,
                        source_path=source,
                        entity_key=entity_key,
                        entity_timestamp_column=entity_timestamp,
                        source_event_timestamp_column=source_timestamp,
                        feature_columns=parsed_features,
                        output_path=output,
                        data_source=data_source,
                    )
                except Exception as exc:
                    record_dataset_build_error_audit(
                        db,
                        entity_df_path=entities,
                        source_path=source,
                        source_name=source_name,
                        output_path=output,
                        entity_key=entity_key,
                        entity_timestamp_column=entity_timestamp,
                        source_event_timestamp_column=source_timestamp,
                        feature_columns=parsed_features,
                        error=exc,
                        actor=resolve_user(),
                    )
                    raise
        else:
            try:
                result = build_training_dataset(
                    entity_df_path=entities,
                    source_path=source,
                    entity_key=entity_key,
                    entity_timestamp_column=entity_timestamp,
                    source_event_timestamp_column=source_timestamp,
                    feature_columns=parsed_features,
                    output_path=output,
                )
            except Exception as exc:
                record_dataset_build_error_audit(
                    db,
                    entity_df_path=entities,
                    source_path=source,
                    source_name=source_name,
                    output_path=output,
                    entity_key=entity_key,
                    entity_timestamp_column=entity_timestamp,
                    source_event_timestamp_column=source_timestamp,
                    feature_columns=parsed_features,
                    error=exc,
                    actor=resolve_user(),
                )
                raise
        record_dataset_build_audit(
            db,
            result=result,
            source_name=source_name,
            actor=resolve_user(),
            requested_source_path=source,
            requested_output_path=output,
        )
    finally:
        if db is not None:
            db.close()

    payload = training_dataset_result_to_dict(result)
    if json_output:
        print(json.dumps(payload, indent=2, default=str))
    elif result.is_valid:
        console.print(f"[green]Dataset built:[/green] {result.row_count:,} rows")
        console.print(f"Features: {result.feature_count}")
        if result.output_path:
            console.print(f"Output: [cyan]{result.output_path}[/cyan]")
        if result.unresolved_row_count:
            console.print(f"Unresolved rows: [yellow]{result.unresolved_row_count}[/yellow]")
    else:
        console.print("[red]Dataset build failed:[/red]")
        for error in result.errors:
            field = f" ({error.field})" if error.field else ""
            console.print(f"  [red]{error.code}[/red]{field}: {error.message}")

    if not result.is_valid:
        raise typer.Exit(1)


@dataset_builds_app.command("list")
def dataset_builds_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum rows to return"),
    status: str | None = typer.Option(
        None,
        "--status",
        help="Filter by status: success, validation_failed, or error",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """List recent training dataset build audit records."""
    db = _get_db()
    try:
        rows = db.list_dataset_build_audits(limit=limit, status=status)
    finally:
        db.close()

    payload = [row.model_dump(mode="json") if hasattr(row, "model_dump") else row for row in rows]
    if json_output:
        print(json.dumps(payload, indent=2, default=str))
        return

    table = Table(title="Training Dataset Builds")
    table.add_column("Created")
    table.add_column("Status")
    table.add_column("Rows", justify="right")
    table.add_column("Features", justify="right")
    table.add_column("Output")
    for row in rows:
        created_at = getattr(row, "created_at", "")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        table.add_row(
            str(created_at),
            row.status,
            str(row.row_count),
            str(row.feature_count),
            row.output_path or "",
        )
    console.print(table)


# =========================================================================
# Online store commands
# =========================================================================


@online_app.command("write")
def online_write(
    input_path: Path = typer.Option(  # noqa: B008
        ...,
        "--input",
        "-i",
        help="JSONL file with online feature write rows",
    ),
    project: str = typer.Option("", "--project", help="Project namespace"),
    feature_view: str = typer.Option("", "--feature-view", help="Feature view namespace"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Write online feature values from a JSONL file."""
    rows = _read_jsonl_objects(input_path, label="write")
    try:
        writes = [OnlineFeatureWrite.model_validate(row) for row in rows]
    except Exception as exc:
        console.print(f"[red]Invalid online write row:[/red] {exc}")
        raise typer.Exit(1) from None

    db = _get_db()
    try:
        db.init_db()
        result = db.write_online_features(writes, project=project, feature_view=feature_view)
    finally:
        db.close()

    payload = result.model_dump(mode="json")
    if json_output:
        print(json.dumps(payload, indent=2, default=str))
        return

    console.print(
        "[green]Online write complete:[/green] "
        f"requested={result.requested} written={result.written} "
        f"skipped_older={result.skipped_older} "
        f"skipped_same_timestamp={result.skipped_same_timestamp} "
        f"errors={len(result.errors)}"
    )


@online_app.command("get")
def online_get(
    entities: Path = typer.Option(  # noqa: B008
        ...,
        "--entities",
        "-e",
        help="JSONL file with entity key objects",
    ),
    features: str = typer.Option(..., "--features", "-f", help="Comma-separated feature refs"),
    project: str = typer.Option("", "--project", help="Project namespace"),
    feature_view: str = typer.Option("", "--feature-view", help="Feature view namespace"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Read online feature values for entity keys from a JSONL file."""
    entity_keys = _read_jsonl_objects(entities, label="entity")
    feature_refs = _parse_csv_option(features)
    if not feature_refs:
        console.print("[red]No feature refs provided:[/red] --features must include at least one feature")
        raise typer.Exit(1)

    db = _get_db()
    try:
        db.init_db()
        result = db.get_online_features(
            entity_keys=entity_keys,
            feature_refs=feature_refs,
            project=project,
            feature_view=feature_view,
        )
    finally:
        db.close()

    payload = result.model_dump(mode="json")
    if json_output:
        print(json.dumps(payload, indent=2, default=str))
        return

    found_count = sum(1 for row in result.rows for metadata in row.metadata.values() if metadata.found)
    requested_count = len(result.rows) * len(feature_refs)
    console.print(
        "[green]Online read complete:[/green] "
        f"entities={len(result.rows)} features={len(feature_refs)} found={found_count}/{requested_count}"
    )


@online_app.command("materialize")
def online_materialize(
    source: str = typer.Option(..., "--source", help="Registered DataSource name"),
    features: str = typer.Option(..., "--features", "-f", help="Comma-separated feature columns"),
    project: str = typer.Option("", "--project", help="Project namespace"),
    feature_view: str = typer.Option("", "--feature-view", help="Feature view namespace"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Materialize latest offline feature values from a registered source."""
    from .catalog.materialization import materialize_latest_from_source
    from .catalog.materialization_audit import record_materialization_audit, record_materialization_error_audit

    feature_columns = _parse_csv_option(features)
    db = _get_db()
    try:
        db.init_db()
        try:
            result = materialize_latest_from_source(
                db,
                source_name=source,
                feature_columns=feature_columns,
                project=project,
                feature_view=feature_view,
            )
        except Exception as exc:
            record_materialization_error_audit(
                db,
                source_name=source,
                project=project,
                feature_view=feature_view,
                feature_columns=feature_columns,
                error=exc,
                actor=resolve_user(),
            )
            console.print(f"[red]Online materialization error:[/red] {exc}")
            raise typer.Exit(1) from None
        record_materialization_audit(db, result=result, actor=resolve_user())
    finally:
        db.close()

    payload = asdict(result)
    if json_output:
        print(json.dumps(payload, indent=2, default=str))
    elif result.is_valid:
        console.print(
            "[green]Online materialization complete:[/green] "
            f"source={result.source_name} entities={result.entity_count} "
            f"features={result.feature_count} requested={result.requested} "
            f"written={result.written} skipped_older={result.skipped_older} "
            f"skipped_same_timestamp={result.skipped_same_timestamp}"
        )
    else:
        console.print("[red]Online materialization failed:[/red]")
        for error in result.errors:
            field = f" ({error.field})" if error.field else ""
            console.print(f"  [red]{error.code}[/red]{field}: {error.message}")

    if not result.is_valid:
        raise typer.Exit(1)


@app.command("materialize")
def materialize(
    source: str = typer.Option(..., "--source", help="Registered DataSource name"),
    features: str = typer.Option(..., "--features", "-f", help="Comma-separated feature columns"),
    project: str = typer.Option("", "--project", help="Project namespace"),
    feature_view: str = typer.Option("", "--feature-view", help="Feature view namespace"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Materialize latest offline feature values from a registered source to the online store."""
    online_materialize(
        source=source,
        features=features,
        project=project,
        feature_view=feature_view,
        json_output=json_output,
    )


@online_materializations_app.command("list")
def online_materializations_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum rows to return"),
    status: str | None = typer.Option(
        None,
        "--status",
        help="Filter by status: success, validation_failed, or error",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """List recent online materialization audit records."""
    db = _get_db()
    try:
        rows = db.list_materialization_audits(limit=limit, status=status)
    finally:
        db.close()

    payload = [row.model_dump(mode="json") if hasattr(row, "model_dump") else row for row in rows]
    if json_output:
        print(json.dumps(payload, indent=2, default=str))
        return

    table = Table(title="Online Materializations")
    table.add_column("Created")
    table.add_column("Status")
    table.add_column("Source")
    table.add_column("Entities", justify="right")
    table.add_column("Features", justify="right")
    table.add_column("Written", justify="right")
    for row in rows:
        created_at = getattr(row, "created_at", "")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        table.add_row(
            str(created_at),
            row.status,
            row.source_name,
            str(row.entity_count),
            str(row.feature_count),
            str(row.written),
        )
    console.print(table)


@online_materialization_schedules_app.command("add")
def online_materialization_schedule_add(
    name: str = typer.Option(..., "--name", help="Unique schedule name"),
    source: str = typer.Option(..., "--source", help="Registered DataSource name"),
    features: str = typer.Option(..., "--features", "-f", help="Comma-separated feature columns"),
    interval_seconds: int = typer.Option(..., "--interval-seconds", help="Interval between runs in seconds"),
    project: str = typer.Option("", "--project", help="Project namespace"),
    feature_view: str = typer.Option("", "--feature-view", help="Feature view namespace"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Create an interval materialization schedule."""
    feature_columns = _parse_csv_option(features)
    if not feature_columns:
        console.print("[red]No feature columns provided:[/red] --features must include at least one feature column")
        raise typer.Exit(1)

    db = _get_db()
    try:
        db.init_db()
        schedule = db.create_materialization_schedule(
            name=name,
            source_name=source,
            feature_columns=feature_columns,
            interval_seconds=interval_seconds,
            project=project,
            feature_view=feature_view,
            actor=resolve_user(),
        )
    except Exception as exc:
        console.print(f"[red]Could not create materialization schedule:[/red] {exc}")
        raise typer.Exit(1) from None
    finally:
        db.close()

    payload = schedule.model_dump(mode="json") if hasattr(schedule, "model_dump") else schedule
    if json_output:
        print(json.dumps(payload, indent=2, default=str))
        return

    console.print(
        "[green]Materialization schedule created:[/green] "
        f"name={schedule.name} source={schedule.source_name} "
        f"features={len(schedule.feature_columns)} interval_seconds={schedule.interval_seconds}"
    )


@online_materialization_schedules_app.command("list")
def online_materialization_schedules_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum schedules to return"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """List materialization schedules."""
    db = _get_db()
    try:
        db.init_db()
        rows = db.list_materialization_schedules(limit=limit)
    finally:
        db.close()

    payload = [row.model_dump(mode="json") if hasattr(row, "model_dump") else row for row in rows]
    if json_output:
        print(json.dumps(payload, indent=2, default=str))
        return

    table = Table(title="Online Materialization Schedules")
    table.add_column("Name")
    table.add_column("Enabled")
    table.add_column("Source")
    table.add_column("Interval", justify="right")
    table.add_column("Next Run")
    for row in rows:
        next_run_at = row.next_run_at.isoformat() if row.next_run_at else ""
        table.add_row(
            row.name,
            "yes" if row.enabled else "no",
            row.source_name,
            str(row.interval_seconds),
            next_run_at,
        )
    console.print(table)


@online_materialization_schedules_app.command("enable")
def online_materialization_schedule_enable(
    schedule: str = typer.Argument(..., help="Schedule id or name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Enable a materialization schedule."""
    _set_online_materialization_schedule_enabled(schedule, True, json_output=json_output)


@online_materialization_schedules_app.command("disable")
def online_materialization_schedule_disable(
    schedule: str = typer.Argument(..., help="Schedule id or name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Disable a materialization schedule."""
    _set_online_materialization_schedule_enabled(schedule, False, json_output=json_output)


def _set_online_materialization_schedule_enabled(schedule: str, enabled: bool, *, json_output: bool) -> None:
    db = _get_db()
    try:
        db.init_db()
        row = db.set_materialization_schedule_enabled(schedule, enabled)
    finally:
        db.close()

    if row is None:
        console.print(f"[red]Materialization schedule not found:[/red] {schedule}")
        raise typer.Exit(1)

    payload = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
    if json_output:
        print(json.dumps(payload, indent=2, default=str))
        return

    state = "enabled" if enabled else "disabled"
    console.print(f"[green]Materialization schedule {state}:[/green] {row.name}")


@online_materializations_app.command("run-once")
def online_materializations_run_once(
    runner_id: str = typer.Option("local", "--runner-id", help="Runner id used for schedule leases"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum due schedules to claim"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Claim and run due materialization schedules once."""
    from .catalog.materialization_scheduler import run_due_materialization_schedules

    db = _get_db()
    try:
        db.init_db()
        result = run_due_materialization_schedules(db, runner_id=runner_id, limit=limit)
    finally:
        db.close()

    payload = asdict(result)
    if json_output:
        print(json.dumps(payload, indent=2, default=str))
        return

    status_counts: dict[str, int] = {}
    for run in result.runs:
        status_counts[run.status] = status_counts.get(run.status, 0) + 1
    summary = " ".join(f"{status}={count}" for status, count in sorted(status_counts.items()))
    console.print(
        "[green]Materialization scheduler run complete:[/green] "
        f"runner_id={result.runner_id} claimed={result.claimed}" + (f" {summary}" if summary else "")
    )


@online_materializations_app.command("loop")
def online_materializations_loop(
    runner_id: str = typer.Option("local", "--runner-id", help="Runner id used for schedule leases"),
    poll_interval: float = typer.Option(60.0, "--poll-interval", help="Seconds to sleep between iterations"),
    lease_seconds: int = typer.Option(1800, "--lease-seconds", help="Seconds before claimed schedule leases expire"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum due schedules to claim per iteration"),
    max_iterations: int | None = typer.Option(
        None,
        "--max-iterations",
        help="Stop after this many iterations; omit to run until interrupted",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON per iteration"),
) -> None:
    """Continuously claim and run due materialization schedules."""
    from .catalog.materialization_scheduler import run_due_materialization_schedules

    if poll_interval <= 0:
        console.print("[red]Invalid poll interval:[/red] --poll-interval must be greater than 0")
        raise typer.Exit(1)
    if lease_seconds <= 0:
        console.print("[red]Invalid lease seconds:[/red] --lease-seconds must be greater than 0")
        raise typer.Exit(1)
    if max_iterations is not None and max_iterations <= 0:
        console.print("[red]Invalid max iterations:[/red] --max-iterations must be greater than 0")
        raise typer.Exit(1)

    db = _get_db()
    iteration = 0
    try:
        db.init_db()
        while max_iterations is None or iteration < max_iterations:
            iteration += 1
            result = run_due_materialization_schedules(
                db,
                runner_id=runner_id,
                lease_seconds=lease_seconds,
                limit=limit,
            )
            payload = {"iteration": iteration, **asdict(result)}
            if json_output:
                print(json.dumps(payload, default=str), flush=True)
            else:
                status_counts: dict[str, int] = {}
                for run in result.runs:
                    status_counts[run.status] = status_counts.get(run.status, 0) + 1
                summary = " ".join(f"{status}={count}" for status, count in sorted(status_counts.items()))
                console.print(
                    "[green]Materialization scheduler iteration complete:[/green] "
                    f"iteration={iteration} runner_id={result.runner_id} claimed={result.claimed}"
                    + (f" {summary}" if summary else "")
                )
            if max_iterations is not None and iteration >= max_iterations:
                break
            _sleep(poll_interval)
    finally:
        db.close()


# =========================================================================
# Source commands
# =========================================================================


@source_app.command("add")
def source_add(
    name: str = typer.Argument(help="Unique name for this data source"),
    path: str = typer.Argument(help="Local path or s3:// URI"),
    fmt: str = typer.Option("parquet", "--format", help="File format: parquet or csv"),
    description: str = typer.Option("", help="Optional description"),
    entity_key: str | None = typer.Option(None, "--entity-key", help="Entity/join key column for offline joins"),
    event_timestamp_column: str | None = typer.Option(
        None,
        "--event-timestamp-column",
        help="Event timestamp column for future point-in-time joins",
    ),
    created_timestamp_column: str | None = typer.Option(
        None,
        "--created-timestamp-column",
        help="Created timestamp column used as a future point-in-time tie-breaker",
    ),
) -> None:
    """Register a new data source."""
    storage_type = "s3" if path.startswith("s3://") else "local"

    if storage_type == "local":
        path = str(Path(path).resolve())

    source = DataSource(
        name=name,
        path=path,
        storage_type=storage_type,
        format=fmt,
        description=description,
        entity_key=entity_key,
        event_timestamp_column=event_timestamp_column,
        created_timestamp_column=created_timestamp_column,
    )
    db = _get_db()
    try:
        db.add_source(source)
        console.print(f"[green]Source added:[/green] {name} -> {path}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None
    finally:
        db.close()


@source_app.command("list")
def source_list(
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON to stdout instead of a table"),
) -> None:
    """List all registered data sources."""
    db = _get_db()
    sources = db.list_sources()
    db.close()

    payload = [
        {
            "name": s.name,
            "path": s.path,
            "storage_type": s.storage_type,
            "format": s.format,
            "description": s.description,
            "entity_key": s.entity_key,
            "event_timestamp_column": s.event_timestamp_column,
            "created_timestamp_column": s.created_timestamp_column,
        }
        for s in sources
    ]

    def _render() -> None:
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

    _emit(payload, _render, json_mode=json_output)


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
        raise typer.Exit(1) from None

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
    console.print(f"[green]Done:[/green] {registered} features registered from [cyan]{name}[/cyan]")


@source_app.command("rm")
def source_rm(
    name: str = typer.Argument(help="Source name to remove"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
) -> None:
    """Hard-delete a source and cascade-remove its features and dependents.

    Mirrors ``DELETE /api/sources/{name}``: every dependent row (features,
    docs, baselines, monitoring checks, usage logs, group memberships,
    lineage edges, action items) is cleaned up. When the source has more
    than 10 features the prompt requires typing the source name back to
    confirm; ``--yes`` skips both prompts.
    """
    db = _get_db()
    try:
        if db.get_source_by_name(name) is None:
            console.print(f"[red]Source not found:[/red] {name}")
            raise typer.Exit(1)

        impact = db.get_source_impact(name)
        features_count = int(impact.get("features_count", 0))
        groups = impact.get("groups", [])
        groups_count = len(groups)

        impact_summary = (
            f"[yellow]Source '{name}' has {features_count} feature(s)"
            f" across {groups_count} group(s).[/yellow]\n"
            "[yellow]Deleting will cascade-remove all features, docs, baselines,"
            " monitoring checks, usage logs, group memberships, and lineage edges.[/yellow]"
        )

        if features_count > 10:
            if not _confirm_typing(name, impact_summary, skip=yes):
                console.print("[dim]Aborted.[/dim]")
                raise typer.Exit(0)
        elif not yes:
            console.print(impact_summary)
            if not typer.confirm(f"Delete source '{name}'?"):
                console.print("[dim]Aborted.[/dim]")
                raise typer.Exit(0)

        try:
            removed = db.delete_source(name)
        except KeyError:
            console.print(f"[red]Source not found:[/red] {name}")
            raise typer.Exit(1) from None
        console.print(
            f"[green]Removed source '{name}'[/green] ({removed} feature(s),"
            f" {groups_count} group membership(s) cleaned up)"
        )
    finally:
        db.close()


@source_app.command("update")
def source_update(
    name: str = typer.Argument(help="Source name"),
    description: str | None = typer.Option(None, "--description", "-d", help="New description"),
    fmt: str | None = typer.Option(None, "--format", help="New file format (parquet|csv)"),
    entity_key: str | None = typer.Option(None, "--entity-key", help="Entity/join key column for offline joins"),
    event_timestamp_column: str | None = typer.Option(
        None,
        "--event-timestamp-column",
        help="Event timestamp column for future point-in-time joins",
    ),
    created_timestamp_column: str | None = typer.Option(
        None,
        "--created-timestamp-column",
        help="Created timestamp column used as a future point-in-time tie-breaker",
    ),
) -> None:
    """Update mutable fields on a source (description, format, join metadata).

    Mirrors ``PATCH /api/sources/{name}``. ``name``, ``path``, and
    ``storage_type`` are immutable — rename is intentionally not supported.
    """
    if (
        description is None
        and fmt is None
        and entity_key is None
        and event_timestamp_column is None
        and created_timestamp_column is None
    ):
        console.print("[red]Nothing to update.[/red] Pass --description, --format, or a join metadata option.")
        raise typer.Exit(1)

    db = _get_db()
    try:
        if db.get_source_by_name(name) is None:
            console.print(f"[red]Source not found:[/red] {name}")
            raise typer.Exit(1)
        db.update_source(
            name,
            description=description,
            format=fmt,
            entity_key=entity_key,
            event_timestamp_column=event_timestamp_column,
            created_timestamp_column=created_timestamp_column,
        )
        console.print(f"[green]Updated source:[/green] {name}")
    finally:
        db.close()


# =========================================================================
# Feature commands
# =========================================================================


@feature_app.command("list")
def feature_list(
    source: str | None = typer.Option(None, "--source", "-s", help="Filter by source name"),
    health_grade: str | None = typer.Option(None, "--health-grade", help="Filter by health grade (A/B/C/D)"),
    drift_status: str | None = typer.Option(
        None, "--drift-status", help="Filter by drift status (healthy/warning/critical)"
    ),
    has_doc: bool | None = typer.Option(None, "--has-doc/--no-doc", help="Only show features with/without docs"),
    owner: str | None = typer.Option(None, "--owner", help="Filter by owner"),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag"),
    dtype: str | None = typer.Option(None, "--dtype", help="Filter by dtype"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON to stdout instead of a table"),
) -> None:
    """List features with rich filtering matching the API."""
    from .catalog.health import compute_health_score
    from .server.routes.features import _bulk_health_data

    db = _get_db()
    features = db.list_features(source_name=source)

    enriched: list[dict] = []
    needs_health = any([health_grade, drift_status, has_doc is not None])
    if needs_health:
        all_docs, drift_map, usage_map = _bulk_health_data(db)
    else:
        all_docs, drift_map, usage_map = {}, {}, {}

    for f in features:
        d: dict = {
            "name": f.name,
            "column": f.column_name,
            "dtype": f.dtype,
            "tags": f.tags or [],
            "owner": f.owner or "",
            "stats": f.stats or {},
        }
        if needs_health:
            usage = usage_map.get(f.id, {"views": 0, "queries": 0})
            h = compute_health_score(
                has_doc=f.id in all_docs,
                has_hints=bool(f.generation_hints),
                drift_status=drift_map.get(f.id),
                views_30d=usage["views"],
                queries_30d=usage["queries"],
            )
            d["health_grade"] = h["grade"]
            d["health_score"] = h["score"]
            d["has_doc"] = f.id in all_docs
            d["drift_status"] = drift_map.get(f.id, "healthy")
        enriched.append(d)
    db.close()

    if owner:
        enriched = [d for d in enriched if d["owner"] == owner]
    if tag:
        enriched = [d for d in enriched if tag in (d["tags"] or [])]
    if dtype:
        enriched = [d for d in enriched if d["dtype"] == dtype]
    if health_grade:
        enriched = [d for d in enriched if d.get("health_grade") == health_grade]
    if drift_status:
        enriched = [d for d in enriched if d.get("drift_status") == drift_status]
    if has_doc is True:
        enriched = [d for d in enriched if d.get("has_doc")]
    elif has_doc is False:
        enriched = [d for d in enriched if not d.get("has_doc")]

    def _render() -> None:
        if not enriched:
            console.print("[dim]No features match these filters[/dim]")
            return

        table = Table(title=f"Features ({len(enriched)})")
        table.add_column("Name", style="cyan")
        table.add_column("Column")
        table.add_column("Dtype")
        show_health = "health_grade" in enriched[0]
        if show_health:
            table.add_column("Grade")
            table.add_column("Drift")
            table.add_column("Doc", justify="center")
        table.add_column("Owner")
        table.add_column("Tags")
        table.add_column("Nulls", justify="right")

        for d in enriched:
            null_ratio = d["stats"].get("null_ratio", "")
            null_str = f"{null_ratio:.1%}" if isinstance(null_ratio, int | float) else str(null_ratio)
            tags_str = ", ".join(d["tags"]) if d["tags"] else ""
            row = [d["name"], d["column"], d["dtype"]]
            if show_health:
                row += [
                    d.get("health_grade", "-"),
                    d.get("drift_status", "-"),
                    "yes" if d.get("has_doc") else "-",
                ]
            row += [d["owner"] or "-", tags_str, null_str]
            table.add_row(*row)

        console.print(table)

    _emit(enriched, _render, json_mode=json_output)


@feature_app.command("info")
def feature_info(
    name: str = typer.Argument(help="Feature name (e.g. source.column)"),
) -> None:
    """Show detailed information about a feature."""
    db = _get_db()
    feature = db.get_feature_by_name(name)

    if feature is None:
        db.close()
        console.print(f"[red]Feature not found:[/red] {name}")
        raise typer.Exit(1)

    log_feature_usage(db, feature.id, "view")

    console.print(f"\n[bold cyan]{feature.name}[/bold cyan]")
    console.print(f"  Column:      {feature.column_name}")
    console.print(f"  Dtype:       {feature.dtype}")
    console.print(f"  Description: {feature.description or '(none)'}")
    console.print(f"  Owner:       {feature.owner or '(none)'}")
    console.print(f"  Tags:        {', '.join(feature.tags) if feature.tags else '(none)'}")
    console.print(f"  Source ID:   {feature.data_source_id}")
    console.print(f"  Created:     {feature.created_at}")
    console.print(f"  Updated:     {feature.updated_at}")

    # Show definition if set
    defn = db.get_feature_definition(feature.id)
    if defn:
        console.print(f"\n  [bold]Definition ({defn['definition_type']}):[/bold]")
        console.print(f"    {defn['definition']}")

    if feature.stats:
        console.print("\n  [bold]Statistics:[/bold]")
        for k, v in feature.stats.items():
            console.print(f"    {k}: {v}")

    db.close()
    console.print()


@feature_app.command("rm")
def feature_rm(
    name: str = typer.Argument(help="Feature name (source.column)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Hard-delete a feature and cascade-remove its docs, baselines, checks,
    usage logs, group memberships, lineage edges, and version history.

    Cascade contract matches ``LocalBackend.bulk_delete_features``.
    """
    db = _get_db()
    try:
        feature = db.get_feature_by_name(name)
        if feature is None:
            console.print(f"[red]Feature not found:[/red] {name}")
            raise typer.Exit(1)

        if not yes and not typer.confirm(f"Delete feature '{name}'?"):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

        removed = db.bulk_delete_features([feature.id])
        if removed == 0:
            console.print(f"[red]Delete failed for:[/red] {name}")
            raise typer.Exit(1)
        console.print(f"[green]Removed feature:[/green] {name}")
    finally:
        db.close()


@feature_app.command("update")
def feature_update(
    name: str = typer.Argument(help="Feature name (source.column)"),
    owner: str | None = typer.Option(None, "--owner", help="New owner"),
    description: str | None = typer.Option(None, "--description", "-d", help="New description"),
) -> None:
    """Update mutable fields on a feature (owner, description).

    Mirrors ``PATCH /api/features/by-name`` (excluding ``tags``, which has
    its own dedicated ``featcat feature tag`` command).
    """
    if owner is None and description is None:
        console.print("[red]Nothing to update.[/red] Pass --owner and/or --description.")
        raise typer.Exit(1)

    db = _get_db()
    try:
        feature = db.get_feature_by_name(name)
        if feature is None:
            console.print(f"[red]Feature not found:[/red] {name}")
            raise typer.Exit(1)
        updates: dict[str, str] = {}
        if owner is not None:
            updates["owner"] = owner
        if description is not None:
            updates["description"] = description
        db.update_feature_metadata(feature.id, **updates)
        console.print(f"[green]Updated feature:[/green] {name}")
    finally:
        db.close()


def _resolve_specs(db, specs: list[str]) -> tuple[list[str], list[str]]:
    """Resolve ``source.column`` specs to feature IDs.

    Mirrors the REST bulk endpoints' all-or-nothing validation contract:
    caller should exit with an error if ``invalid`` is non-empty.
    """
    ids: list[str] = []
    invalid: list[str] = []
    for spec in specs:
        feature = db.get_feature_by_name(spec)
        if feature is None:
            invalid.append(spec)
        else:
            ids.append(feature.id)
    return ids, invalid


def _read_specs_file(path: Path) -> list[str]:
    """Read a newline-delimited specs file. Blank lines and ``#`` comments are skipped."""
    raw = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in raw if line.strip() and not line.lstrip().startswith("#")]


@feature_app.command("bulk-tag")
def feature_bulk_tag(
    action: str = typer.Option(..., "--action", "-a", help="add | remove | replace"),
    tags: str = typer.Option(..., "--tags", "-t", help="Comma-separated tags"),
    file: Path = typer.Option(  # noqa: B008
        ...,
        "--file",
        "-f",
        help="Path to newline-delimited specs file (one source.column per line; '#' lines ignored)",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt for --action replace"),
) -> None:
    """Bulk-apply a tag change across many features.

    Mirrors ``POST /api/features/bulk/tags`` (LocalBackend.bulk_update_tags).
    All-or-nothing: if any spec in the file doesn't resolve to a feature
    the command exits 1 with the unresolved specs listed, before any DB
    writes happen.
    """
    if action not in {"add", "remove", "replace"}:
        console.print(f"[red]--action must be add|remove|replace[/red] (got {action!r})")
        raise typer.Exit(1)

    specs = _read_specs_file(file)
    if not specs:
        console.print("[red]No specs in file.[/red]")
        raise typer.Exit(1)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if not tag_list:
        console.print("[red]--tags must contain at least one tag.[/red]")
        raise typer.Exit(1)

    db = _get_db()
    try:
        ids, invalid = _resolve_specs(db, specs)
        if invalid:
            console.print(f"[red]Unresolved feature spec(s):[/red] {', '.join(invalid)}")
            raise typer.Exit(1)

        if action == "replace" and not yes:
            console.print(
                f"[yellow]Replacing tags on {len(ids)} feature(s)"
                f" with {tag_list}.[/yellow] Existing tags will be discarded."
            )
            if not typer.confirm("Continue?"):
                console.print("[dim]Aborted.[/dim]")
                raise typer.Exit(0)

        updated = db.bulk_update_tags(ids, action, tag_list)
        console.print(f"[green]Updated {updated}/{len(ids)} feature(s) (action: {action}).[/green]")
    finally:
        db.close()


@feature_app.command("bulk-delete")
def feature_bulk_delete(
    file: Path = typer.Option(  # noqa: B008
        ...,
        "--file",
        "-f",
        help="Path to newline-delimited specs file (one source.column per line; '#' lines ignored)",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
) -> None:
    """Bulk hard-delete features (cascade per LocalBackend.bulk_delete_features).

    Mirrors ``POST /api/features/bulk/delete`` (with the REST API's
    ``confirm: true`` gate replaced by an interactive prompt). When the
    file contains more than 10 specs the prompt requires typing
    ``DELETE`` back to confirm.
    """
    specs = _read_specs_file(file)
    if not specs:
        console.print("[red]No specs in file.[/red]")
        raise typer.Exit(1)

    db = _get_db()
    try:
        ids, invalid = _resolve_specs(db, specs)
        if invalid:
            console.print(f"[red]Unresolved feature spec(s):[/red] {', '.join(invalid)}")
            raise typer.Exit(1)

        impact_summary = (
            f"[yellow]About to delete {len(ids)} feature(s).[/yellow]\n"
            "[yellow]This will cascade-remove docs, baselines, monitoring checks,"
            " usage logs, group memberships, lineage edges, and version history.[/yellow]"
        )

        if len(ids) > 10:
            if not _confirm_typing("DELETE", impact_summary, skip=yes):
                console.print("[dim]Aborted.[/dim]")
                raise typer.Exit(0)
        elif not yes:
            console.print(impact_summary)
            if not typer.confirm("Proceed?"):
                console.print("[dim]Aborted.[/dim]")
                raise typer.Exit(0)

        deleted = db.bulk_delete_features(ids)
        console.print(f"[green]Deleted {deleted}/{len(ids)} feature(s).[/green]")
    finally:
        db.close()


@feature_app.command("tag")
def feature_tag(
    name: str = typer.Argument(help="Feature name"),
    tags: list[str] = typer.Argument(help="Tags to add"),  # noqa: B008
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

    for f in results:
        log_feature_usage(db, f.id, "search", context=query)

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


@feature_app.command("history")
def feature_history(
    name: str = typer.Argument(help="Feature name (e.g. source.column)"),
) -> None:
    """Show version history for a feature."""
    db = _get_db()
    feature = db.get_feature_by_name(name)
    if feature is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        db.close()
        raise typer.Exit(1)
    versions = db.list_feature_versions(feature.id)
    db.close()
    if not versions:
        console.print(f"No version history for [cyan]{name}[/cyan]")
        return
    table = Table(title=f"Version History: {name}")
    table.add_column("Version", style="bold", justify="right")
    table.add_column("Changed", style="dim")
    table.add_column("Summary")
    table.add_column("By", style="dim")
    for v in versions:
        ts = v["created_at"]
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%Y-%m-%d %H:%M")
        table.add_row(str(v["version"]), str(ts), v.get("change_summary", ""), v.get("changed_by", ""))
    console.print(table)


@feature_app.command("diff")
def feature_diff(
    name: str = typer.Argument(help="Feature name"),
    v1: int | None = typer.Option(None, "--v1", help="First version (default: previous)"),
    v2: int | None = typer.Option(None, "--v2", help="Second version (default: latest)"),
) -> None:
    """Diff two versions of a feature's metadata."""
    db = _get_db()
    feature = db.get_feature_by_name(name)
    if feature is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        db.close()
        raise typer.Exit(1)
    versions = db.list_feature_versions(feature.id)
    db.close()
    if not versions:
        console.print(f"No version history for [cyan]{name}[/cyan]")
        return
    if v2 is None:
        v2 = versions[0]["version"]
    if v1 is None:
        v1 = versions[1]["version"] if len(versions) > 1 else versions[0]["version"]
    snap_v1 = next((v["snapshot"] for v in versions if v["version"] == v1), None)
    snap_v2 = next((v["snapshot"] for v in versions if v["version"] == v2), None)
    if snap_v1 is None or snap_v2 is None:
        console.print("[red]Version not found[/red]")
        raise typer.Exit(1)
    console.print(f"\n[bold]Comparing v{v2} vs v{v1}:[/bold]")
    has_diff = False
    # User-editable fields the diff should report. The original list missed
    # `definition` / `definition_type` / `generation_hints` / `status` /
    # `status_notes`, so any version that only changed those (the common case
    # after `feature set-definition` or `feature set-hint`) reported
    # "(no differences)" — UAT scenario g.3, drift bug #1 in docs/BACKLOG.md.
    diff_fields: tuple[str, ...] = (
        "description",
        "tags",
        "owner",
        "dtype",
        "column_name",
        "definition",
        "definition_type",
        "generation_hints",
        "status",
        "status_notes",
    )
    for field in diff_fields:
        old = snap_v1.get(field)
        new = snap_v2.get(field)
        if old != new:
            console.print(f"  [cyan]{field}:[/cyan]  {old!r} -> {new!r}")
            has_diff = True
    if not has_diff:
        console.print("  (no differences)")
    console.print()


@feature_app.command("rollback")
def feature_rollback(
    name: str = typer.Argument(help="Feature name"),
    version: int = typer.Option(..., "--version", "-v", help="Version number to rollback to"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Rollback feature metadata to a previous version."""
    db = _get_db()
    feature = db.get_feature_by_name(name)
    if feature is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        db.close()
        raise typer.Exit(1)
    target = db.get_feature_version(feature.id, version)
    if target is None:
        console.print(f"[red]Version {version} not found[/red]")
        db.close()
        raise typer.Exit(1)
    if not yes:
        console.print(f"\nRollback [cyan]{name}[/cyan] to version {version}?")
        snapshot = target["snapshot"]
        for field in ("description", "tags", "owner", "dtype"):
            old = getattr(feature, field, None)
            new = snapshot.get(field)
            if old != new:
                console.print(f"  [cyan]{field}:[/cyan]  {old!r} -> {new!r}")
        if not typer.confirm("Confirm?"):
            db.close()
            raise typer.Exit(0)
    db.rollback_feature(feature.id, version)
    versions = db.list_feature_versions(feature.id)
    new_ver = versions[0]["version"] if versions else "?"
    db.close()
    console.print(f"[green]Rolled back.[/green] New version {new_ver} created.")


# =========================================================================
# Discover command
# =========================================================================


@app.command()
def discover(
    use_case: str = typer.Argument(help="Description of the use case"),
) -> None:
    """Discover relevant features for a use case using AI."""
    from .catalog.remote import RemoteBackend

    db = _get_db()

    if isinstance(db, RemoteBackend):
        with console.status("[blue]Analyzing catalog (remote)..."):
            try:
                data = db.ai_discover(use_case)
            except Exception as e:
                db.close()
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1) from None
        db.close()
    else:
        llm = _get_llm(use_cache=False)
        if llm is None:
            db.close()
            console.print("[red]LLM unavailable.[/red] Ensure LLM server is running")
            raise typer.Exit(1)

        settings = load_settings()

        from .plugins.discovery import DiscoveryPlugin

        plugin = DiscoveryPlugin()

        with console.status("[blue]Analyzing catalog..."):
            result = plugin.execute(
                db,
                llm,
                use_case=use_case,
                max_features=settings.max_context_features,
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
    from .catalog.remote import RemoteBackend

    db = _get_db()

    if isinstance(db, RemoteBackend):
        with console.status("[blue]Searching (remote)..."):
            try:
                data = db.ai_ask(query)
            except Exception as e:
                db.close()
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1) from None
        db.close()
    else:
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


@app.command()
def chat(
    server_url: str = typer.Option("", "--server", help="Server URL (defaults to FEATCAT_SERVER_URL or :8000)"),
) -> None:
    """Interactive chat with the catalog AI agent (streams via SSE)."""
    import httpx

    base = server_url or os.environ.get("FEATCAT_SERVER_URL", "http://localhost:8000")
    history: list[dict[str, str]] = []
    console.print(f"[dim]Connected to {base}. Type your question (or 'exit' to quit).[/dim]")

    while True:
        try:
            query = typer.prompt(">", prompt_suffix=" ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not query.strip():
            continue
        if query.strip().lower() in {"exit", "quit", ":q"}:
            break

        history.append({"role": "user", "content": query})
        console.print()  # blank line before response
        full_response = ""
        try:
            with httpx.stream(
                "POST",
                f"{base}/api/ai/chat",
                json={"messages": history},
                timeout=180,
            ) as response:
                response.raise_for_status()
                event_name: str | None = None
                for line in response.iter_lines():
                    if not line:
                        event_name = None
                        continue
                    if line.startswith("event:"):
                        event_name = line[6:].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_payload = line[5:].strip()
                    if not data_payload:
                        continue
                    try:
                        evt = json.loads(data_payload)
                    except json.JSONDecodeError:
                        continue
                    kind = evt.get("type") or event_name
                    if kind == "token":
                        token = evt.get("content") or evt.get("token") or ""
                        console.print(token, end="", soft_wrap=True)
                        full_response += token
                    elif kind == "tool_call":
                        console.print(f"\n[dim italic]→ tool: {evt.get('name', '?')}[/dim italic]")
                    elif kind == "thinking_start":
                        console.print("[dim]thinking…[/dim] ", end="")
                    elif kind == "thinking_end":
                        console.print()
                    elif kind == "done":
                        break
        except httpx.HTTPError as e:  # noqa: BLE001
            console.print(f"\n[red]Stream error:[/red] {e}")
            history.pop()  # don't keep failed turn
            continue

        console.print()  # newline after stream
        if full_response:
            history.append({"role": "assistant", "content": full_response})


# =========================================================================
# Doc commands
# =========================================================================


@doc_app.command("generate")
def doc_generate(
    name: str | None = typer.Argument(None, help="Feature name (or omit for all)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass response cache"),
    all_features: bool = typer.Option(False, "--all", help="Regenerate docs for ALL features, even documented ones"),
    context: str | None = typer.Option(
        None,
        "--context",
        help="Free-form organization/domain context injected into the LLM prompt.",
    ),
    source: str | None = typer.Option(
        None,
        "--source",
        help="Only generate docs for features from this source. Combines with --all.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        min=0,
        help="Cap the number of features processed (after source filter).",
    ),
) -> None:
    """Generate AI documentation for features."""
    from .catalog.remote import RemoteBackend

    db = _get_db()

    if isinstance(db, RemoteBackend):
        with console.status(f"[blue]Generating docs (remote){'for ' + name if name else ''}..."):
            try:
                data = db.doc_generate(feature_name=name)
            except Exception as e:
                db.close()
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1) from None
        db.close()
        documented = data.get("documented", 0)
        console.print(f"[green]Done:[/green] {documented} features documented")
        if context:
            console.print("[yellow]Note:[/yellow] --context is ignored in remote mode (server uses its own context).")
        if source or limit is not None:
            console.print("[yellow]Note:[/yellow] --source / --limit are ignored in remote mode.")
        return

    llm = _get_llm(use_cache=not no_cache)
    if llm is None:
        db.close()
        console.print("[red]LLM unavailable.[/red] Ensure LLM server is running")
        raise typer.Exit(1)

    from rich.progress import Progress

    from .plugins.autodoc import AutodocPlugin

    plugin = AutodocPlugin()

    if name:
        if source or limit is not None:
            console.print(
                "[yellow]Note:[/yellow] --source / --limit are ignored when a specific feature name is supplied."
            )
        with console.status(f"[blue]Generating doc for {name}..."):
            result = plugin.execute(db, llm, feature_name=name, context=context)
    else:
        with Progress(console=console) as progress:
            task = progress.add_task("[blue]Generating docs...", total=None)

            def on_progress(current: int, total: int) -> None:
                progress.update(task, completed=current, total=total)

            result = plugin.execute(
                db,
                llm,
                progress_callback=on_progress,
                regenerate_all=all_features,
                context=context,
                source_name=source,
                limit=limit,
            )

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

    console.print("\n[bold]Documentation Coverage[/bold]")
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
    from .catalog.remote import RemoteBackend

    db = _get_db()

    if isinstance(db, RemoteBackend):
        with console.status("[blue]Computing baselines (remote)..."):
            data = db.monitor_baseline()
        db.close()
        console.print(f"[green]Baseline saved:[/green] {data.get('baselines_saved', 0)} features")
        return

    from .plugins.monitoring import MonitoringPlugin

    plugin = MonitoringPlugin()
    result = plugin.execute(db, None, action="baseline")
    db.close()
    console.print(f"[green]Baseline saved:[/green] {result.data.get('baselines_saved', 0)} features")


@monitor_app.command("check")
def monitor_check(
    name: str | None = typer.Argument(None, help="Feature name (or omit for all)"),
    refresh_baseline: bool = typer.Option(False, "--refresh-baseline", help="Update baseline after check"),
    use_llm: bool = typer.Option(False, "--llm", help="Include LLM analysis for issues"),
) -> None:
    """Check features for quality issues and drift."""
    from .catalog.remote import RemoteBackend

    db = _get_db()

    if isinstance(db, RemoteBackend):
        with console.status("[blue]Running quality checks (remote)..."):
            report = db.monitor_check(feature_name=name, use_llm=use_llm)
        db.close()
    else:
        llm = _get_llm() if use_llm else None

        from .plugins.monitoring import MonitoringPlugin

        plugin = MonitoringPlugin()

        with console.status("[blue]Running quality checks..."):
            result = plugin.execute(
                db,
                llm,
                action="check",
                feature_name=name,
                refresh_baseline=refresh_baseline,
                use_llm=use_llm and llm is not None,
            )
        db.close()

        report = result.data
    checked = report.get("checked", 0)
    healthy = report.get("healthy", 0)
    warnings = report.get("warnings", 0)
    critical = report.get("critical", 0)

    console.print("\n[bold]Quality Check Results[/bold]")
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


@monitor_app.command("history")
def monitor_history(
    feature: str = typer.Argument(help="Feature name (e.g. source.column)"),
    days: int = typer.Option(30, "--days", "-d", help="History window in days"),
) -> None:
    """Show drift check history for a feature."""
    db = _get_db()
    rows = db.get_monitoring_history(feature, days=days)
    db.close()
    if not rows:
        console.print(f"[dim]No monitoring history for {feature} in last {days} days[/dim]")
        return

    table = Table(title=f"Drift history — {feature} (last {days} days)")
    table.add_column("Checked at")
    table.add_column("Severity")
    table.add_column("PSI", justify="right")
    for r in rows:
        psi = r.get("psi")
        psi_str = f"{psi:.4f}" if isinstance(psi, int | float) else "-"
        ts = str(r.get("checked_at", ""))[:19]
        table.add_row(ts, r.get("severity", "-"), psi_str)
    console.print(table)


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
    console.print("\n[bold]LLM Response Cache[/bold]")
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
# Config commands
# =========================================================================


@config_app.command("show")
def config_show() -> None:
    """Show all current configuration."""
    from .config import get_all_setting_sources

    settings = load_settings()
    sources = get_all_setting_sources()

    table = Table(title="featcat Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    for key, value in sorted(settings.model_dump().items()):
        source = sources.get(key, "default")
        source_style = {"env": "green", "project": "yellow", "user": "blue"}.get(source, "dim")
        display_val = str(value) if value is not None else "(not set)"
        # Mask sensitive values
        if "secret" in key or "password" in key:
            display_val = "****" if value else "(not set)"
        table.add_row(key, display_val, f"[{source_style}]{source}[/{source_style}]")

    console.print(table)


@config_app.command("get")
def config_get(
    key: str = typer.Argument(help="Configuration key"),
) -> None:
    """Get a configuration value."""
    settings = load_settings()
    data = settings.model_dump()
    if key not in data:
        console.print(f"[red]Unknown key:[/red] {key}")
        console.print(f"[dim]Available: {', '.join(sorted(data.keys()))}[/dim]")
        raise typer.Exit(1)
    console.print(f"{data[key]}")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Configuration key"),
    value: str = typer.Argument(help="Configuration value"),
    user: bool = typer.Option(False, "--user", help="Save to user config instead of project"),
) -> None:
    """Set a configuration value."""
    # Validate key
    from .config import CONFIG_PROJECT_PATH, CONFIG_USER_PATH, Settings, _load_yaml, _save_yaml

    defaults = Settings().model_dump()
    if key not in defaults:
        console.print(f"[red]Unknown key:[/red] {key}")
        console.print(f"[dim]Available: {', '.join(sorted(defaults.keys()))}[/dim]")
        raise typer.Exit(1)

    # Type coercion based on default value type
    default_val = defaults[key]
    if isinstance(default_val, bool):
        typed_value = value.lower() in ("true", "1", "yes")
    elif isinstance(default_val, int):
        typed_value = int(value)
    elif isinstance(default_val, float):
        typed_value = float(value)
    elif value.lower() == "none" or value == "":
        typed_value = None
    else:
        typed_value = value

    config_path = CONFIG_USER_PATH if user else CONFIG_PROJECT_PATH
    data = _load_yaml(config_path)
    data[key] = typed_value
    _save_yaml(config_path, data)

    location = "user" if user else "project"
    console.print(f"[green]Set[/green] {key} = {typed_value} [dim]({location} config)[/dim]")


@config_app.command("reset")
def config_reset(
    user: bool = typer.Option(False, "--user", help="Reset user config"),
    project: bool = typer.Option(False, "--project", help="Reset project config"),
    all_configs: bool = typer.Option(False, "--all", help="Reset both user and project config"),
) -> None:
    """Reset configuration to defaults."""
    from .config import CONFIG_PROJECT_PATH, CONFIG_USER_PATH

    if all_configs:
        user = project = True

    if not user and not project:
        project = True  # default to project

    if project and CONFIG_PROJECT_PATH.exists():
        CONFIG_PROJECT_PATH.unlink()
        console.print(f"[green]Removed:[/green] {CONFIG_PROJECT_PATH}")

    if user and CONFIG_USER_PATH.exists():
        CONFIG_USER_PATH.unlink()
        console.print(f"[green]Removed:[/green] {CONFIG_USER_PATH}")

    console.print("[green]Config reset to defaults.[/green]")


@config_app.command("path")
def config_path() -> None:
    """Show configuration file locations."""
    from .config import CONFIG_PROJECT_PATH, CONFIG_USER_PATH

    console.print(f"  User config:    {CONFIG_USER_PATH}", end="")
    console.print(" [green](exists)[/green]" if CONFIG_USER_PATH.exists() else " [dim](not created)[/dim]")
    console.print(f"  Project config: {CONFIG_PROJECT_PATH.resolve()}", end="")
    console.print(" [green](exists)[/green]" if CONFIG_PROJECT_PATH.exists() else " [dim](not created)[/dim]")


# =========================================================================
# Job commands
# =========================================================================


def _job_api():
    """Get httpx client for remote job API, or None if local mode."""
    settings = load_settings()
    if settings.server_url:
        import httpx

        headers = {}
        if settings.server_auth_token:
            headers["Authorization"] = f"Bearer {settings.server_auth_token}"
        return httpx.Client(base_url=settings.server_url, timeout=30, headers=headers)
    return None


def _job_local_scheduler():
    """Create a local FeatcatScheduler for direct job access."""
    try:
        from .server.scheduler import FeatcatScheduler
    except ImportError:
        console.print("[red]Job commands require server extras.[/red] Install: uv pip install 'featcat[server]'")
        raise typer.Exit(1) from None

    settings = load_settings()
    db = LocalBackend(settings.catalog_db_path)
    db.init_db()
    scheduler = FeatcatScheduler(backend=db, llm=None, settings=settings)
    scheduler.setup_default_jobs()
    return scheduler, db


@job_app.command("list")
def job_list() -> None:
    """Show all scheduled jobs."""
    api = _job_api()
    if api:
        rows = api.get("/api/jobs").json()
        api.close()
    else:
        scheduler, db = _job_local_scheduler()
        rows = scheduler.get_schedules()
        db.close()

    if not rows:
        console.print("[dim]No scheduled jobs found.[/dim]")
        return

    table = Table(title="Scheduled Jobs")
    table.add_column("Job", style="cyan")
    table.add_column("Schedule")
    table.add_column("Enabled")
    table.add_column("Last Run")
    table.add_column("Description")

    for row in rows:
        enabled = "[green]yes[/green]" if row.get("enabled") else "[red]no[/red]"
        last_run = str(row.get("last_run_at", ""))[:19] if row.get("last_run_at") else "[dim]never[/dim]"
        table.add_row(
            row.get("job_name", ""), row.get("cron_expression", ""), enabled, last_run, row.get("description", "")
        )

    console.print(table)


@job_app.command("logs")
def job_logs(
    job: str | None = typer.Option(None, "--job", "-j", help="Filter by job name"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows"),
) -> None:
    """Show recent job execution logs."""
    api = _job_api()
    if api:
        params: dict = {"limit": limit}
        if job:
            params["job_name"] = job
        rows = api.get("/api/jobs/logs", params=params).json()
        api.close()
    else:
        scheduler, db = _job_local_scheduler()
        rows = scheduler.get_logs(job_name=job, limit=limit)
        db.close()

    if not rows:
        console.print("[dim]No job logs found.[/dim]")
        return

    table = Table(title="Job Logs")
    table.add_column("Job", style="cyan")
    table.add_column("Status")
    table.add_column("Started")
    table.add_column("Duration")
    table.add_column("Triggered By")

    for row in rows:
        status = row.get("status", "")
        color = {"success": "green", "failed": "red", "warning": "yellow", "running": "blue"}.get(status, "dim")
        dur = row.get("duration_seconds")
        duration = f"{dur:.1f}s" if dur else "-"
        started = str(row.get("started_at", ""))[:19] if row.get("started_at") else "-"
        table.add_row(
            row.get("job_name", ""), f"[{color}]{status}[/{color}]", started, duration, row.get("triggered_by", "")
        )

    console.print(table)


@job_app.command("run")
def job_run(
    name: str = typer.Argument(help="Job name to run"),
) -> None:
    """Manually trigger a job."""
    api = _job_api()
    if api:
        with console.status(f"[blue]Running {name} (remote)..."):
            resp = api.post(f"/api/jobs/{name}/run")
            result = resp.json()
        api.close()
    else:
        import asyncio

        scheduler, db = _job_local_scheduler()
        with console.status(f"[blue]Running {name}..."):
            result = asyncio.run(scheduler.run_job(name, triggered_by="manual"))
        db.close()

    status = result.get("status", "unknown")
    color = "green" if status == "success" else "red" if status == "failed" else "yellow"
    dur = result.get("duration_seconds", 0)
    console.print(f"[{color}]{status}[/{color}] {name} ({dur:.1f}s)")
    if result.get("error_message"):
        console.print(f"[red]Error:[/red] {result['error_message']}")


@job_app.command("enable")
def job_enable(name: str = typer.Argument(help="Job name")) -> None:
    """Enable a scheduled job."""
    api = _job_api()
    if api:
        api.patch(f"/api/jobs/{name}", json={"enabled": True})
        api.close()
    else:
        scheduler, db = _job_local_scheduler()
        scheduler.update_schedule(name, cron=None, enabled=True)
        db.close()
    console.print(f"[green]Enabled:[/green] {name}")


@job_app.command("disable")
def job_disable(name: str = typer.Argument(help="Job name")) -> None:
    """Disable a scheduled job."""
    api = _job_api()
    if api:
        api.patch(f"/api/jobs/{name}", json={"enabled": False})
        api.close()
    else:
        scheduler, db = _job_local_scheduler()
        scheduler.update_schedule(name, cron=None, enabled=False)
        db.close()
    console.print(f"[yellow]Disabled:[/yellow] {name}")


@job_app.command("schedule")
def job_schedule(
    name: str = typer.Argument(help="Job name"),
    cron: str = typer.Argument(help="Cron expression (e.g. '0 */6 * * *')"),
) -> None:
    """Change a job's cron schedule."""
    api = _job_api()
    if api:
        api.patch(f"/api/jobs/{name}", json={"cron_expression": cron})
        api.close()
    else:
        scheduler, db = _job_local_scheduler()
        scheduler.update_schedule(name, cron=cron, enabled=None)
        db.close()
    console.print(f"[green]Updated:[/green] {name} -> {cron}")


# =========================================================================
# Server command
# =========================================================================


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
    reload: bool = typer.Option(False, help="Auto-reload on code changes"),
) -> None:
    """Start the featcat API server."""
    try:
        import uvicorn

        from .server import create_app as _check_server  # noqa: F401
    except ImportError:
        console.print("[red]Server requires extras.[/red] Install with: uv pip install 'featcat[server]'")
        raise typer.Exit(1) from None

    console.print(f"[green]Starting featcat server[/green] at http://{host}:{port}")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    uvicorn.run(
        "featcat.server:create_app",
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else 1,
        factory=True,
    )


# =========================================================================
# Bulk Inventory
# =========================================================================


@app.command(name="scan-bulk")
def scan_bulk(
    path: str = typer.Argument(help="Directory or S3 prefix (s3://bucket/prefix) to scan for data files"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Search subdirectories"),
    owner: str = typer.Option("", "--owner", "-o", help="Owner for all discovered features"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Tags to apply to all features"),  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen without writing to DB"),
    formats: str = typer.Option(
        "parquet,csv",
        "--formats",
        help="Comma-separated list of formats to discover: parquet,csv",
    ),
) -> None:
    """Scan a directory or S3 prefix for Parquet/CSV files and register them as sources + features."""
    fmt_list = tuple(f.strip().lower() for f in formats.split(",") if f.strip())
    try:
        files = discover_files(path, recursive=recursive, formats=fmt_list)
    except NotADirectoryError:
        console.print(f"[red]Not a directory:[/red] {path}")
        raise typer.Exit(1) from None
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    except ValueError as e:
        console.print(f"[red]Invalid path:[/red] {e}")
        raise typer.Exit(1) from None

    if not files:
        console.print(f"[dim]No matching data files found in {path}[/dim]")
        return

    db = _get_db()
    registered_sources = 0
    registered_features = 0
    skipped = 0

    for f in files:
        # ``f`` is a string in both branches: absolute local path or s3:// URI.
        abs_path = f
        source_name = Path(f).stem

        # Check if already registered by path
        existing = db.get_source_by_path(abs_path)
        if existing:
            skipped += 1
            console.print(f"  [dim]Skipped {source_name} (already registered)[/dim]")
            continue

        if dry_run:
            try:
                columns = scan_source(abs_path)
                console.print(f"  [cyan]Would register[/cyan] {source_name}: {len(columns)} features")
            except Exception as e:  # noqa: BLE001
                console.print(f"  [red]Error reading {source_name}:[/red] {e}")
            continue

        # Handle name collision: if source name already exists, append suffix
        final_name = source_name
        suffix = 1
        while db.get_source_by_name(final_name) is not None:
            final_name = f"{source_name}_{suffix}"
            suffix += 1

        try:
            source = DataSource(name=final_name, path=abs_path, format=detect_file_format(abs_path))
            db.add_source(source)
            registered_sources += 1

            columns = scan_source(abs_path)
            for col in columns:
                feature = Feature(
                    name=f"{final_name}.{col.column_name}",
                    data_source_id=source.id,
                    column_name=col.column_name,
                    dtype=col.dtype,
                    stats=col.stats,
                    owner=owner,
                    tags=list(tag),
                )
                db.upsert_feature(feature)
                registered_features += 1

            console.print(f"  [green]OK[/green] {final_name}: {len(columns)} features")
        except Exception as e:  # noqa: BLE001
            console.print(f"  [red]Error processing {source_name}:[/red] {e}")

    db.close()

    console.print()
    if dry_run:
        console.print(
            f"[bold]Dry run:[/bold] Found {len(files)} files, "
            f"would register {len(files) - skipped} sources, skipped {skipped}"
        )
    else:
        console.print(
            f"[bold]Done:[/bold] Found {len(files)} files, registered {registered_sources} new sources, "
            f"{registered_features} new features, skipped {skipped} (already exist)"
        )


# =========================================================================
# Feature Groups
# =========================================================================


@group_app.command("create")
def group_create(
    name: str = typer.Argument(help="Group name"),
    description: str = typer.Option("", "--description", "-d", help="Group description"),
    project: str = typer.Option("", "--project", "-p", help="Project name"),
    owner: str = typer.Option("", "--owner", "-o", help="Group owner"),
) -> None:
    """Create a new feature group."""
    db = _get_db()
    group = FeatureGroup(name=name, description=description, project=project, owner=owner)
    try:
        db.create_group(group)
        console.print(f"[green]Group created:[/green] {name}")
    except Exception:  # noqa: BLE001
        console.print(f"[red]Group already exists:[/red] {name}")
        raise typer.Exit(1) from None
    finally:
        db.close()


@group_app.command("list")
def group_list(
    project: str = typer.Option("", "--project", "-p", help="Filter by project"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit JSON to stdout instead of a table"),
) -> None:
    """List all feature groups."""
    db = _get_db()
    groups = db.list_groups(project=project or None)
    counts = {g.id: db.count_group_members(g.id) for g in groups}
    db.close()

    payload = [
        {
            "name": g.name,
            "project": g.project or "",
            "owner": g.owner or "",
            "feature_count": counts[g.id],
            "description": g.description or "",
        }
        for g in groups
    ]

    def _render() -> None:
        if not groups:
            console.print("[dim]No groups found[/dim]")
            return
        table = Table(title="Feature Groups")
        table.add_column("Name", style="cyan")
        table.add_column("Project")
        table.add_column("Owner")
        table.add_column("Features", justify="right")
        table.add_column("Description")
        for g in groups:
            table.add_row(g.name, g.project or "-", g.owner or "-", str(counts[g.id]), g.description or "-")
        console.print(table)

    _emit(payload, _render, json_mode=json_output)


@group_app.command("show")
def group_show(
    name: str = typer.Argument(help="Group name"),
) -> None:
    """Show group details and member features."""
    db = _get_db()
    group = db.get_group_by_name(name)
    if group is None:
        db.close()
        console.print(f"[red]Group not found:[/red] {name}")
        raise typer.Exit(1)

    members = db.list_group_members(group.id)
    db.close()

    console.print(f"\n[bold cyan]Group: {group.name}[/bold cyan]")
    if group.project:
        console.print(f"  Project:     {group.project}")
    if group.owner:
        console.print(f"  Owner:       {group.owner}")
    if group.description:
        console.print(f"  Description: {group.description}")

    if not members:
        console.print("\n  [dim]No features in this group[/dim]")
    else:
        console.print(f"\n  Features ({len(members)}):")
        for f in members:
            desc = f.description[:50] if f.description else ""
            console.print(f"    {f.name:<40s} {f.dtype:<10s} {desc}")
    console.print()


@group_app.command("add")
def group_add(
    group_name: str = typer.Argument(help="Group name"),
    feature_specs: list[str] = typer.Argument(help="Feature names (e.g. source.column)"),  # noqa: B008
) -> None:
    """Add features to a group."""
    db = _get_db()
    group = db.get_group_by_name(group_name)
    if group is None:
        db.close()
        console.print(f"[red]Group not found:[/red] {group_name}")
        raise typer.Exit(1)

    feature_ids = []
    for spec in feature_specs:
        feature = db.get_feature_by_name(spec)
        if feature is None:
            console.print(f"[red]Feature not found:[/red] {spec}")
            continue
        feature_ids.append(feature.id)
        log_feature_usage(db, feature.id, "group_add", context=group_name)

    if feature_ids:
        added = db.add_group_members(group.id, feature_ids)
        console.print(f"[green]Added {added} feature(s)[/green] to group '{group_name}'")
    db.close()


@group_app.command("remove")
def group_remove(
    group_name: str = typer.Argument(help="Group name"),
    feature_specs: list[str] = typer.Argument(help="Feature names to remove"),  # noqa: B008
) -> None:
    """Remove features from a group."""
    db = _get_db()
    group = db.get_group_by_name(group_name)
    if group is None:
        db.close()
        console.print(f"[red]Group not found:[/red] {group_name}")
        raise typer.Exit(1)

    for spec in feature_specs:
        feature = db.get_feature_by_name(spec)
        if feature is None:
            console.print(f"[red]Feature not found:[/red] {spec}")
            continue
        db.remove_group_member(group.id, feature.id)
        console.print(f"  Removed {spec}")

    db.close()


@group_app.command("delete")
def group_delete(
    name: str = typer.Argument(help="Group name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a feature group."""
    if not yes:
        confirm = typer.confirm(f"Delete group '{name}'?")
        if not confirm:
            raise typer.Exit(0)

    db = _get_db()
    group = db.get_group_by_name(name)
    if group is None:
        db.close()
        console.print(f"[red]Group not found:[/red] {name}")
        raise typer.Exit(1)

    db.delete_group(group.id)
    db.close()
    console.print(f"[green]Group deleted:[/green] {name}")


@group_app.command("update")
def group_update(
    name: str = typer.Argument(help="Group name"),
    description: str | None = typer.Option(None, "--description", "-d", help="New description"),
    project: str | None = typer.Option(None, "--project", "-p", help="New project"),
    owner: str | None = typer.Option(None, "--owner", help="New owner"),
) -> None:
    """Update mutable fields on a group (description, project, owner).

    Mirrors ``PATCH /api/groups/{name}``. Empty strings are passed through
    (clear the field); to leave a field untouched, omit the option.
    """
    if description is None and project is None and owner is None:
        console.print("[red]Nothing to update.[/red] Pass --description, --project and/or --owner.")
        raise typer.Exit(1)

    db = _get_db()
    try:
        group = db.get_group_by_name(name)
        if group is None:
            console.print(f"[red]Group not found:[/red] {name}")
            raise typer.Exit(1)
        updates: dict[str, str] = {}
        if description is not None:
            updates["description"] = description
        if project is not None:
            updates["project"] = project
        if owner is not None:
            updates["owner"] = owner
        db.update_group(group.id, **updates)
        console.print(f"[green]Updated group:[/green] {name}")
    finally:
        db.close()


@group_app.command("health")
def group_health(name: str = typer.Argument(help="Group name")) -> None:
    """Aggregate health score and grade distribution for a group."""
    from .catalog.health import compute_health_score
    from .server.routes.features import _bulk_health_data

    db = _get_db()
    group = db.get_group_by_name(name)
    if group is None:
        db.close()
        console.print(f"[red]Group not found:[/red] {name}")
        raise typer.Exit(1)

    members = db.list_group_members(group.id)
    if not members:
        db.close()
        console.print(f"[dim]Group '{name}' has no members[/dim]")
        return

    all_docs, drift_map, usage_map = _bulk_health_data(db)
    grades: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    rows: list[dict] = []
    for f in members:
        usage = usage_map.get(f.id, {"views": 0, "queries": 0})
        h = compute_health_score(
            has_doc=f.id in all_docs,
            has_hints=bool(f.generation_hints),
            drift_status=drift_map.get(f.id),
            views_30d=usage["views"],
            queries_30d=usage["queries"],
        )
        grades[h["grade"]] = grades.get(h["grade"], 0) + 1
        rows.append({"spec": f.name, "score": h["score"], "grade": h["grade"]})
    db.close()

    rows.sort(key=lambda x: x["score"])
    avg = round(sum(r["score"] for r in rows) / len(rows))

    console.print(f"\n[bold cyan]Group health: {name}[/bold cyan]")
    console.print(f"  Members:        {len(members)}")
    console.print(f"  Average score:  {avg}/100")
    grade_str = "  ".join(f"{g}: {c}" for g, c in grades.items())
    console.print(f"  Grades:         {grade_str}\n")

    table = Table(title="Lowest scoring members")
    table.add_column("Feature", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Grade")
    for r in rows[:10]:
        table.add_row(r["spec"], str(r["score"]), r["grade"])
    console.print(table)


@group_app.command("monitoring")
def group_monitoring(name: str = typer.Argument(help="Group name")) -> None:
    """Aggregate latest drift status across group members."""
    db = _get_db()
    group = db.get_group_by_name(name)
    if group is None:
        db.close()
        console.print(f"[red]Group not found:[/red] {name}")
        raise typer.Exit(1)

    members = db.list_group_members(group.id)
    severity_counts: dict[str, int] = {"healthy": 0, "warning": 0, "critical": 0, "unknown": 0}
    rows: list[dict] = []
    for f in members:
        history = []
        try:
            history = db.get_monitoring_history(f.name, days=365)
        except Exception:  # noqa: BLE001
            history = []
        latest = history[0] if history else {}
        sev = (latest or {}).get("severity") or "unknown"
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        rows.append(
            {
                "spec": f.name,
                "severity": sev,
                "psi": (latest or {}).get("psi"),
                "checked_at": str((latest or {}).get("checked_at") or ""),
            }
        )
    db.close()

    console.print(f"\n[bold cyan]Group monitoring: {name}[/bold cyan]")
    console.print(f"  Members: {len(members)}")
    summary = "  ".join(f"{k}: {v}" for k, v in severity_counts.items())
    console.print(f"  Severity: {summary}\n")

    drift = [r for r in rows if r["severity"] in ("warning", "critical")]
    if not drift:
        console.print("[green]No drift detected in this group[/green]")
        return

    table = Table(title="Members with drift")
    table.add_column("Feature", style="cyan")
    table.add_column("Severity")
    table.add_column("PSI", justify="right")
    table.add_column("Checked at")
    for r in drift:
        psi_str = f"{r['psi']:.4f}" if isinstance(r["psi"], int | float) else "-"
        table.add_row(r["spec"], r["severity"], psi_str, r["checked_at"][:19])
    console.print(table)


@group_app.command("regenerate-docs")
def group_regenerate_docs(
    name: str = typer.Argument(help="Group name"),
    regenerate_existing: bool = typer.Option(False, "--regenerate", help="Overwrite existing docs"),
    global_hint: str = typer.Option("", "--hint", help="Global hint applied to features without an individual hint"),
) -> None:
    """Trigger batch doc regeneration scoped to this group via the server."""
    import os as _os
    import time as _time

    import httpx

    server_url = _os.environ.get("FEATCAT_SERVER_URL", "http://localhost:8000")
    try:
        post = httpx.post(
            f"{server_url}/api/groups/{name}/regenerate-docs",
            json={"regenerate_existing": regenerate_existing, "global_hint": global_hint or None},
            timeout=30,
        )
        post.raise_for_status()
    except httpx.HTTPError as e:  # noqa: BLE001
        console.print(f"[red]Server error:[/red] {e}")
        raise typer.Exit(1) from None

    payload = post.json()
    job_id = payload.get("job_id")
    total = payload.get("total", 0)
    console.print(f"[green]Started job {job_id}[/green] for {total} feature(s) in group '{name}'.")

    while True:
        try:
            resp = httpx.get(f"{server_url}/api/docs/generate-batch/{job_id}/status", timeout=15)
            resp.raise_for_status()
        except httpx.HTTPError:
            _time.sleep(2)
            continue
        st = resp.json()
        line = (
            f"  status={st.get('status')} completed={st.get('completed')} failed={st.get('failed')} / {st.get('total')}"
        )
        console.print(line, end="\r")
        if st.get("status") in ("done", "error", "completed"):
            console.print()
            break
        _time.sleep(2)


@group_app.command("freeze")
def group_freeze(
    name: str = typer.Argument(help="Group name"),
    note: str = typer.Option("", "--note", "-n", help="Freeze note (e.g. 'before holiday traffic')"),
    by: str = typer.Option("", "--by", help="Owner attribution; defaults to $USER"),
) -> None:
    """Snapshot the group's current members as a new immutable version."""
    import os as _os

    db = _get_db()
    group = db.get_group_by_name(name)
    if group is None:
        db.close()
        console.print(f"[red]Group not found:[/red] {name}")
        raise typer.Exit(1)
    if db.count_group_members(group.id) == 0:
        db.close()
        console.print(f"[red]Group is empty:[/red] {name}")
        raise typer.Exit(1)

    frozen_by = by or _os.environ.get("USER", "")
    version = db.freeze_group(group.id, note=note, frozen_by=frozen_by)
    db.close()

    member_count = len(json.loads(version.snapshot_json).get("features", []))
    console.print(
        f"[green]Frozen[/green] group [cyan]{name}[/cyan] as v{version.version_number} with {member_count} feature(s)"
    )
    if note:
        console.print(f"  Note: {note}")


@group_app.command("versions")
def group_versions(
    name: str = typer.Argument(help="Group name"),
) -> None:
    """List frozen versions for a group."""
    db = _get_db()
    group = db.get_group_by_name(name)
    if group is None:
        db.close()
        console.print(f"[red]Group not found:[/red] {name}")
        raise typer.Exit(1)
    versions = db.list_group_versions(group.id)
    db.close()

    if not versions:
        console.print(f"[dim]No versions for group '{name}' — run 'featcat group freeze {name}' first[/dim]")
        return

    table = Table(title=f"Versions of {name}")
    table.add_column("Version", justify="right", style="cyan")
    table.add_column("Frozen at")
    table.add_column("By")
    table.add_column("Members", justify="right")
    table.add_column("Note")
    for v in versions:
        member_count = len(json.loads(v.snapshot_json).get("features", []))
        table.add_row(
            f"v{v.version_number}",
            v.frozen_at.isoformat(timespec="seconds"),
            v.frozen_by or "-",
            str(member_count),
            v.note or "-",
        )
    console.print(table)


@group_app.command("export")
def group_export(
    name: str = typer.Argument(help="Group name"),
    version: int = typer.Option(..., "--version", "-v", help="Version number to export"),
    format: str = typer.Option(  # noqa: A002 — keeps --format flag as the obvious name
        "json", "--format", "-f", help="Output format: json | csv | parquet"
    ),
    output: str = typer.Option("", "--output", "-o", help="Output file path; defaults to <name>-v<n>.<format>"),
) -> None:
    """Export a frozen group version as a feature manifest.

    The manifest captures name, dtype, definition, and source path/format
    for every feature in the version — not the underlying data values.
    Reproducibility contract: re-running the pipeline against the same
    sources should yield matching columns.
    """
    if format not in ("json", "csv", "parquet"):
        console.print(f"[red]Invalid format:[/red] {format}")
        raise typer.Exit(1)

    db = _get_db()
    group = db.get_group_by_name(name)
    if group is None:
        db.close()
        console.print(f"[red]Group not found:[/red] {name}")
        raise typer.Exit(1)
    snapshot_version = db.get_group_version(group.id, version)
    if snapshot_version is None:
        db.close()
        console.print(f"[red]Version not found:[/red] {name} v{version}")
        raise typer.Exit(1)

    snapshot = json.loads(snapshot_version.snapshot_json)
    warnings: list[str] = []
    for feature in snapshot.get("features", []):
        current = db.get_feature_by_name(feature.get("name", ""))
        if current is None:
            feature["deleted_after_freeze"] = True
            warnings.append(f"Feature '{feature.get('name')}' was deleted after this version was frozen.")
        else:
            feature["deleted_after_freeze"] = False
    snapshot["warnings"] = warnings
    db.close()

    out_path = output or f"{name}-v{version}.{format}"

    if format == "json":
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2, ensure_ascii=False)
    else:
        columns = [
            "name",
            "dtype",
            "definition",
            "definition_type",
            "column_name",
            "source_name",
            "source_path",
            "source_format",
            "owner",
            "deleted_after_freeze",
        ]
        rows = [{c: f.get(c, "") for c in columns} for f in snapshot.get("features", [])]
        if format == "csv":
            import csv as _csv

            with open(out_path, "w", encoding="utf-8", newline="") as fh:
                writer = _csv.DictWriter(fh, fieldnames=columns)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
        else:  # parquet
            try:
                import pyarrow as pa
                import pyarrow.parquet as pq
            except ImportError:
                console.print("[red]pyarrow is not installed[/red]")
                raise typer.Exit(1) from None
            table = pa.Table.from_pylist([{c: str(r[c]) if r[c] is not None else "" for c in columns} for r in rows])
            pq.write_table(table, out_path)

    console.print(f"[green]Exported[/green] {name} v{version} → {out_path}")
    for w in warnings:
        typer.echo(f"warning: {w}", err=True)


# =========================================================================
# Feature Definitions
# =========================================================================


@feature_app.command("set-definition")
def feature_set_definition(
    spec: str = typer.Argument(help="Feature name (e.g. source.column)"),
    sql: str | None = typer.Option(None, "--sql", help="SQL definition"),
    python: str | None = typer.Option(None, "--python", help="Python expression definition"),
    manual: str | None = typer.Option(None, "--manual", help="Manual/text definition"),
) -> None:
    """Set a feature's definition (SQL, Python, or manual)."""
    # Validate exactly one type is provided
    provided = [(sql, "sql"), (python, "python"), (manual, "manual")]
    active = [(val, typ) for val, typ in provided if val is not None]
    if len(active) != 1:
        console.print("[red]Error:[/red] Provide exactly one of --sql, --python, or --manual")
        raise typer.Exit(1)

    definition, definition_type = active[0]

    db = _get_db()
    feature = db.get_feature_by_name(spec)
    if feature is None:
        db.close()
        console.print(f"[red]Feature not found:[/red] {spec}")
        raise typer.Exit(1)

    db.set_feature_definition(feature.id, definition, definition_type)
    db.close()
    console.print(f"[green]Definition set:[/green] {spec} ({definition_type})")


@feature_app.command("show-definition")
def feature_show_definition(
    spec: str = typer.Argument(help="Feature name (e.g. source.column)"),
) -> None:
    """Show a feature's definition."""
    db = _get_db()
    feature = db.get_feature_by_name(spec)
    if feature is None:
        db.close()
        console.print(f"[red]Feature not found:[/red] {spec}")
        raise typer.Exit(1)

    defn = db.get_feature_definition(feature.id)
    db.close()

    if defn is None:
        console.print(f"[dim]No definition set for {spec}[/dim]")
        return

    console.print(
        Panel(
            defn["definition"],
            title=f"{spec} ({defn['definition_type']})",
            border_style="cyan",
        )
    )


# =========================================================================
# Generation Hints
# =========================================================================


@feature_app.command("set-hint")
def feature_set_hint(
    spec: str = typer.Argument(help="Feature name (e.g. source.column)"),
    hint: str = typer.Option(..., "--hint", "-h", help="Hint text for doc generation"),
) -> None:
    """Set generation hints for a feature (used as ground truth by LLM)."""
    db = _get_db()
    feature = db.get_feature_by_name(spec)
    if feature is None:
        db.close()
        console.print(f"[red]Feature not found:[/red] {spec}")
        raise typer.Exit(1)
    db.set_feature_hint(feature.id, hint)
    db.close()
    console.print(f"[green]Hint set:[/green] {spec}")


@feature_app.command("show-hint")
def feature_show_hint(
    spec: str = typer.Argument(help="Feature name"),
) -> None:
    """Show generation hints for a feature."""
    db = _get_db()
    feature = db.get_feature_by_name(spec)
    if feature is None:
        db.close()
        console.print(f"[red]Feature not found:[/red] {spec}")
        raise typer.Exit(1)
    hint = db.get_feature_hint(feature.id)
    db.close()
    if hint is None:
        console.print(f"[dim]No hint set for {spec}[/dim]")
    else:
        console.print(Panel(hint, title=f"{spec} hint", border_style="cyan"))


@feature_app.command("similar")
def feature_similar(
    name: str = typer.Argument(help="Feature name (e.g. source.column)"),
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Similarity threshold (0.1-0.9)"),
) -> None:
    """Find features similar to the given one via the server's similarity graph."""
    import httpx

    server_url = os.environ.get("FEATCAT_SERVER_URL", "http://localhost:8000")
    try:
        resp = httpx.get(f"{server_url}/api/features/similarity-graph", params={"threshold": threshold}, timeout=60)
        resp.raise_for_status()
    except httpx.HTTPError as e:  # noqa: BLE001
        console.print(f"[red]Server error:[/red] {e}")
        raise typer.Exit(1) from None

    data = resp.json()
    edges = data.get("edges", [])
    neighbors: list[tuple[str, float]] = []
    for edge in edges:
        if edge["source"] == name:
            neighbors.append((edge["target"], edge["similarity"]))
        elif edge["target"] == name:
            neighbors.append((edge["source"], edge["similarity"]))
    if not neighbors:
        console.print(f"[dim]No similar features found for {name} at threshold {threshold}[/dim]")
        return

    neighbors.sort(key=lambda x: -x[1])
    table = Table(title=f"Similar to {name} (threshold {threshold})")
    table.add_column("Feature", style="cyan")
    table.add_column("Similarity", justify="right")
    for spec, sim in neighbors:
        table.add_row(spec, f"{sim:.3f}")
    console.print(table)


@feature_app.command("clear-hint")
def feature_clear_hint(
    spec: str = typer.Argument(help="Feature name"),
) -> None:
    """Remove generation hints for a feature."""
    db = _get_db()
    feature = db.get_feature_by_name(spec)
    if feature is None:
        db.close()
        console.print(f"[red]Feature not found:[/red] {spec}")
        raise typer.Exit(1)
    db.clear_feature_hint(feature.id)
    db.close()
    console.print(f"[green]Hint cleared:[/green] {spec}")


# =========================================================================
# Feature Health
# =========================================================================


def _get_health_inputs(db, feature):
    """Gather health score inputs for a single feature."""
    from .catalog.health import compute_health_score

    all_docs = db.get_all_feature_docs()
    has_doc = feature.id in all_docs
    has_hints = bool(feature.generation_hints)

    drift_status = None
    with contextlib.suppress(Exception):
        drift_status = db.get_latest_severity(feature.id)

    views_30d = 0
    queries_30d = 0
    try:
        usage = db.get_feature_usage(feature.id, days=30)
        views_30d = usage.get("views", 0)
        queries_30d = usage.get("queries", 0)
    except Exception:  # noqa: BLE001
        pass

    return (
        compute_health_score(
            has_doc=has_doc,
            has_hints=has_hints,
            drift_status=drift_status,
            views_30d=views_30d,
            queries_30d=queries_30d,
        ),
        drift_status,
        views_30d,
        queries_30d,
    )


def _health_bar(value: int, max_value: int, width: int = 20) -> str:
    """Render a text progress bar."""
    filled = round(value / max_value * width) if max_value > 0 else 0
    return "\u2588" * filled + "\u2591" * (width - filled)


@feature_app.command("health")
def feature_health(
    name: str = typer.Argument(help="Feature name (e.g. source.column)"),
) -> None:
    """Show health score breakdown for a feature."""
    db = _get_db()
    feature = db.get_feature_by_name(name)
    if feature is None:
        db.close()
        console.print(f"[red]Feature not found:[/red] {name}")
        raise typer.Exit(1)

    health, drift_status, views_30d, queries_30d = _get_health_inputs(db, feature)
    db.close()

    score = health["score"]
    grade = health["grade"]
    bd = health["breakdown"]

    grade_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red"}[grade]

    console.print(f"\nHealth Score: [bold]{score}/100[/bold]  [{grade_color}][{grade}][/{grade_color}]")
    console.print(f"Documentation  {_health_bar(bd['documentation'], 40)}  {bd['documentation']}/40")
    console.print(
        f"Drift          {_health_bar(bd['drift'], 40)}  {bd['drift']}/40  ({drift_status or 'never checked'})"
    )
    console.print(
        f"Usage          {_health_bar(bd['usage'], 20)}  {bd['usage']}/20"
        f"  ({'no recent usage' if bd['usage'] == 0 else f'{views_30d} views, {queries_30d} queries'})"
    )

    # Improvement tips
    tips = []
    if bd["documentation"] < 25:
        tips.append("Generate documentation for this feature (+25pts)")
    if not feature.generation_hints:
        tips.append("Add a generation hint to improve documentation score (+15pts)")
    if bd["usage"] == 0:
        tips.append("Feature has never been queried \u2014 consider sharing with team (+10pts)")
    if tips:
        console.print("\n[dim]Improvement tips:[/dim]")
        for tip in tips:
            console.print(f"  \u2192 {tip}")
    console.print()


@feature_app.command("health-report")
def feature_health_report(
    min_score: int = typer.Option(0, "--min-score", help="Only show features with score >= this value"),
    sort: str = typer.Option("score", "--sort", help="Sort by: score, name, grade"),
) -> None:
    """Show health report for all features."""
    from rich.table import Table

    from .catalog.health import compute_health_score

    db = _get_db()
    features = db.list_features()
    if not features:
        db.close()
        console.print("[dim]No features in catalog.[/dim]")
        raise typer.Exit()

    all_docs = db.get_all_feature_docs()

    rows = []
    for f in features:
        has_doc = f.id in all_docs
        has_hints = bool(f.generation_hints)

        drift_status = None
        with contextlib.suppress(Exception):
            drift_status = db.get_latest_severity(f.id)

        views_30d = 0
        queries_30d = 0
        try:
            usage = db.get_feature_usage(f.id, days=30)
            views_30d = usage.get("views", 0)
            queries_30d = usage.get("queries", 0)
        except Exception:  # noqa: BLE001
            pass

        health = compute_health_score(
            has_doc=has_doc,
            has_hints=has_hints,
            drift_status=drift_status,
            views_30d=views_30d,
            queries_30d=queries_30d,
        )
        if health["score"] >= min_score:
            rows.append({"name": f.name, **health})

    db.close()

    if sort == "score":
        rows.sort(key=lambda r: r["score"])
    elif sort == "grade":
        rows.sort(key=lambda r: r["grade"])
    else:
        rows.sort(key=lambda r: r["name"])

    grade_color = {"A": "green", "B": "cyan", "C": "yellow", "D": "red"}

    table = Table(title="Feature Health Report")
    table.add_column("Feature", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Grade", justify="center")
    table.add_column("Doc", justify="right")
    table.add_column("Drift", justify="right")
    table.add_column("Usage", justify="right")

    for r in rows:
        bd = r["breakdown"]
        gc = grade_color.get(r["grade"], "white")
        table.add_row(
            r["name"],
            str(r["score"]),
            f"[{gc}]{r['grade']}[/{gc}]",
            f"{bd['documentation']}/40",
            f"{bd['drift']}/40",
            f"{bd['usage']}/20",
        )

    console.print(table)
    console.print(f"\n[dim]{len(rows)} features shown[/dim]")


# =========================================================================
# Usage Analytics
# =========================================================================


@usage_app.command("top")
def usage_top(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of features to show"),
    days: int = typer.Option(30, "--days", "-d", help="Number of days to look back"),
) -> None:
    """Show top features by usage count."""
    db = _get_db()
    results = db.get_top_features(limit=limit, days=days)
    db.close()

    if not results:
        console.print(f"[dim]No usage data in the last {days} days[/dim]")
        return

    console.print(f"\n[bold]Top {limit} features (last {days} days)[/bold]\n")
    table = Table()
    table.add_column("#", justify="right")
    table.add_column("Feature", style="cyan")
    table.add_column("Views", justify="right")
    table.add_column("Queries", justify="right")
    table.add_column("Total", justify="right")

    for i, r in enumerate(results, 1):
        table.add_row(str(i), r["name"], str(r["view_count"]), str(r["query_count"]), str(r["total_count"]))

    console.print(table)


@usage_app.command("orphaned")
def usage_orphaned(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to look back"),
) -> None:
    """Show features with zero usage in the given period."""
    db = _get_db()
    results = db.get_orphaned_features(days=days)
    db.close()

    if not results:
        console.print(f"[green]All features have been used in the last {days} days[/green]")
        return

    console.print(f"\n[bold]Orphaned features (no usage in {days} days)[/bold]\n")
    table = Table()
    table.add_column("Feature", style="cyan")
    table.add_column("Last Seen")

    for r in results:
        last = r.get("last_seen") or "never"
        table.add_row(r["name"], str(last))

    console.print(table)
    console.print(f"\n[dim]{len(results)} feature(s) with no recent usage[/dim]")


@usage_app.command("activity")
def usage_activity(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to look back"),
) -> None:
    """Show per-day usage activity summary."""
    db = _get_db()
    results = db.get_usage_activity(days=days)
    db.close()

    if not results:
        console.print(f"[dim]No activity in the last {days} days[/dim]")
        return

    console.print(f"\n[bold]Activity (last {days} days)[/bold]\n")
    table = Table()
    table.add_column("Date")
    table.add_column("Views", justify="right")
    table.add_column("Queries", justify="right")
    table.add_column("Unique Features", justify="right")
    table.add_column("Total", justify="right")

    for r in results:
        table.add_row(
            r["date"],
            str(r["view_count"]),
            str(r["query_count"]),
            str(r["unique_features"]),
            str(r["total"]),
        )

    console.print(table)


# =========================================================================
# Action items (lifecycle loop)
# =========================================================================


@actions_app.command("list")
def actions_list(
    feature: str = typer.Option("", "--feature", "-f", help="Filter by feature name"),
    status: str = typer.Option("pending", "--status", "-s", help="pending|applied|dismissed|snoozed|all"),
    source: str = typer.Option("", "--source", help="Filter by source: drift_alert|chat|autodoc|manual"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max rows"),
) -> None:
    """List action items pending or completed."""
    db = _get_db()
    feature_id = None
    if feature:
        feat = db.get_feature_by_name(feature)
        if feat is None:
            db.close()
            console.print(f"[red]Feature not found:[/red] {feature}")
            raise typer.Exit(1)
        feature_id = feat.id

    items = db.list_action_items(
        feature_id=feature_id,
        status=None if status == "all" else status,
        source=source or None,
        limit=limit,
    )
    db.close()

    if not items:
        console.print("[dim]No action items[/dim]")
        return

    table = Table(title=f"Action Items ({status})")
    table.add_column("ID", style="dim", overflow="fold")
    table.add_column("Feature", style="cyan")
    table.add_column("Source")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Created")
    for it in items:
        table.add_row(
            str(it.get("id", ""))[:8],
            it.get("feature_name", ""),
            it.get("source", ""),
            (it.get("title") or "")[:60],
            it.get("status", ""),
            (it.get("created_at") or "")[:19],
        )
    console.print(table)


@actions_app.command("show")
def actions_show(
    item_id: str = typer.Argument(help="Action item id (full or 8-char prefix)"),
) -> None:
    """Show full detail of an action item."""
    db = _get_db()
    item = _resolve_action(db, item_id)
    db.close()
    if item is None:
        console.print(f"[red]Action item not found:[/red] {item_id}")
        raise typer.Exit(1)
    console.print(f"\n[bold cyan]Action {item['id']}[/bold cyan]")
    console.print(f"  Feature:        {item.get('feature_name', '')}")
    console.print(f"  Source:         {item.get('source', '')}")
    console.print(f"  Status:         {item.get('status', '')}")
    console.print(f"  Title:          {item.get('title', '')}")
    console.print(f"  Recommendation: {item.get('recommendation', '')}")
    if item.get("change_summary"):
        console.print(f"  Change summary: {item['change_summary']}")
    if item.get("applied_by"):
        console.print(f"  Applied by:     {item['applied_by']}  at  {item.get('applied_at', '')}")
    ctx = item.get("context") or {}
    if ctx:
        console.print(f"  Context:        {json.dumps(ctx, indent=2)}")


@actions_app.command("apply")
def actions_apply(
    item_id: str = typer.Argument(help="Action item id"),
    summary: str = typer.Option("", "--summary", "-m", help="Change summary describing what was done"),
    user: str = typer.Option("", "--user", "-u", help="Actor name (defaults to $USER)"),
) -> None:
    """Mark an action item as applied."""
    _set_action_status(item_id, "applied", summary=summary, user=user)


@actions_app.command("dismiss")
def actions_dismiss(
    item_id: str = typer.Argument(help="Action item id"),
    reason: str = typer.Option("", "--reason", "-m", help="Why dismissed"),
    user: str = typer.Option("", "--user", "-u", help="Actor name (defaults to $USER)"),
) -> None:
    """Dismiss an action item."""
    _set_action_status(item_id, "dismissed", summary=reason, user=user)


def _resolve_action(db, item_id: str) -> dict | None:
    item = db.get_action_item(item_id)
    if item is not None:
        return item
    # Allow 8-char prefix lookup (purely a convenience for CLI)
    matches = [it for it in db.list_action_items(status=None, limit=500) if str(it.get("id", "")).startswith(item_id)]
    return matches[0] if len(matches) == 1 else None


def _set_action_status(item_id: str, status: str, summary: str, user: str) -> None:
    import os as _os

    db = _get_db()
    item = _resolve_action(db, item_id)
    if item is None:
        db.close()
        console.print(f"[red]Action item not found:[/red] {item_id}")
        raise typer.Exit(1)
    actor = user or _os.environ.get("USER", "")
    db.update_action_item_status(item["id"], status=status, applied_by=actor, change_summary=summary)
    db.close()
    console.print(f"[green]Action {item['id'][:8]} -> {status}[/green]")


# =========================================================================
# Embeddings (T1.2)
# =========================================================================


@app.command()
def embed(
    all_: bool = typer.Option(False, "--all", help="Re-embed every feature, including ones already embedded"),
    feature: str | None = typer.Option(None, "--feature", help="Embed only this feature (by name)"),
) -> None:
    """Generate vector embeddings for features (T1.2).

    Default: embed only features missing an embedding or whose ``updated_at``
    is newer than ``embedding_updated_at``. ``--all`` forces a full re-embed;
    ``--feature NAME`` targets a single one.

    Requires ``sentence-transformers`` — install with::

        uv pip install -e '.[embeddings]'
    """
    from .ai.embeddings import (
        embeddings_available,
        update_feature_embedding,
        update_missing_embeddings,
    )

    if not embeddings_available():
        console.print(
            "[red]sentence-transformers is not installed.[/red] Run: [cyan]uv pip install -e '.[embeddings]'[/cyan]"
        )
        raise typer.Exit(1)

    db = _get_db()

    if feature:
        f = db.get_feature_by_name(feature)
        if f is None:
            console.print(f"[red]Feature not found:[/red] {feature}")
            raise typer.Exit(1)
        console.print(f"Embedding [cyan]{feature}[/cyan]...")
        update_feature_embedding(db, f)
        console.print("[green]Done.[/green]")
        return

    if all_:
        # Force re-embed: clear all embeddings so the "stale" check fires for every row.
        from sqlalchemy import text as _text

        with db.session() as s:
            s.execute(_text("UPDATE features SET embedding = NULL"))
            s.commit()
        console.print("[dim]Cleared all embeddings; re-embedding...[/dim]")

    import time

    start = time.monotonic()
    result = update_missing_embeddings(db, batch_size=32)
    elapsed = time.monotonic() - start
    console.print(
        f"[green]Embedded[/green] {result['embedded']} feature(s) "
        f"([dim]{result['failed']} failed[/dim]) in {elapsed:.1f}s"
    )


# =========================================================================
# Feature lifecycle status (T3.1)
# =========================================================================


_status_app = typer.Typer(help="Feature lifecycle status: draft → reviewed → certified → deprecated.")
app.add_typer(_status_app, name="status")


@_status_app.command("show")
def status_show(name: str = typer.Argument(..., help="Feature name")) -> None:
    """Show a feature's current status + last-change timestamp + notes."""
    db = _get_db()
    feat = db.get_feature_by_name(name)
    if feat is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        raise typer.Exit(1)
    when = feat.status_changed_at.isoformat() if feat.status_changed_at else "-"
    console.print(
        f"[bold]{feat.name}[/bold]  status=[cyan]{feat.status}[/cyan]  changed={when}\n"
        f"  notes: {feat.status_notes or '[dim]—[/dim]'}"
    )


@_status_app.command("set")
def status_set(
    name: str = typer.Argument(...),
    status: str = typer.Argument(..., help="One of draft, reviewed, certified, deprecated"),
    notes: str | None = typer.Option(None, "--notes", "-n"),
) -> None:
    """Set a feature's status. Certified target gates on the readiness checklist."""
    db = _get_db()
    feat = db.get_feature_by_name(name)
    if feat is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        raise typer.Exit(1)
    try:
        result = db.set_feature_status(feat.id, status, notes)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    if not result["ok"]:
        console.print(f"[yellow]Cannot mark [bold]{name}[/bold] as certified — missing:[/yellow]")
        for m in result["missing"]:
            console.print(f"  • {m}")
        raise typer.Exit(2)
    console.print(f"[green]{name} → {result['status']}[/green]")


@_status_app.command("check")
def status_check(name: str = typer.Argument(...)) -> None:
    """Check whether a feature meets the certification checklist."""
    db = _get_db()
    feat = db.get_feature_by_name(name)
    if feat is None:
        console.print(f"[red]Feature not found:[/red] {name}")
        raise typer.Exit(1)
    readiness = db.check_certification_readiness(feat.id)
    if readiness["ready"]:
        console.print(f"[green]{name} is ready for certification.[/green]")
    else:
        console.print(f"[yellow]{name} is not ready. Missing:[/yellow]")
        for m in readiness["missing"]:
            console.print(f"  • {m}")


@_status_app.command("list")
def status_list(
    status: str = typer.Option(..., "--status", "-s", help="Filter by status"),
) -> None:
    """List features in a given status."""
    db = _get_db()
    try:
        feats = db.list_features_by_status(status)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    if not feats:
        console.print(f"[dim]No features in status={status}.[/dim]")
        return
    console.print(f"[bold]{len(feats)} feature(s) in status={status}[/bold]")
    for f in feats:
        when = f.status_changed_at.isoformat() if f.status_changed_at else "-"
        console.print(f"  [cyan]{f.name}[/cyan]  changed={when}")


# =========================================================================
# Lineage / impact analysis (T1.1)
# =========================================================================


@app.command()
def impact(
    target: str = typer.Argument(..., help="Source name or 'source.column' to analyze"),
    depth: int = typer.Option(5, "--depth", "-d", help="Max BFS depth through feature→feature edges"),
) -> None:
    """Show features impacted by changes to a source or source.column.

    Output is grouped by depth: direct children first, then transitive
    downstreams. ``via`` shows the immediate parent in the propagation chain
    so you can trace how the impact reaches each feature.

    Examples:

        featcat impact user_behavior
        featcat impact user_behavior.session_count
        featcat impact user_behavior.session_count --depth 3
    """
    db = _get_db()
    if "." in target:
        source_name, column = target.split(".", 1)
    else:
        source_name, column = target, None

    rows = db.get_impact(source_name=source_name, column=column, max_depth=depth)
    if not rows:
        console.print(f"[yellow]No features depend on {target}.[/yellow]")
        return

    console.print(f"[bold]Impact of {target}[/bold] — [cyan]{len(rows)}[/cyan] downstream feature(s)")
    current_depth = -1
    for r in rows:
        if r["depth"] != current_depth:
            current_depth = r["depth"]
            label = "direct" if current_depth == 1 else f"depth {current_depth}"
            console.print(f"\n[dim]{label}[/dim]")
        console.print(f"  [cyan]{r['name']}[/cyan]  [dim]({r['dtype']})[/dim]  via [magenta]{r['via']}[/magenta]")


# =========================================================================
# Lineage subcommands (T1.1b — sqlglot auto-detect)
# =========================================================================


@lineage_app.command("detect")
def lineage_detect(
    from_: list[str] = typer.Option(  # noqa: B008
        ...,
        "--from",
        "-f",
        help="SQL file(s) or glob(s) to scan. Repeat the flag or pass shell-expanded paths.",
    ),
    dialect: str = typer.Option(
        "postgres",
        "--dialect",
        "-d",
        help="sqlglot dialect (postgres|snowflake|bigquery|mysql|sqlite|...). Default: postgres.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Write proposed edges to the catalog. Without this flag, just print a summary.",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="With --apply, skip the interactive confirmation prompt (for scripts / CI).",
    ),
) -> None:
    """Auto-detect feature lineage from SQL transformation files.

    Parses each file with sqlglot, extracts ``output_table.column ←
    input_table.column`` edges, and either prints a summary or writes them
    to the catalog. Unmatched parents (columns whose table isn't in the
    catalog as either a feature or a data source) are skipped with a
    warning instead of erroring.

    Requires the optional ``[lineage-sql]`` extra:

        uv pip install 'featcat[lineage-sql]'

    Examples:

        featcat lineage detect --from sql/transforms/*.sql
        featcat lineage detect --from sql/sessions.sql --dialect snowflake
        featcat lineage detect --from sql/*.sql --apply --confirm
    """
    try:
        from .lineage import detect_lineage_from_file
    except ImportError:
        console.print(
            r"[red]sqlglot is required.[/red] Install with: [cyan]uv pip install 'featcat\[lineage-sql]'[/cyan]"
        )
        raise typer.Exit(1) from None

    paths = _expand_sql_globs(from_)
    if not paths:
        console.print("[yellow]No SQL files matched the --from patterns.[/yellow]")
        raise typer.Exit(1)

    all_edges = []
    for p in paths:
        try:
            edges = detect_lineage_from_file(p, dialect=dialect)
        except ImportError:
            console.print(
                r"[red]sqlglot is required.[/red] Install with: [cyan]uv pip install 'featcat\[lineage-sql]'[/cyan]"
            )
            raise typer.Exit(1) from None
        except OSError as e:
            console.print(f"[yellow]Skipping {p}: {e}[/yellow]")
            continue
        all_edges.extend(edges)

    if not all_edges:
        console.print("[yellow]No lineage edges detected.[/yellow]")
        return

    # Print summary table.
    table = Table(title=f"Proposed lineage edges ({len(all_edges)})")
    table.add_column("Child", style="cyan")
    table.add_column("Parent", style="magenta")
    table.add_column("Transform", style="dim", overflow="fold")
    table.add_column("Source")
    for edge in all_edges:
        loc = ""
        if edge.source_file:
            loc = f"{Path(edge.source_file).name}"
            if edge.source_line is not None:
                loc += f":{edge.source_line}"
        table.add_row(edge.child, edge.parent, edge.transform, loc)
    console.print(table)

    if not apply:
        console.print("\n[dim]Preview only. Run with [cyan]--apply --confirm[/cyan] to write edges.[/dim]")
        return

    if not confirm and not typer.confirm(
        f"Write {len(all_edges)} lineage edges to the catalog?",
        default=False,
    ):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    db = _get_db()
    written, skipped = _apply_proposed_edges(db, all_edges)
    console.print(f"[green]Wrote {written} edge(s).[/green] [dim]Skipped {skipped} (unknown child or parent).[/dim]")


def _expand_sql_globs(patterns: list[str]) -> list[Path]:
    """Expand a list of SQL paths/globs into a sorted, deduplicated list of
    files. Plain non-glob paths pass through; missing paths are dropped
    silently (typer prints the original ``--from`` value if everything
    misses).
    """
    import glob as _glob

    seen: set[Path] = set()
    out: list[Path] = []
    for pat in patterns:
        # Shells (zsh/bash with glob) usually expand globs before they
        # reach us, but pass-through globs still work for users who quote
        # the pattern.
        matches = _glob.glob(pat, recursive=True)
        if matches:
            for m in matches:
                p = Path(m)
                if p.is_file() and p not in seen:
                    seen.add(p)
                    out.append(p)
        else:
            p = Path(pat)
            if p.is_file() and p not in seen:
                seen.add(p)
                out.append(p)
    return sorted(out)


def _apply_proposed_edges(db, edges) -> tuple[int, int]:
    """Resolve each ProposedEdge against the catalog and write it.

    Returns ``(written, skipped)``. We try, in order:

    1. Look up the child by name. If it doesn't exist in the catalog, skip
       (we can't dangle an edge off a missing feature).
    2. Look up the parent by feature name → ``add_lineage``.
    3. If parent isn't a feature, split on the first dot and look up the
       source name → ``add_source_lineage``.
    4. Otherwise skip with a warning.
    """
    written = 0
    skipped = 0
    for edge in edges:
        child = db.get_feature_by_name(edge.child)
        if child is None:
            console.print(f"[yellow]  skip:[/yellow] child not in catalog: {edge.child}")
            skipped += 1
            continue

        parent_feature = db.get_feature_by_name(edge.parent)
        if parent_feature is not None:
            # detected_method is a LocalBackend-only kwarg (T1.1a). Pass it
            # via kwargs so RemoteBackend's narrower signature still works.
            try:
                db.add_lineage(child.id, parent_feature.id, edge.transform, detected_method="sql_parse")
            except TypeError:
                db.add_lineage(child.id, parent_feature.id, edge.transform)
            written += 1
            continue

        # Fall back to source-column lookup.
        if "." in edge.parent:
            src_name, col_name = edge.parent.split(".", 1)
            src = db.get_source_by_name(src_name)
            if src is not None and hasattr(db, "add_source_lineage"):
                db.add_source_lineage(
                    child.id,
                    src.id,
                    col_name,
                    transform=edge.transform,
                    detected_method="sql_parse",
                )
                written += 1
                continue

        console.print(f"[yellow]  skip:[/yellow] parent not in catalog: {edge.parent}")
        skipped += 1
    return written, skipped


# =========================================================================
# Lineage demo fixture seeding (lineage seed / lineage clear --demo-only)
# =========================================================================

# Marker values used to identify lineage rows + features created by the demo
# seeder. The `detected_method` column on feature_lineage already accepts
# free-form strings ('manual', 'sql_parse', 'imported'); 'demo' fits the same
# pattern without a schema change. For features we tag them so the existing
# `tag` filter on list_features can find them later.
DEMO_DETECTED_METHOD = "demo"
DEMO_FEATURE_TAG = "demo"
_DEMO_FEATURE_DESC = "Demo feature (auto-created from lineage fixture)"
_DEMO_SOURCE_DESC = "Auto-created by `featcat lineage seed` for demo lineage"


class _LineageFixtureEdge(BaseModel):
    """One edge in a lineage fixture file."""

    child: str
    parent: str
    transformation: str = ""


class _LineageFixture(BaseModel):
    """Top-level schema for `tests/fixtures/lineage-demo.json` and friends."""

    description: str = ""
    version: str = "1.0"
    edges: list[_LineageFixtureEdge]


def _infer_demo_dtype(feature_name: str) -> str:
    """Guess a sensible dtype from the feature-name suffix.

    Demo features have no real data, so the dtype is purely cosmetic — it
    shows up in the lineage graph node label. Aiming for plausible types
    that match what each feature would be in reality.
    """
    col = feature_name.rsplit(".", 1)[-1].lower()
    if col.endswith("_flag") or col.endswith("_anomaly"):
        return "bool"
    if col.endswith("_count") or col.endswith("_id"):
        return "int64"
    return "float64"


def _split_feature_name(name: str) -> tuple[str, str]:
    """Split `source.column` into `(source_name, column_name)`.

    Feature names without a dot are rejected — every feature in a fixture
    must belong to a registered (or auto-creatable) source so the lineage
    graph can colour nodes by source.
    """
    if "." not in name:
        raise ValueError(
            f"Fixture feature name must be 'source.column', got: {name!r}. "
            "Lineage seeding needs a source prefix to bucket the feature."
        )
    src, col = name.split(".", 1)
    if not src or not col:
        raise ValueError(f"Empty source or column in feature name: {name!r}")
    return src, col


def _ensure_demo_source(db, name: str, *, dry_run: bool):
    """Return the source for `name`, creating a placeholder if missing.

    The placeholder path is `/demo/<name>.parquet` — it doesn't have to
    exist on disk; lineage doesn't read source data, only joins by ID. We
    skip path uniqueness collisions by checking name first.
    """
    existing = db.get_source_by_name(name)
    if existing is not None:
        return existing, False
    if dry_run:
        return None, True
    source = db.add_source(
        DataSource(
            name=name,
            path=f"/demo/{name}.parquet",
            description=_DEMO_SOURCE_DESC,
        )
    )
    return source, True


def _ensure_demo_feature(db, full_name: str, *, dry_run: bool):
    """Return the feature for `full_name`, creating a tagged stub if missing.

    Returns ``(feature_or_none, was_created)``. In dry-run mode we return
    ``(None, True)`` for features that would be created; callers should
    only consume the feature object outside dry-run.
    """
    existing = db.get_feature_by_name(full_name)
    if existing is not None:
        return existing, False

    src_name, col_name = _split_feature_name(full_name)
    source, _ = _ensure_demo_source(db, src_name, dry_run=dry_run)
    if dry_run:
        return None, True
    assert source is not None, "non-dry-run must always return a source"
    feature = Feature(
        name=full_name,
        data_source_id=source.id,
        column_name=col_name,
        dtype=_infer_demo_dtype(full_name),
        description=_DEMO_FEATURE_DESC,
        tags=[DEMO_FEATURE_TAG],
    )
    db.upsert_feature(feature)
    # upsert_feature returns the same model we passed in, but re-read so
    # we're sure we have the persisted row (with the source_id resolved).
    persisted = db.get_feature_by_name(full_name)
    return persisted, True


def _load_lineage_fixture(path: Path) -> _LineageFixture:
    """Read a JSON file and validate it against ``_LineageFixture``.

    Raises ``typer.Exit(1)`` with a clear console message on parse or
    schema errors — callers shouldn't need to handle JSONDecodeError or
    pydantic.ValidationError directly.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        console.print(f"[red]Could not read fixture {path}:[/red] {e}")
        raise typer.Exit(1) from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON in {path}:[/red] {e}")
        raise typer.Exit(1) from None
    try:
        return _LineageFixture.model_validate(data)
    except Exception as e:  # pydantic.ValidationError, but kept loose to avoid the import.
        console.print(f"[red]Fixture schema validation failed:[/red] {e}")
        raise typer.Exit(1) from None


@lineage_app.command("seed")
def lineage_seed(
    fixture_file: Path = typer.Argument(  # noqa: B008
        ...,
        exists=True,
        readable=True,
        help="Path to a lineage fixture JSON file (see tests/fixtures/lineage-demo.json).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print what would be created without writing to the catalog.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-create lineage edges that already exist (transforms get updated).",
    ),
) -> None:
    """Import lineage edges from a JSON fixture, auto-creating any missing
    features and sources as demo stubs.

    Stub features get tag ``demo`` and edges get ``detected_method='demo'``
    so ``featcat lineage clear --demo-only`` can roll the whole thing back.
    Existing features and edges (created by real workflows) are never
    touched.

    Examples:

        featcat lineage seed tests/fixtures/lineage-demo.json --dry-run
        featcat lineage seed tests/fixtures/lineage-demo.json
    """
    fixture = _load_lineage_fixture(fixture_file)
    if not fixture.edges:
        console.print("[yellow]Fixture has no edges. Nothing to do.[/yellow]")
        return

    db = _get_db()

    # Plan phase — compute, before touching the DB, what's new vs. existing.
    # We resolve every feature name once (set), then walk edges to count
    # new/duplicate. In dry-run we stop here and print; otherwise we proceed
    # to the apply phase below.
    unique_features: list[str] = []
    seen: set[str] = set()
    for edge in fixture.edges:
        for name in (edge.child, edge.parent):
            if name not in seen:
                seen.add(name)
                unique_features.append(name)

    sources_to_create: list[str] = []
    features_to_create: list[str] = []
    for fname in unique_features:
        src_name, _ = _split_feature_name(fname)
        if db.get_source_by_name(src_name) is None and src_name not in sources_to_create:
            sources_to_create.append(src_name)
        if db.get_feature_by_name(fname) is None:
            features_to_create.append(fname)

    console.print(f"[bold]Loading fixture:[/bold] {fixture_file}")
    console.print(
        f"Found [cyan]{len(fixture.edges)}[/cyan] edge(s) across [cyan]{len(unique_features)}[/cyan] feature(s)."
    )

    if sources_to_create:
        console.print(f"\n[bold]Sources to auto-create ({len(sources_to_create)}):[/bold]")
        for s in sources_to_create:
            console.print(f"  - [magenta]{s}[/magenta] (path: /demo/{s}.parquet)")

    if features_to_create:
        console.print(f"\n[bold]Features to auto-create ({len(features_to_create)}):[/bold]")
        for fname in features_to_create:
            console.print(f"  - [cyan]{fname}[/cyan] ({_infer_demo_dtype(fname)})")

    if dry_run:
        console.print(f"\n[bold]Edges to seed ({len(fixture.edges)}):[/bold]")
        for edge in fixture.edges:
            console.print(f"  - [cyan]{edge.child}[/cyan] <- [magenta]{edge.parent}[/magenta]")
        console.print("\n[dim]Dry run — no changes written. Re-run without --dry-run to apply.[/dim]")
        return

    # Apply phase — ensure sources and features first so we can resolve IDs
    # for each edge.
    sources_created = 0
    for src_name in sources_to_create:
        _, was_new = _ensure_demo_source(db, src_name, dry_run=False)
        if was_new:
            sources_created += 1

    features_created = 0
    for fname in features_to_create:
        _, was_new = _ensure_demo_feature(db, fname, dry_run=False)
        if was_new:
            features_created += 1

    edges_created = 0
    edges_skipped = 0
    edges_replaced = 0
    for edge in fixture.edges:
        child = db.get_feature_by_name(edge.child)
        parent = db.get_feature_by_name(edge.parent)
        # Should never happen — we just ensured both above.
        assert child is not None and parent is not None
        if _lineage_edge_exists(db, child.id, parent.id):
            if force:
                db.remove_lineage(child.id, parent.id)
                _insert_demo_lineage_edge(db, child.id, parent.id, edge.transformation)
                edges_replaced += 1
            else:
                edges_skipped += 1
            continue
        _insert_demo_lineage_edge(db, child.id, parent.id, edge.transformation)
        edges_created += 1

    console.print(
        f"\n[green]Created {sources_created} source(s), {features_created} feature(s), {edges_created} edge(s).[/green]"
    )
    if edges_replaced:
        console.print(f"[yellow]Replaced {edges_replaced} existing edge(s) (--force).[/yellow]")
    if edges_skipped:
        console.print(f"[dim]Skipped {edges_skipped} duplicate edge(s). Use --force to re-create.[/dim]")
    console.print("\n[dim]View the lineage graph at http://localhost:8000/lineage[/dim]")


def _lineage_edge_exists(db, child_feature_id: str, parent_feature_id: str) -> bool:
    """Return True iff a feature→feature lineage row exists for this pair.

    The seeder uses this to count duplicates (without --force) and decide
    whether to replace (with --force). Source-column edges live in the
    same table but are keyed differently — the demo fixture doesn't emit
    them, so we only check the feature→feature case.
    """
    with db.session() as s:
        row = s.execute(
            text(
                "SELECT 1 FROM feature_lineage "
                "WHERE parent_type = 'feature' "
                "  AND child_feature_id = :cid AND parent_feature_id = :pid"
            ),
            {"cid": child_feature_id, "pid": parent_feature_id},
        ).first()
        return row is not None


def _insert_demo_lineage_edge(db, child_feature_id: str, parent_feature_id: str, transform: str) -> None:
    """Insert a demo feature→feature lineage row directly.

    Why not just call ``db.add_lineage``? That method's ON CONFLICT clause
    targets the widened 5-column unique constraint that landed in the T1.1
    SQLAlchemy model (``uq_feature_lineage_pair``). Catalogs created before
    T1.1 keep the old 2-column ``UNIQUE(child_feature_id, parent_feature_id)``
    constraint — ``init_db`` adds the new columns via ALTER TABLE but doesn't
    rebuild the constraint, so the ON CONFLICT clause fails to resolve.

    The seeder already pre-checks duplicates via ``_lineage_edge_exists``
    so we don't need conflict resolution here — a plain INSERT works on
    both legacy and current schemas.
    """
    import uuid
    from datetime import datetime, timezone

    with db.session() as s:
        s.execute(
            text(
                "INSERT INTO feature_lineage "
                "(id, child_feature_id, parent_type, parent_feature_id, "
                " parent_source_id, parent_column, transform, "
                " detected_method, created_at) "
                "VALUES (:id, :cid, 'feature', :pid, NULL, NULL, :transform, "
                "        :method, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "cid": child_feature_id,
                "pid": parent_feature_id,
                "transform": transform,
                "method": DEMO_DETECTED_METHOD,
                "now": datetime.now(timezone.utc),
            },
        )
        s.commit()


@lineage_app.command("clear")
def lineage_clear(
    demo_only: bool = typer.Option(
        False,
        "--demo-only",
        help=(
            "Remove only the rows created by `lineage seed` "
            "(detected_method='demo' edges + 'demo'-tagged stub features)."
        ),
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt.",
    ),
) -> None:
    """Remove demo lineage seeded by `featcat lineage seed`.

    Currently only ``--demo-only`` is supported — clearing real lineage
    needs a different UX and isn't part of this command. Pass ``--yes`` to
    skip the prompt (useful from scripts).
    """
    if not demo_only:
        console.print(
            "[red]Refusing to clear without --demo-only.[/red] "
            "Mass lineage deletion is not supported via this command yet."
        )
        raise typer.Exit(2)

    db = _get_db()

    # Count first so we can report exactly what we'll touch (and skip the
    # confirmation entirely when there's nothing to do).
    with db.session() as s:
        edge_count = int(
            s.execute(
                text("SELECT COUNT(*) FROM feature_lineage WHERE detected_method = :m"),
                {"m": DEMO_DETECTED_METHOD},
            ).scalar()
            or 0
        )
    demo_features = db.list_features(tag=DEMO_FEATURE_TAG)
    if edge_count == 0 and not demo_features:
        console.print("[yellow]No demo lineage or features found. Nothing to clear.[/yellow]")
        return

    console.print(
        f"Will remove [cyan]{edge_count}[/cyan] demo edge(s) and [cyan]{len(demo_features)}[/cyan] demo feature(s)."
    )
    if not yes and not typer.confirm("Proceed?", default=False):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    # Delete demo edges first so the feature delete doesn't have to cascade
    # them (it would, via FK ON DELETE CASCADE, but explicit is clearer for
    # the user-visible counters).
    with db.session() as s:
        s.execute(
            text("DELETE FROM feature_lineage WHERE detected_method = :m"),
            {"m": DEMO_DETECTED_METHOD},
        )
        s.commit()

    removed_features = db.bulk_delete_features([f.id for f in demo_features]) if demo_features else 0

    # Identify and drop demo sources that are now empty (no remaining
    # features). Real sources that happened to share a name with the
    # fixture are untouched because they were created with a different
    # description; we filter on that.
    demo_sources = [
        s for s in db.list_sources() if s.description == _DEMO_SOURCE_DESC and not db.list_features(source_name=s.name)
    ]
    removed_sources = 0
    for src in demo_sources:
        try:
            db.delete_source(src.name)
            removed_sources += 1
        except KeyError:
            pass  # Race with another caller — fine.

    console.print(
        f"[green]Removed {edge_count} edge(s), {removed_features} feature(s), {removed_sources} source(s).[/green]"
    )


@lineage_edge_app.command("add")
def lineage_edge_add(
    child: str = typer.Argument(help="Child feature name (the derived feature)"),
    parent: str = typer.Argument(help="Parent feature name (the upstream feature)"),
    transform: str = typer.Option("", "--transform", "-t", help="Free-form transform expression (e.g. SQL)"),
) -> None:
    """Manually add a feature→feature lineage edge.

    Wraps ``LocalBackend.add_lineage`` with ``detected_method='manual'``.
    The DB unique constraint makes inserts idempotent (re-adding the same
    edge is a no-op).
    """
    db = _get_db()
    try:
        child_feat = db.get_feature_by_name(child)
        if child_feat is None:
            console.print(f"[red]Child feature not found:[/red] {child}")
            raise typer.Exit(1)
        parent_feat = db.get_feature_by_name(parent)
        if parent_feat is None:
            console.print(f"[red]Parent feature not found:[/red] {parent}")
            raise typer.Exit(1)
        db.add_lineage(
            child_feature_id=child_feat.id,
            parent_feature_id=parent_feat.id,
            transform=transform,
            detected_method="manual",
        )
        console.print(f"[green]Added lineage edge:[/green] {child} <- {parent}")
    finally:
        db.close()


@lineage_edge_app.command("rm")
def lineage_edge_rm(
    child: str = typer.Argument(help="Child feature name"),
    parent: str = typer.Argument(help="Parent feature name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove a feature→feature lineage edge.

    Source-column edges (parent_type='source_column') are not removable
    through this command — see ``featcat lineage clear --demo-only`` for
    bulk removal of seeded edges.
    """
    db = _get_db()
    try:
        child_feat = db.get_feature_by_name(child)
        if child_feat is None:
            console.print(f"[red]Child feature not found:[/red] {child}")
            raise typer.Exit(1)
        parent_feat = db.get_feature_by_name(parent)
        if parent_feat is None:
            console.print(f"[red]Parent feature not found:[/red] {parent}")
            raise typer.Exit(1)
        if not _lineage_edge_exists(db, child_feat.id, parent_feat.id):
            console.print(f"[red]Edge not found:[/red] {child} <- {parent}")
            raise typer.Exit(1)
        if not yes and not typer.confirm(f"Remove lineage edge {child} <- {parent}?"):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)
        db.remove_lineage(child_feat.id, parent_feat.id)
        console.print(f"[green]Removed lineage edge:[/green] {child} <- {parent}")
    finally:
        db.close()


# =========================================================================
# Demo commands
# =========================================================================


@demo_app.command("seed")
def demo_seed(
    fixture_file: Path | None = typer.Option(  # noqa: B008
        None, "--fixture", help="Path to a demo-catalog.json (defaults to the bundled fixture)."
    ),
) -> None:
    """Populate the catalog with bundled demo data.

    Demo rows are tagged so ``featcat demo clear`` can remove only them
    without touching real catalog content.
    """
    from .demo import bundled_fixture_path, load_demo_fixture, seed_demo

    path = fixture_file if fixture_file is not None else bundled_fixture_path()
    try:
        fixture = load_demo_fixture(path)
    except ValueError as e:
        console.print(f"[red]Fixture error:[/red] {e}")
        raise typer.Exit(1) from None

    db = _get_db()
    try:
        stats = seed_demo(db, fixture)
    finally:
        db.close()

    console.print(
        f"[green]Seeded demo catalog:[/green]\n"
        f"  sources:  +{stats.sources_created}\n"
        f"  features: +{stats.features_created}\n"
        f"  docs:     +{stats.docs_created}\n"
        f"  groups:   +{stats.groups_created}\n"
        f"  lineage:  +{stats.lineage_edges_created}"
    )
    console.print("\n[dim]To remove: featcat demo clear[/dim]")


@demo_app.command("clear")
def demo_clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Remove every demo-tagged row from the catalog. Real data is preserved."""
    from .demo import clear_demo

    if not yes and not typer.confirm("Remove all demo data from this catalog?", default=False):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    db = _get_db()
    try:
        stats = clear_demo(db)
    finally:
        db.close()

    console.print(
        f"[green]Cleared demo data:[/green]\n"
        f"  sources:  -{stats.sources_removed}\n"
        f"  features: -{stats.features_removed}\n"
        f"  docs:     -{stats.docs_removed}\n"
        f"  groups:   -{stats.groups_removed}\n"
        f"  lineage:  -{stats.lineage_edges_removed}"
    )


# =========================================================================
# Backup / restore
# =========================================================================


@backup_app.callback()
def backup_root(
    ctx: typer.Context,
    output: Path | None = typer.Option(  # noqa: B008
        None,
        "--output",
        "-o",
        help="Path to the backup archive (.tar.gz). Default: ./catalog-backup-<ts>.tar.gz",
    ),
) -> None:
    """Create a backup archive of the current catalog."""
    if ctx.invoked_subcommand is not None:
        return
    _backup_create(output)


@backup_app.command("list")
def backup_list_cmd(
    directory: Path = typer.Option(  # noqa: B008
        Path("."), "--dir", "-d", help="Directory to scan for *.tar.gz backup archives."
    ),
) -> None:
    """List backup archives in a directory."""
    archives = sorted(directory.glob("*.tar.gz"))
    if not archives:
        console.print(f"[dim]No backup archives in {directory}[/dim]")
        return
    table = Table(title=f"Backups in {directory}")
    table.add_column("File")
    table.add_column("Size")
    table.add_column("Created")
    for archive in archives:
        size_mb = archive.stat().st_size / 1024 / 1024
        meta = _read_archive_metadata(archive)
        created = meta.created_at.isoformat() if meta else "(unreadable metadata)"
        table.add_row(archive.name, f"{size_mb:.2f} MB", created)
    console.print(table)


@app.command("restore")
def restore_cmd(
    input_path: Path = typer.Option(  # noqa: B008
        ...,
        "--input",
        "-i",
        exists=True,
        readable=True,
        help="Path to a backup archive (.tar.gz) created by `featcat backup`.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite the destination catalog even if it has data."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Restore a catalog from a backup archive."""
    import tempfile

    from .backup import restore_catalog, unpack_archive
    from .backup.metadata import BackupMetadata
    from .backup.restore import RestoreError

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            dump_dir = unpack_archive(input_path, Path(tmpdir))
        except Exception as e:
            console.print(f"[red]Could not unpack archive:[/red] {e}")
            raise typer.Exit(1) from None

        try:
            meta = BackupMetadata.model_validate_json((dump_dir / "metadata.json").read_text(encoding="utf-8"))
        except Exception as e:
            console.print(f"[red]Invalid backup metadata:[/red] {e}")
            raise typer.Exit(1) from None

        console.print("[bold]Backup metadata[/bold]")
        console.print(f"  Created:        {meta.created_at}")
        console.print(f"  Featcat version: {meta.featcat_version}")
        console.print(f"  Backend:         {meta.backend} {meta.backend_version}")
        console.print(f"  Stats:           {meta.stats}")

        db = _get_db()
        current = db.get_catalog_stats()
        non_empty = int(current.get("sources", 0) or 0) > 0 or int(current.get("features", 0) or 0) > 0
        if non_empty and not force:
            console.print(
                f"[yellow]Current catalog has {current.get('sources', 0)} sources / "
                f"{current.get('features', 0)} features — restore will REPLACE them.[/yellow]"
            )
            if not yes and not typer.confirm("Proceed?", default=False):
                console.print("[yellow]Aborted.[/yellow]")
                db.close()
                raise typer.Exit(0)
            force = True

        try:
            counts = restore_catalog(db, dump_dir, force=force)
        except RestoreError as e:
            console.print(f"[red]Restore failed:[/red] {e}")
            db.close()
            raise typer.Exit(1) from None
        finally:
            db.close()

        total = sum(counts.values())
        console.print(f"[green]Restored {total} rows across {len(counts)} tables from {input_path.name}[/green]")


def _backup_create(output: Path | None) -> None:
    """Shared body for the `backup` callback."""
    import tempfile
    from datetime import datetime

    from .backup import dump_catalog, pack_archive

    if output is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = Path(f"./catalog-backup-{ts}.tar.gz")

    db = _get_db()
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            stem = output.name
            if stem.endswith(".tar.gz"):
                stem = stem[: -len(".tar.gz")]
            elif output.suffix:
                stem = output.stem
            dump_dir = Path(tmpdir) / stem
            dump_dir.mkdir(parents=True)
            metadata, _ = dump_catalog(db, dump_dir)
            pack_archive(dump_dir, output)
    finally:
        db.close()

    size_mb = output.stat().st_size / 1024 / 1024
    console.print(
        f"[green]Backup created:[/green] {output} ({size_mb:.2f} MB)\n"
        f"  sources:  {metadata.stats.get('sources', 0)}\n"
        f"  features: {metadata.stats.get('features', 0)}\n"
        f"  groups:   {metadata.stats.get('groups', 0)}\n"
        f"  edges:    {metadata.stats.get('lineage_edges', 0)}"
    )


def _read_archive_metadata(archive: Path):
    """Return BackupMetadata for an archive, or None if unreadable."""
    import tarfile

    from .backup.metadata import BackupMetadata

    try:
        with tarfile.open(archive, "r:gz") as tf:
            for m in tf.getmembers():
                if m.name.endswith("/metadata.json"):
                    f = tf.extractfile(m)
                    if f is None:
                        return None
                    return BackupMetadata.model_validate_json(f.read().decode("utf-8"))
    except Exception:
        return None
    return None


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
        console.print("[red]TUI requires textual.[/red] Install with: uv pip install 'featcat[tui]'")
        raise typer.Exit(1) from None


@app.command("build")
def build(
    entities: str = typer.Option(..., "--entities", help="Local parquet entity dataframe path"),
    source: str | None = typer.Option(None, "--source", help="Local parquet source dataframe path"),
    source_name: str | None = typer.Option(None, "--source-name", help="Registered DataSource name"),
    entity_key: str | None = typer.Option(None, "--entity-key", help="Entity/join key column"),
    entity_timestamp: str | None = typer.Option(None, "--entity-timestamp", help="Entity timestamp column"),
    source_timestamp: str | None = typer.Option(None, "--source-timestamp", help="Source event timestamp column"),
    features: str = typer.Option(..., "--features", help="Comma-separated feature columns"),
    output: str | None = typer.Option(None, "--output", "-o", help="Local parquet output path"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Build a local point-in-time training dataset."""
    dataset_build(
        entities=entities,
        source=source,
        source_name=source_name,
        entity_key=entity_key,
        entity_timestamp=entity_timestamp,
        source_timestamp=source_timestamp,
        features=features,
        output=output,
        json_output=json_output,
    )


@app.command("get")
def get(
    entities: Path = typer.Option(  # noqa: B008
        ...,
        "--entities",
        "-e",
        help="JSONL file with entity key objects",
    ),
    features: str = typer.Option(..., "--features", "-f", help="Comma-separated feature refs"),
    project: str = typer.Option("", "--project", help="Project namespace"),
    feature_view: str = typer.Option("", "--feature-view", help="Feature view namespace"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Read online feature values for entity keys from a JSONL file."""
    online_get(
        entities=entities,
        features=features,
        project=project,
        feature_view=feature_view,
        json_output=json_output,
    )


@app.command("write")
def write(
    input_path: Path = typer.Option(  # noqa: B008
        ...,
        "--input",
        "-i",
        help="JSONL file with online feature write rows",
    ),
    project: str = typer.Option("", "--project", help="Project namespace"),
    feature_view: str = typer.Option("", "--feature-view", help="Feature view namespace"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Emit structured JSON"),
) -> None:
    """Write online feature values from a JSONL file."""
    online_write(
        input_path=input_path,
        project=project,
        feature_view=feature_view,
        json_output=json_output,
    )


@app.command("scan")
def scan(
    name: str = typer.Argument(help="Name of the data source to scan"),
) -> None:
    """Scan a data source and auto-register features."""
    source_scan(name=name)


# =========================================================================
# Helpers
# =========================================================================


def _print_check(ok: bool, message: str) -> None:
    marker = "[green][x][/green]" if ok else "[red][ ][/red]"
    console.print(f"  {marker} {message}")


if __name__ == "__main__":
    app()
