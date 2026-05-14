# Sandbox UAT run — <run-id>

| Field            | Value |
|------------------|-------|
| Sandbox id       | `<YYYYMMDD-HHMMSS-PID>` |
| Host profile     | `local` / `lab` |
| Git SHA          | `<rev-parse HEAD>` |
| Image tags       | `<nxank4/featcat:VERSION>`, `<llama.cpp commit>`, `<pgvector tag>` |
| Model file       | `gemma-4-E2B-it-Q4_K_M.gguf` (size, sha256) |
| Host OS / kernel | `<uname -a>` |
| Docker version   | `<docker --version>` |
| Date (UTC)       | `<YYYY-MM-DDTHH:MM:SSZ>` |
| Operator         | `<name>` |

---

## Scenario a — Install path

- **Time taken:** _e.g. 2m10s_
- **Steps that worked:**
  - _list working steps_
- **Steps that broke:**
  - _list broken steps with verbatim error output_
- **UX confusion:** _what was unclear or surprising_
- **Severity:** `blocker` | `major` | `minor` | `nit`
- **Suggested fix:** _or `n/a — works as designed`_

## Scenario b — Doctor / preflight

- **Time taken:**
- **Steps that worked:**
- **Steps that broke:**
- **UX confusion:**
- **Severity:**
- **Suggested fix:**

## Scenario c — Source registration

- **Time taken:**
- **Steps that worked:**
- **Steps that broke:**
- **UX confusion:**
- **Severity:**
- **Suggested fix:**

## Scenario d — Bulk inventory + browse + search

- **Time taken:**
- **Steps that worked:**
- **Steps that broke:**
- **UX confusion:**
- **Severity:**
- **Suggested fix:**

## Scenario e — Auto-doc

(carry forward into a real run; leave blank until executed)

## Scenario f — Feature Groups

## Scenario g — Feature Definitions

## Scenario h — AI chat (SSE)

## Scenario i — Similarity graph

## Scenario j — PSI timeline

## Scenario k — Documentation Debt Heatmap

## Scenario l — Health Score

## Scenario m — Export to DataFrame

## Scenario n — Versioning + rollback

## Scenario o — Teardown + reproduce

---

## Summary

| Scenario | Status | Severity | Notes |
|----------|--------|----------|-------|
| a — Install path           |   |   |   |
| b — Doctor / preflight     |   |   |   |
| c — Source registration    |   |   |   |
| d — Bulk inventory         |   |   |   |
| e — Auto-doc               |   |   |   |
| f — Feature Groups         |   |   |   |
| g — Feature Definitions    |   |   |   |
| h — AI chat (SSE)          |   |   |   |
| i — Similarity graph       |   |   |   |
| j — PSI timeline           |   |   |   |
| k — Doc Debt heatmap       |   |   |   |
| l — Health Score           |   |   |   |
| m — Export                 |   |   |   |
| n — Versioning             |   |   |   |
| o — Teardown               |   |   |   |

Status legend: `✓` pass, `✗` fail, `~` partial, `-` not run.

---

## Reproduce this run

```bash
# 1. Clone or use an existing featcat checkout at:
#    <path>

# 2. Confirm the LLM model is in place:
ls -l deploy/models/gemma-4-E2B-it-Q4_K_M.gguf

# 3. Start the sandbox.
bash deploy/sandbox/scripts/start-sandbox.sh --profile <local|lab>

# 4. Use the URL / id printed by step 3. Walk through scenarios in this report
#    in order. Capture exact output into the relevant section.

# 5. Tear down.
bash deploy/sandbox/scripts/reset-sandbox.sh --id <id-from-step-3>
```
