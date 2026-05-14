# Sandbox fixtures

`synthetic.parquet` is a tiny synthetic dataset (50 rows, ≈ 4 KB) shipped with
the sandbox tooling so a fresh operator can run `featcat scan-bulk /sources`
immediately after the stack comes up.

## Safety

Every value is randomly generated under a fixed seed (`generate_synthetic.py`).
No FPT Telecom customer ID, no real ARPU, no real subscriber data — the
`customer_id` prefix is literally `syn-` so an audit can scan for and reject
non-synthetic rows.

## Schema

| Column            | Type     | Notes |
|-------------------|----------|-------|
| `customer_id`     | string   | `syn-<8-hex>` synthetic identifier |
| `age_bucket`      | string   | one of `18-25 / 26-35 / 36-45 / 46-60 / 60+` |
| `plan_tier`       | string   | one of `bronze / silver / gold / platinum` |
| `arpu_synthetic`  | float64  | uniform `[50_000, 500_000]`, two decimals |
| `usage_gb`        | float64  | uniform `[0.5, 50.0]`, three decimals |
| `churn_flag`      | int64    | 0 / 1 with a 15 % positive rate |
| `signup_month`    | string   | `YYYY-MM` between 2024-01 and 2025-12 |

## Regenerating

```bash
uv pip install polars   # only needed once
python deploy/sandbox/fixtures/generate_synthetic.py
```

The seed is pinned at 2026-05-14 inside `generate_synthetic.py`. Bump the
constant if you intentionally need a different draw; otherwise running the
script must produce a byte-identical parquet so `git diff` stays clean.
