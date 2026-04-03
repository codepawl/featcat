# User Guide

[Tiếng Việt](user-guide-vi.md)

## CLI Reference

### Managing Data Sources

```bash
# Register a local data source
featcat source add <name> <path>
featcat source add device_perf /data/features/device_performance.parquet

# Register an S3 data source
featcat source add user_logs s3://bucket/path/file.parquet

# List all sources
featcat source list

# Scan source -> auto-create features
featcat source scan device_perf
```

### Managing Features

```bash
# List all features
featcat feature list

# Filter by source
featcat feature list --source device_perf

# View feature details
featcat feature info device_perf.cpu_usage

# Add tags
featcat feature tag device_perf.cpu_usage performance infra

# Search (keyword)
featcat feature search "cpu"
```

### AI Discovery

```bash
# Suggest features for a use case
featcat discover "churn prediction for telecom customers"

# Vietnamese queries also work
featcat discover "dự đoán khách hàng rời mạng dựa trên hành vi sử dụng"
```

Output includes:
1. **Existing Features** — matching features ranked by relevance
2. **New Feature Suggestions** — new features to create from existing data
3. **Strategy Summary** — feature engineering strategy overview

### AI Documentation

```bash
# Generate doc for one feature
featcat doc generate device_perf.cpu_usage

# Generate docs for all undocumented features
featcat doc generate

# View doc
featcat doc show device_perf.cpu_usage

# Export to Markdown
featcat doc export
featcat doc export --output docs/my_features.md

# View doc coverage stats
featcat doc stats
```

### Natural Language Query

```bash
# Ask in English
featcat ask "features related to user behavior in the last 30 days"

# Ask in Vietnamese
featcat ask "các feature liên quan đến hành vi người dùng"

# When Ollama is unavailable, automatically falls back to fuzzy search
```

### Quality Monitoring

```bash
# Create baseline (run once initially)
featcat monitor baseline

# Check for drift
featcat monitor check

# Check a specific feature
featcat monitor check device_perf.cpu_usage

# Check with LLM analysis
featcat monitor check --llm

# Check + update baseline
featcat monitor check --refresh-baseline

# Export report
featcat monitor report
```

### System Health

```bash
# Check overall system health
featcat doctor

# View summary statistics
featcat stats

# Export data
featcat export --format json     # JSON
featcat export --format csv      # CSV
featcat export --format markdown  # Markdown
```

### TUI (Terminal UI)

```bash
featcat ui
```

#### Dashboard (key: D)
- Overview: feature count, sources, doc coverage, alerts
- Recent alerts from monitoring
- Quick actions

#### Feature Browser (key: F)
- Feature table on the left (70%) — sortable, filterable by keyword
- Feature detail on the right (30%) — stats, docs, tags
- Search bar at the top for real-time filtering
- Press `/` to focus search

#### Monitoring (key: M)
- Quality check results table with severity colors
- Summary bar: healthy/warning/critical
- Press `R` to run check, `B` to compute baseline

#### AI Chat (key: C)
- Natural language Q&A about features
- Special commands: `/discover <use case>`, `/search <query>`, `/monitor`
- Streaming response from LLM

## Example Workflows

### 1. Starting a New Project

```bash
# Find relevant features for your problem
featcat discover "predict customer churn for internet service"

# View details of suggested features
featcat feature info user_behavior_30d.session_count
featcat feature info user_behavior_30d.complaint_count

# Read documentation
featcat doc show user_behavior_30d.session_count
```

### 2. Adding a New Data Source

```bash
# Register source
featcat source add payment_history /data/features/payment_history.parquet

# Scan
featcat source scan payment_history

# Generate docs
featcat doc generate

# Tag features
featcat feature tag payment_history.late_payment_count billing churn
featcat feature tag payment_history.avg_payment_amount billing revenue
```

### 3. Weekly Data Quality Check

```bash
# Run quality check
featcat monitor check --llm

# Export report
featcat monitor report --output docs/weekly_report.md

# If issues found, investigate
featcat feature info device_perf.cpu_usage
featcat monitor check device_perf.cpu_usage --llm
```

## Tips and Tricks

- **Cache**: Auto-doc and NL query results are cached. Use `--no-cache` to bypass
- **Offline mode**: When Ollama is unavailable, `featcat ask` automatically uses fuzzy search
- **Shell completion**: `featcat --install-completion bash` (or zsh/fish)
- **Quick export**: `featcat export --format json > features.json`
- **Backup**: Just copy `catalog.db` — that's all you need
