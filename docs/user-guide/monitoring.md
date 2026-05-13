# Drift monitoring

featcat watches every feature for distribution drift relative to a baseline you set, and tells you when something has changed enough to be worth investigating before it breaks downstream models.

## When to use it

- **Right after declaring a feature production-ready** — set the baseline, and you'll be notified the next time the distribution moves.
- **Before a model retrain** — pull the drift report to confirm inputs are stable.
- **As a postmortem signal** — when a model degrades, drift history tells you which inputs shifted and when.

## How drift is measured

featcat uses **PSI** (Population Stability Index) by default for numeric features and **categorical PSI** for categoricals. Both yield the same scale:

| PSI | Meaning |
|---|---|
| `< 0.1` | No meaningful change |
| `0.1 – 0.25` | **Warning** — investigate |
| `> 0.25` | **Critical** — likely broken or shifted upstream |

Thresholds are configurable per feature (`featcat hints set <name> --warning-psi 0.05` for tighter monitoring on a sensitive feature).

## Setting a baseline

A baseline is a frozen snapshot of stats — bins, counts, mean/std/null-ratio. Future checks compare against it.

```bash
featcat baseline set --source user_behavior          # all features in source
featcat baseline set user_behavior.session_count_30d # one feature
```

The current parquet contents become the baseline. Store the baseline date with notes:

```bash
featcat baseline set user_behavior.session_count_30d --notes "v2 schema cutover, post-bot-filter"
```

## Running checks

Manually:

```bash
featcat monitor check                                # full catalog
featcat monitor check --source user_behavior        # one source
featcat monitor check user_behavior.session_count_30d
```

In production, the scheduler runs `monitor_check` every 6 hours by default. Configure with:

```bash
featcat schedule set monitor_check --cron "0 */6 * * *"
```

## What a check produces

For each feature, a `monitoring_checks` row:

```json
{
  "feature": "user_behavior.session_count_30d",
  "checked_at": "2026-05-06T14:00:00Z",
  "psi": 0.184,
  "severity": "warning",
  "stats_now": {"mean": 8.4, "std": 12.1, "null_ratio": 0.02},
  "stats_baseline": {"mean": 7.1, "std": 9.3, "null_ratio": 0.02},
  "n_now": 1000000,
  "n_baseline": 1200000
}
```

Aggregated:

```bash
featcat monitor report --since 30d
# 412 features checked, 8 warning, 1 critical, 403 stable
```

## Drift history

Per-feature time series:

```bash
featcat monitor history user_behavior.session_count_30d --days 30
```

The web UI shows a sparkline on the feature detail panel and a full chart on the **Monitoring** tab. Useful for spotting "drift is creeping up week over week" vs "drift spiked on one day."

API:

```bash
curl http://localhost:8000/api/monitor/history/user_behavior.session_count_30d?days=30
```

## Alerts

Critical drift fires an [in-app notification](notifications.md) to feature owners. The notification links straight to the feature's monitoring history. There's no email or Slack today — keep an eye on the bell icon.

For pipelines, poll `GET /api/monitor/report?severity=critical` and act on the response.

## Refreshing baselines

If the new distribution is the *correct* one (e.g. you fixed a long-standing bug, or migrated to a new sessionization), accept it as the new baseline:

```bash
featcat baseline set user_behavior.session_count_30d \
    --notes "Refresh after migrating bot-filter to v3, 2026-05-06"
```

The previous baseline is archived (`baselines_history`) so you can compare across regimes.

For routine refreshes (weekly snapshot), enable `auto_refresh=true` on the source. The scheduler re-baselines on whatever cadence you set with `featcat baseline schedule --source user_behavior --cron "0 0 * * 0"`.

## Tuning false positives

Common culprits:

- **Holiday seasonality** — Christmas, lunar new year, sporting events. Add a per-feature `seasonality_window` and PSI is computed against the same window in the baseline year.
- **Sample size** — small N inflates PSI. The check skips features with `n_now < 1000` by default; bump or lower with `--min-n`.
- **Long-tail features** — heavy-tailed distributions often look unstable with default 10-bin PSI. Switch to KS test (`featcat hints set <name> --drift-method ks`).

## Caveats

- **PSI assumes a stationary baseline.** If your business is genuinely growing (more users, more sessions), absolute counts will drift. Pair with normalized features.
- **PSI is feature-by-feature.** A model can degrade from joint shifts even when no single PSI trips. For that, monitor the model output too.
- **PSI is a number; investigate before acting.** A warning isn't a bug; it's a flag.

## Related

- **[Notifications](notifications.md)** — drift alerts surface here
- **[Bulk operations](bulk.md)** — set baselines for many features at once
- **[Catalog browser](catalog.md)** — filter features by drift status
- **[Architecture › Data Layer](../architecture/data.md)** *(coming soon)* — `monitoring_checks` schema
