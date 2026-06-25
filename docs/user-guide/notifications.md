# Notifications

featcat raises in-app notifications when something interesting happens to a feature you own — drift trips, doc generation finishes, certification status changes. They live in the bell icon in the top-right of the web UI; there's no email or chat-app integration today.

## When you'll see one

- **Critical drift** — a feature you own has PSI > 0.25 against its baseline
- **Warning drift** — PSI between 0.1 and 0.25 (configurable; off by default for warnings)
- **Doc generation completed** — your batch job of N features finished
- **Doc generation failed** — features that didn't generate cleanly
- **Certification status changed** — a feature you own moved between `draft` / `reviewed` / `certified` / `deprecated`
- **Group membership changed** — a feature you own was added to or removed from a group

These are the seeded types in `featcat/db/models.py`. New types can be registered by passing a `kind` string to `create_notification(...)`.

## Reading notifications

The bell icon shows an unread count. Click it for the dropdown:

- Each notification has a title, body, and severity (`info` / `warning` / `critical`).
- Click a notification → marks it read and navigates to the relevant page (feature detail, group, etc.).
- "Mark all read" clears the unread count.

API equivalents:

```bash
# List
curl http://localhost:8000/api/notifications?actor=alice
# → {"notifications": [...], "unread": 3}

curl http://localhost:8000/api/notifications/unread-count?actor=alice
# → {"unread": 3}

# Mark one read
curl -X POST http://localhost:8000/api/notifications/{id}/read

# Mark all read
curl -X POST http://localhost:8000/api/notifications/read-all?actor=alice
```

The `actor` is a free-form string — your username or pipeline identifier. Use it for routing notifications to the right person, not as a credential. Access control is handled separately by bearer token or trusted-proxy auth on the server.

## Owners and routing

Each feature has an `owner` field (string). Notifications about a feature are routed to its owner. Set with:

```bash
curl -X PATCH 'http://localhost:8000/api/features/by-name?name=user_behavior.session_count_30d' \
    -H 'Content-Type: application/json' \
    -d '{"owner": "alice"}'
```

If a feature has no owner, drift / doc / cert notifications go to a single `__catchall__` actor that the dashboard surfaces under "Unassigned alerts." Set up a rotation by tagging a person to that actor.

For groups, notifications fan out to every owner of any member feature, deduped.

## Filtering noise

By default:

- **Critical drift** notifies on every check (not just the first transition into critical).
- **Warning drift** is silent by default.
- **Doc generation completed** notifies once per batch, not per feature.

Reduce noise by keeping feature owners accurate and using the web UI filters to focus on critical alerts.

## Polling vs push

The frontend polls `unread-count` every 30 seconds. There's no SSE / websocket push for notifications today. 30s latency is fine for the use cases we have; if you need real-time, the SSE chat endpoint is a precedent for adding push later.

## Future integrations

The original T2.1 spec had Slack as the alert channel. The current implementation deliberately keeps notifications in-web only — no third-party tokens to manage, no per-team config — until the platform is mature enough that the cost of integration management is worth it.

When integration *is* added, the `create_notification(...)` API stays the same and a separate notifier process consumes from the table and delivers to Slack/email/etc. The data layer is forward-compatible.

## Common questions

- **"I'm not getting drift notifications."** — Is the feature owner set? `featcat feature info <name>` to check. Update owner through the feature edit API or the web UI.
- **"The unread count is wrong."** — Hard refresh the browser; the React store may have drifted from the server. The server-side counts are authoritative.
- **"Can I get a digest instead of one-by-one?"** — Not today. Open an issue with the cadence you want; daily / weekly digest is straightforward to add as a scheduled job.

## Related

- **[Monitoring](monitoring.md)** — drift triggers most notifications
- **[Documentation](docs.md)** — doc batch completion notifications
- **[Catalog browser](catalog.md)** — owner field is in the feature detail panel
- **[Architecture › Data Layer](../architecture/data.md)** — notifications schema
