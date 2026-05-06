# AI assistant

featcat ships with a chat-based AI assistant that knows your catalog. It's grounded — it answers from the actual features and docs in your DB via [tool calls](../architecture/ai.md) *(coming soon)*, not from training-data memorization. You can ask it to find features, compare them, summarize drift, or write SQL.

## When to use it

- **"What features do we have for X?"** — faster than scanning the catalog manually.
- **"Compare these three features."** — pulls stats, descriptions, lineage in one go.
- **"Why is `session_count_30d` drifting?"** — it'll fetch the drift report and the recent stats, and try to explain.
- **"Write SQL to compute a 30-day rolling user count."** — uses the catalog for grounding (right column names, right source).

It's not a replacement for the catalog browser — for "show me everything tagged churn" the filter UI is faster. The assistant shines on questions that are tedious to answer with clicks.

## Opening a chat

=== "Web UI"

    1. Open `http://localhost:8000` → **Chat** (sidebar)
    2. Type your question
    3. Watch the agent think (`<thinking>` block), call tools, and stream the answer
    4. Click suggested follow-up prompts under the answer

=== "API"

    Streaming SSE endpoint:

    ```bash
    curl -N -X POST http://localhost:8000/api/ai/chat \
        -H 'Content-Type: application/json' \
        -d '{"messages": [{"role": "user", "content": "list features for churn"}]}'
    ```

    Events: `thinking_start` / `thinking` / `thinking_end` / `tool_call` / `tool_result` / `token` / `done`.

## What tools it has

Five tools, defined in `featcat/ai/tools.py`:

| Tool | Purpose |
|---|---|
| `search_catalog` | Free-text search over names/descriptions/tags |
| `get_feature_detail` | Full feature record + stats + doc |
| `compare_features` | Side-by-side stats and descriptions |
| `find_similar_features` | Embedding-based similarity (pgvector) or TF-IDF fallback |
| `get_drift_report` | Latest `monitoring_checks` aggregation |

The agent picks tools, runs them, then synthesizes an answer. Max 2 tool rounds per query (configurable). Duplicate tool calls are detected and short-circuited so it can't loop.

## Grounding

The agent's system prompt instructs it to answer **only from tool results**, not from priors. If it can't find what you asked about, it'll tell you instead of inventing.

```
> "What's the dtype of user_behavior.session_count_30d?"
[tool: get_feature_detail user_behavior.session_count_30d] → int64
The dtype is int64.
```

```
> "What's the dtype of feature_we_never_built?"
[tool: search_catalog feature_we_never_built] → []
I couldn't find that feature in the catalog. Did you mean
session_count_30d or event_count_30d?
```

## Streaming

Every response streams. You'll see thinking tokens (rendered in italics, collapsible), tool calls (rendered as a card with the call + result preview), then the answer streaming token-by-token.

Behind the scenes: the API uses llama.cpp's `/v1/chat/completions` endpoint with `stream=true` and yields SSE events to the browser. The frontend reads the EventSource and renders incrementally.

## Bilingual

The chat detects Vietnamese vs English from your input and responds in the same language (`featcat/utils/lang.py`). Feature names and JSON keys stay in English regardless. System prompts stay in English so the model behaves consistently.

```
> "Có feature nào đo session 30 ngày không?"
[tool: search_catalog ...]
Có 3 feature liên quan: user_behavior.session_count_30d (...), …
```

## Configuration

Server-side env vars:

```bash
FEATCAT_LLM_BACKEND=llamacpp           # only supported backend today
FEATCAT_LLM_BASE_URL=http://llm:8080   # llama.cpp server
FEATCAT_LLM_MODEL=gemma-4-E2B-it-Q4_K_M
FEATCAT_LLM_MAX_TOOL_ROUNDS=2
FEATCAT_LLM_TIMEOUT_SECONDS=180
```

The default model returns `<think>...</think>` blocks before the answer. featcat detects and renders these as a separate "thinking" channel so the user sees the chain of thought without it polluting the final answer.

## Caveats

- **No memory across sessions** today. Each chat is fresh — the agent doesn't remember prior conversations.
- **Tool budget is 2 rounds.** Complex multi-hop questions (e.g. "find features that drifted last week and have no owner") may need to be asked in two parts.
- **Cold start ~30s** while llama.cpp loads the model. Subsequent calls are fast.
- **Token budget is bounded** — long catalog dumps are truncated. Ask for a count first, then a sample.

## Related

- **[Architecture › AI Layer](../architecture/ai.md)** *(coming soon)* — agent loop, tool spec
- **[Catalog browser](catalog.md)** — when the assistant is overkill
- **[SDK Quickstart](../sdk/quickstart.md)** — programmatic alternative for repeatable queries
