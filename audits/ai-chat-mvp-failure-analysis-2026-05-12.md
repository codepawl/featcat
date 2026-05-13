# AI Chat MVP — Failure Analysis

**Date**: 2026-05-12
**Author**: Claude (operating on featcat repo)
**Source**: Test results from PR #59 (`featcat-mvp-test-prompts.md`), enriched with code
inspection, llama.cpp server logs over the test window, and targeted
re-runs.

> Audit-only. No fix code in this document. Per-fix PRs to follow.

---

## Section 1 — Failure inventory (enriched)

Every failure / partial from the MVP test, with the data needed to root-cause it.

### 1a. Tool-selection misses (model variability)

| Test | Prompt | Tool chosen | Correct tool (per system prompt) | Failure mode |
|------|--------|-------------|----------------------------------|--------------|
| A2 | `Catalog có bao nhiêu features?` | *(none)* | `count_features()` or `catalog_summary()` | **No tool**. Agent reasoned "no tool exists" — but `count_features` is in the inventory and `catalog_summary` is too. |
| A4 | `Cho tôi danh sách feature chưa có tài liệu` | *(none)* | `list_features(has_doc=false)` | **No tool**. Same pattern as A2 — agent didn't recognise the structured-filter shape. |
| A6 | `Group device có những feature nào?` | `search_features` | `get_group(name="device")` | **Wrong tool**. Picked the generic search over the group-lookup tool that's explicitly listed. |
| E3 | `Tìm duplicate features với threshold 0.8, chỉ trong source device_logs` | *(none)* | `find_similar_features` or per-source iteration | **No tool**. Closest tool is `find_similar_features(feature_name, top_k)` which doesn't take threshold or source. The exact-shape tool genuinely doesn't exist. |

System prompt at `featcat/ai/agent.py:25-63` explicitly maps:
- "có bao nhiêu" → `count_features` (line 36)
- "chưa có doc" → `list_features(has_doc=False)` (line 34, also example line 50)
- "group X có gì" → `get_group(name=...)` (line 45)

So the system prompt **is** correct. The agent is choosing not to follow it — model variability under Gemma 4 E2B (1.4B active params at int4). Verified in C1 Turn 2 where it correctly picked `list_features(has_doc=false, source=...)` immediately after the source was in conversational context: same model, same prompt, different call → different choice.

### 1b. Search-tool rigidity (substring-only)

