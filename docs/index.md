# featcat

> AI-powered feature catalog for data science teams.

featcat is a local-first feature catalog that helps a data team know **what features exist**, **what they mean**, **where they live**, and **whether they're healthy**. It indexes Parquet/CSV sources you point at it, generates documentation via a local LLM, monitors feature drift over time, and exposes everything through a CLI, REST API, web UI, and Python SDK.

## Why featcat

The team grows past a few feature pipelines and the answer to "what should I use for churn prediction?" stops being "ask whoever wrote it last quarter." featcat gives that answer:

- **Discover** features by source, tag, owner, or natural-language query
- **Trust** them via auto-generated documentation, drift checks, and lifecycle status (`draft` → `reviewed` → `certified` → `deprecated`)
- **Reuse** them from notebooks via the [SDK](sdk/quickstart.md) — no copy-pasting Parquet paths
- **Trace** lineage upstream and downstream, so changing a source column shows you which features break

## When to use it

- You've got more than ~20 features across multiple Parquet sources and Slack-asking is now the bottleneck.
- You want feature documentation that's actually maintained — featcat generates it from data + (optional) hints and monitors freshness.
- Your team mixes English and Vietnamese — featcat detects the input language and responds in kind.

## When *not* to use it

- You have a managed feature store already (Feast, Tecton, Databricks Feature Store) — featcat is a *catalog* layer, not a serving layer. It tells you about features; it doesn't materialize them online.
- Your scale is genuinely big-data — featcat's reference target is **5,000–10,000 features** across **20 sources**. Beyond that, the embedding + tsvector pipelines hold up but UI virtualization assumptions start to fray.

## Three minutes to your first feature

```bash
# Install
uv pip install -e ".[server,embeddings]"
featcat init

# Point at a Parquet
featcat source add user_behavior /data/user_behavior.parquet
featcat source scan user_behavior

# Browse it
featcat feature list                           # CLI
featcat serve --host 0.0.0.0 --port 8000       # Web UI at :8000
```

Or from a notebook:

```python
from featcat_client import FeatCatClient
client = FeatCatClient("http://localhost:8000")

df = client.read_feature("user_behavior.session_count_30d")
similar = client.find_similar("user_behavior.session_count_30d", top_k=5)
```

→ [Full installation guide](getting-started/installation.md) · [First feature walkthrough](getting-started/first-feature.md) · [Notebook quickstart](getting-started/notebook-quickstart.md)

## Where to go next

| If you want to… | Read |
|---|---|
| Stand up featcat locally | [Installation](getting-started/installation.md) |
| Catalog your first source | [First Feature](getting-started/first-feature.md) |
| Pull data into a notebook | [Notebook Quickstart](getting-started/notebook-quickstart.md) |
| Use the Python SDK | [SDK Quickstart](sdk/quickstart.md) |
| Understand what's running where | [Architecture Overview](architecture/overview.md) |
| Deploy to production | [Deployment Guide](ops/deployment.md) |

## Links

- **Repo**: [github.com/codepawl/featcat](https://github.com/codepawl/featcat)
- **Issues**: report bugs or request features in the GitHub tracker
- **Plan docs**: `.claude/plan/featcat-scaleup-tasks.md` in the repo for the long-term roadmap
