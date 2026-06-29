# Advisor monitoring

## Surfaces

| Surface | URL | Purpose |
|---------|-----|---------|
| Admin dashboard | `http://localhost:8000/admin` | Integration health, tool outcomes, failed-ops retry, session event timeline |
| Prometheus | `http://localhost:9090` | Scrape `/metrics` (docker `--profile monitoring`) |
| Grafana | `http://localhost:3001` | Time-series tool latency, timeout rates (default login `admin` / `admin`) |
| PostHog | Your project | Product analytics for tool/turn events |

## Environment

```bash
TELEMETRY_JSON_LOGS=true   # JSON telemetry lines to stdout during local tests
SUPABASE_URL=              # Required for chat_events audit trail
SUPABASE_SERVICE_ROLE_KEY=
POSTHOG_API_KEY=
SENTRY_DSN=
```

## Docker monitoring stack

```bash
docker compose --profile monitoring up -d
```

## PostHog dashboard (manual)

Create insights for:

- `tool_completed` count by `tool` property
- `tool_timeout` and `tool_failed` rates
- `turn_completed` p95 `total_ms`

## System test verification

After `scripts/run_manual_tests.py`, open `/admin` → Session Inspector with the test `session_id` to verify `tool_invoked` → `tool_completed` chains and latencies.