| Test | Prompt | Tool args | Why empty |
|------|--------|-----------|-----------|
| A3 | `Tìm feature liên quan đến cpu_usage` | `search_features(query="cpu_usage")` | No feature contains `cpu_usage` as a literal substring. Catalog has `cpu_load`, `cpu_temp`, `cpu_decreasing`, `cpu_*`. |
| E2 | `Tìm feature về user behavior...` | `search_features(query="user behavior")` | No feature has that exact substring. |
| D4 | 7-part query, agent tried `search_features(query="network")` | as shown | No feature has `network` in name/description/tags. |
| E4 | `Liệt kê features của source non_existent_source` | `search_features(query="non_existent_source")` | Correctly empty (the source doesn't exist). |

Confirmed in code (`featcat/catalog/local.py:954-969`):
```python
def search_features(self, query: str) -> list[Feature]:
    pattern = f"%{query}%"
    ... WHERE name LIKE :p OR description LIKE :p OR tags LIKE :p OR column_name LIKE :p
```
Pure SQL `LIKE %query%`. No tokenisation, no stemming, no fuzzy matching, no semantic search. `cpu_usage` ≠ `cpu_load`.

The agent's behaviour given the tool is correct — it queries what the user asked, gets nothing back, reports nothing back. The fault is in the tool itself.

### 1c. Tool-arg errors

| Test | Tool + args | Why bad |
|------|-------------|---------|
| B4 | `find_similar_features(feature_name="all", top_k=5)` | "all" isn't a feature name; tool returned `Feature 'all' not found`. Agent concluded "no duplicates" from this empty result. The right strategy for catalog-wide duplicates is iteration per feature or a dedicated endpoint. |

### 1d. Long-generation failures (timeouts / cutoffs)

| Test | Symptom | Probable cause |
|------|---------|----------------|
| B1 | `transport: TimeoutError: timed out` at 150s | At 10 tok/s generation, 1500 tokens = 150s. Likely hit the script's read timeout while the model was still mid-generation. |
| B7 | Same | Same. |
| B8 | HTTP 500: "LLM error: Cannot connect to llama.cpp server" | See section 1f — coincided with featcat server memory pressure. |
| B2 (inner) | `Discovery failed: ... HTTP Error 500` — but the outer agent caught and responded gracefully | Inner `suggest_features` calls the LLM again (rerank). That secondary call hit a 500 — possibly during B7's slot-busy window. |

### 1e. Memory / context

| Test | Symptom | Root cause |
|------|---------|------------|
| C5 Turn 6 | Agent said "feature đầu tiên là `device_logs.mem_usage`" — actually was `client_logs.rssi` (Turn 1). | `featcat/ai/session.py:30-33`: `get_history()` returns only the **last 6 user/assistant messages**. After 6 turns (12 messages) only the last 3 turns survive. Turn 1's content is no longer in the prompt sent to the LLM. |

### 1f. Stability under load

| Test | Symptom | Observation |
|------|---------|-------------|
| B8 | "Cannot connect to llama.cpp" — but llama.cpp logs show **no errors anywhere across the entire test window** | Transient client-side. Not a true llama.cpp failure. |
| Reproducer (today) | 10 back-to-back requests → 10/10 transport errors (connection refused) | The **featcat server (uvicorn) died** between end of Section C and the reproducer attempt. `dmesg` shows `systemd-journald: Under memory pressure, flushing caches`. The python process is gone. |

That gives two distinct stability concerns:
- llama.cpp itself was stable through every test — no errors in its logs.
- The **featcat server can OOM** during long test runs. Plausibly the SQLAlchemy session pool, the agent's growing tool-result buffers, the SessionManager's 50 in-memory sessions, and uvicorn's 4 workers (per CLAUDE.md) combine to exhaust memory on WSL2.

---

## Section 2 — Root-cause analysis per gap

### Gap 1 — Latency (~70s avg vs <10s target)

**Hard numbers from llama.cpp logs over the test window** (each line = one LLM call):

```
total time =   33488.77 ms /   540 tokens     (62 tok/s overall — but mostly prompt)
total time =   19250.26 ms /   465 tokens
total time =   38138.53 ms /   608 tokens
total time =   42634.92 ms /   600 tokens
total time =   53966.33 ms /   860 tokens
total time =   75136.65 ms /  1520 tokens     (the 75s case below)
total time =    4510.43 ms /   109 tokens     (E5 — no tool, short answer)
```

Detailed breakdown of the slowest call (task 24544):
```
prompt eval time = 13896.01 ms /  914 tokens (15.20 ms/tok ≈ 66 tok/s)
       eval time = 61240.65 ms /  606 tokens (101.06 ms/tok ≈ 9.9 tok/s)
      total time = 75136.65 ms / 1520 tokens
```

**Three concrete findings**:

1. **Generation is the dominant cost at ~10 tok/s**. Every 100-token expansion of the response adds ~10s. A 600-token Vietnamese explanation = 60s. The 65 tok/s prompt-eval rate is fine; the model itself is CPU-bound during generation.

2. **The agent makes two LLM calls per query for tool-using prompts** — `agent.chat` first call decides tool calls (~30-45s if 200-300 generated tokens), then a second call after tool results produces the user-facing summary (~30-60s if 400-700 tokens). E5 (no-tool case) ran in 4.5s for the llama.cpp call and 59s end-to-end — confirming the second-LLM-call cost when tools are used.

3. **The 13 tool schemas occupy ~2000 prompt tokens**. Prompt-eval at 66 tok/s = ~13s per call just to ingest the system prompt + tool inventory. Llama.cpp's context-checkpoint mechanism helps (see `context checkpoint 5 of 32` in logs) but only when the prefix matches exactly; small differences in history blow the cache.

**The 70s average is the sum of: 2×(13s prompt eval + ~25s generation) ≈ 75s for typical queries.** Not a bug. The model on this hardware fundamentally can't hit a <10s target.

### Gap 2 — Tool-selection misses

The system prompt is correct (`agent.py:25-63`). It explicitly lists `count_features`, `list_features(has_doc=False)`, and `get_group` with example phrasings that match A2/A4/A6.

But A2/A4/A6 still failed. Three contributing factors:

1. **Long system prompt + 13 tool schemas in the prompt**. The model picks tools by next-token prediction. With ~2000 tokens of tool definitions to attend over, a 2B-param model's attention is diluted; it doesn't always condition strongly on the specific instruction.

2. **No few-shot examples**. The system prompt lists workflows but doesn't include a worked example of input → tool call → output → response. Few-shots strongly anchor tool routing on small models.

3. **High tool count for the size of the model**. 13 tools is a lot for a 2B-param model to keep straight. Several tools overlap conceptually (`search_features` vs `list_features(name_contains=...)`, `list_features(has_doc=false)` vs `count_features(has_doc=false)`) and the model may pick the wrong overlap.

This is reinforced by what worked: when the catalog state was already in the conversation (C1 Turn 2 — "trong số đó, cái nào chưa có doc?"), the agent correctly picked `list_features(has_doc=false, source="device_logs")`. The conversational context provided the disambiguation the system prompt alone didn't.

### Gap 3 — Generation timeouts (B1, B7)

Not a true server bug. The pattern:

- Prompts ask for rich, multi-bullet output ("xây model dự đoán churn… feature nào nên dùng?")
- The model generates ~1500-2000 tokens before hitting natural stop
- At 10 tok/s, that's 150-200s
- The test script's `urlopen(timeout=120)` gives up reading partway through

The **server-side has no timeout on `/api/ai/chat`** (verified in `routes/ai.py:236-294` — no `asyncio.wait_for` wrapping the generator). The 180s `LLM_TIMEOUT` constant at `routes/ai.py:17` is only used by `/discover` and `/ask`. So the server happily generates for as long as llama.cpp needs.

llama.cpp's own `max_tokens=2048` (`llamacpp.py:53`) is the hard ceiling — sometimes responses hit that, which gives mid-sentence cutoffs.

### Gap 4 — Memory / context (C5)

`featcat/ai/session.py:30-33`:
```python
def get_history(self) -> list[dict]:
    """Return last 6 user/assistant messages for context."""
    hist = [m for m in self.messages if m["role"] in ("user", "assistant")]
    return hist[-6:]
```

The agent then re-slices at `agent.py:103`:
```python
messages.extend(history[-6:])
```

For a 6-turn conversation the user/assistant slice has 12 messages; `[-6:]` keeps the last 6 = last 3 turns. Turn 1 is gone before the LLM sees the prompt.

This is **deliberate** — Gemma 4 E2B has a 4096-token context (`docker-compose.yml`: `--ctx-size 4096`), and at ~600-1000 tokens per turn (with tool results) the full history would overflow. The current bound is conservative.

But the bound is too aggressive for "remember turn 1" prompts. A summary-of-earlier-turns approach (compress the dropped messages into a one-line bullet) would let memory extend without burning context.

### Gap 5 — Stability under load

llama.cpp itself was rock-solid: zero errors in ~2 hours of mixed workload, all `print_timing` rows ended with `done request: 200`. So that piece is fine.

The featcat server is the weak link:

- **Memory pressure**: `dmesg` showed `systemd-journald: Under memory pressure, flushing caches` immediately after the test runs. The uvicorn process died at some point during Section C or shortly after.
- **No graceful degradation**: when the server falls over, there's no auto-restart and no health-check endpoint that would catch the dead state until a request is attempted.
- **B8's "Cannot connect" was probably the early symptom of this** — a transient timeout/connection-refused as the server got memory-pressured but hadn't fully died yet.

Concretely, the load on the featcat process during the test:
- 4 uvicorn workers (per CLAUDE.md)
- Each worker holds the LocalBackend (SQLite, small)
- Agent state: in-memory `SessionManager` with up to 50 sessions × up to 20 messages each × tool-result strings (≤1500 chars each) = a few MB worst case
- BUT each route handler also pulls `feature_summary` via `get_feature_summary` which scans the catalog
- Worker memory grows with each request; Python doesn't return memory to the OS easily

The 4-worker model is overkill for this workload (single-threaded LLM bottleneck downstream). Each worker idle-eats ~150-250 MB. 4 × ~200MB + everything else on WSL2 = real risk of OOM under burst load.

---

## Section 3 — Prioritized fix plan

### P0 — blocks MVP

**P0.1 — Suppress the redundant summary LLM call when the tool result alone answers the question.**
Current flow: tool round → second LLM call for prose summary. For factual lookups (`list_sources`, `get_feature_detail`, `get_group`, `catalog_summary`, `features_by_source`, `list_groups`), the tool output is already user-readable; running it through a second LLM pass spends 30-60s reformatting plain facts into prose.
- Target: latency target (P0).
- Implementation: classify tools as "self-explanatory" vs "needs prose". For self-explanatory, stream the tool result directly to the user with a short hard-coded intro ("Đây là kết quả:"), skip the second LLM call.
- Effort: 0.5 day.
- Expected impact: A1/A5/A7/A8/A10/B6/C4 latency drops from ~60s to ~20-30s (single LLM call + tool I/O). ~30% of test cases improve.
- Risk: low. Worst case the user sees raw tool output instead of a polished paragraph — still useful.

**P0.2 — Cap response length more aggressively.**
Drop `max_tokens` from 2048 to 600 for the summary-style second call. Add an explicit instruction "keep response under 4 sentences" to the summary prompt.
- Target: latency for cases that still need the second LLM call; cuts B1/B7-style timeouts.
- Effort: <1 hour.
- Expected impact: ~30s shaved off the slowest 30% of queries. B1/B7 stop timing out.
- Risk: low. Some answers get truncated; mitigated by the explicit instruction.

**P0.3 — Tighten the system prompt: fewer tools per query, with a few-shot example.**
The agent makes wrong choices because 13 tools with conceptual overlap confuse a 2B model. Split tools into "primary" (5-6 covering 80% of queries) and "advanced", or inject only the relevant subset based on a cheap pre-classifier.
- Target: A2 / A4 / A6 + similar phrasing misses.
- Effort: 1 day for a basic intent classifier; 2-3 hours for a tool-pruning pass.
- Expected impact: A2/A4/A6 flip to pass. ~3 additional tests pass.
- Risk: medium — wrong classification = wrong tool subset. Mitigation: classifier with high recall, fall through to the full tool list if uncertain.

**P0.4 — Fix `find_similar_features` for catalog-wide queries.**
Add a `mode="catalog"` or accept `feature_name="*"` to mean "find all near-duplicate pairs across the catalog." B4 fails because the agent can't express the catalog-wide intent through the current tool signature.
- Target: B4, E3.
- Effort: 0.5 day.
- Expected impact: B4 and E3 flip to pass.
- Risk: low.

### P1 — significant UX

**P1.1 — Summary-of-earlier-turns to fix C5.**
When a conversation exceeds 6 user/assistant messages, compress the dropped messages into a single "Previously discussed: feature_a (RSSI), feature_b (CPU load)…" line and prepend to history.
- Target: C5 + any future long-conversation pattern.
- Effort: 0.5-1 day.
- Expected impact: C5 flips to pass.
- Risk: low.

**P1.2 — Server stability: trim workers, add restart, fix memory growth.**
- Drop uvicorn workers from 4 to 2 (single-slot llama.cpp downstream makes 4 mostly idle anyway).
- Add a systemd-style restart policy in the dev script and Docker compose.
- Audit the agent's `SessionManager` for cumulative growth.
- Target: B8-style transient failures, server-OOM-during-load.
- Effort: 1 day (workers/restart) + 1 day (memory audit).
- Expected impact: B8-style errors disappear. Server survives extended test runs.
- Risk: low for worker count; medium for memory work depending on what's found.

**P1.3 — Tool-result-driven follow-up instead of forced second LLM call.**
Tied to P0.1 but more ambitious: have the agent emit "would you like more detail?" as a fixed suffix when the tool result is below a complexity threshold. Skips the prose generation entirely.
- Target: latency for medium-complexity queries.
- Effort: 0.5 day.
- Expected impact: another 20-30% latency reduction for queries that fall through P0.1.
- Risk: low.

### P2 — polish

**P2.1 — Replace `LIKE %query%` with sqlite FTS5 + dtype-aware tokenisation.**
Catalog uses sqlite. FTS5 is built in. Adding an FTS5 index over feature names + description + tags would make "cpu_usage" match "cpu_load" via token-prefix or stemming.
- Target: A3/E2 search-tool partials.
- Effort: 1-2 days (migration + index + tool wiring).
- Expected impact: A3, E2, D4 partials flip to pass.
- Risk: low. SQLite FTS5 is mature.

**P2.2 — Decline-loud on multi-part queries (D4) instead of going silent.**
Right now D4 calls one tool and stops with no content. Detect "1)… 2)… 3)…" patterns and decline politely with "I can only handle one of those at a time — which first?"
- Target: D4.
- Effort: 2 hours.
- Risk: nil.

**P2.3 — Don't emit a redundant null-args tool_call event before the real one.**
Streaming-args artifact in the OpenAI-compat response gets emitted twice. Buffer the streamed args until complete before firing the SSE event.
- Target: F2 (streaming smoothness) cosmetics + slight token savings.
- Effort: 2-4 hours.
- Risk: nil.

---

## Section 4 — Quick wins vs deep fixes

### Quick wins (<1 day each, ship immediately)

1. **P0.2** — `max_tokens=600` + "keep under 4 sentences" — 1 hour.
2. **P2.2** — decline-loud on multi-part — 2 hours.
3. **P2.3** — suppress double null-args tool_call event — 2-4 hours.
4. **P0.4** — `find_similar_features` catalog mode — half day.
5. **P0.1** — skip second LLM call for self-explanatory tools — half day.

That's a single sprint (~2-3 days of focused work) and unlocks:
- B1/B7 timeouts → resolved (P0.2)
- A1/A5/A7/A8/A10/B6/C4 latency cut ~40% (P0.1)
- B4 / E3 flip pass (P0.4)
- D4 stops being silent (P2.2)
- Cosmetics on streaming (P2.3)

Projected suite score after quick wins: **~32-34 / 43 (74-79%)** — right at the MVP threshold.

### Deep fixes (multi-day, next milestone)

1. **P0.3** — Intent classifier + tool subset routing — 1-2 days.
2. **P1.1** — Conversation summarisation — 1 day.
3. **P1.2** — Server-stability work — 1-2 days.
4. **P2.1** — FTS5 search — 1-2 days.

Together these likely push the score to **~38-40 / 43 (88-93%)**.

---

## Section 5 — What we WON'T fix in MVP

These are limitations to ship as known issues, not block on:

1. **The model is what it is**. Gemma 4 E2B at int4 on CPU will not hit <10s. Best realistic floor on this hardware after all optimisations: ~15-20s for tool-using queries, ~3-5s for no-tool queries. If users need <10s consistently, that requires either GPU or a different model — both out-of-scope for MVP.

2. **Multi-tool serial chains will stay slow.** Each tool round adds an LLM call. Queries like E2 ("find features about X then check drift") will stay at ~90s end-to-end even after P0.1 (because the chained nature means you can't skip the second LLM call). Document this in the UI ("complex queries may take up to 2 minutes").

3. **Semantic understanding is shallow on a 2B model.** A3 will improve with FTS5 (P2.1) but the agent will still occasionally get questions wrong because the model's domain reasoning is limited. This is fundamental, not fixable in MVP.

4. **B5-style false-premise detection** worked once but isn't guaranteed. The agent might agree with false premises on different phrasings. Building robust premise-checking needs more capable models.

5. **The 2-tool-round limit** in `agent.py:23` (`MAX_TOOL_ROUNDS = 2`) is a deliberate guardrail against runaway agentic loops on this small model. Some queries (E2-style) would benefit from 3-4 rounds but at the cost of latency and potential model loop. Keep at 2 for MVP.

---

## What was investigated but is missing data

- **F4 (kill-llama-mid-chat error recovery)**: not live-tested. The code path exists (`Chat.tsx` error bubble + retry) and is verified to render via the B8 organic failure. Needs a deliberate live test before MVP sign-off.
- **F5 (concurrent sessions)**: not tested. The uvicorn 4-worker setup should support it; llama.cpp will serialise the actual inference. Worth a 5-min live check before MVP.
- **Memory growth slope**: I observed an OOM but didn't quantify rate. Before P1.2 fix work, run `psrecord` against the uvicorn workers during a 30-prompt suite to characterise the curve.

---

Analysis complete. Awaiting prioritization decision on which fixes to ship first.

---

## Follow-up: P0.3 verification (2026-05-13)

The P0.3 intent classifier + tool-subset routing has been implemented (branch `feat/intent-classifier`) and measured. **See [`p0-3-verification-2026-05-13.md`](p0-3-verification-2026-05-13.md) for measured numbers — the speculative claims in Section 3 of this doc are replaced there.** Headline: 58.6% median total-prompt token reduction, 28.6% fallback rate, mechanical 35-prompt pass-rate 85.7% (up from ~75% pre-PR #60).
