-- observability/queries.sql — weekly usage analytics over the api_usage table
--
-- Source: api_usage (populated by api/middleware/usage.py). Operational
-- telemetry only — NOT a regulatory audit record (see migration 0003).
--
-- Each query summarises the trailing 7 days. Run manually, from a scheduled
-- reporting job, or as the basis for a Grafana/QuickSight panel. `status` holds
-- the HTTP status code, so an error is `status >= 400`.

-- ── 1. Top 10 functions by call volume (last 7 days) ────────────────────────
SELECT
    domain,
    function_name,
    COUNT(*) AS call_count
FROM api_usage
WHERE created_at >= now() - interval '7 days'
GROUP BY domain, function_name
ORDER BY call_count DESC
LIMIT 10;

-- ── 2. P95 request duration per domain (last 7 days) ────────────────────────
SELECT
    domain,
    COUNT(*) AS call_count,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_duration_ms,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms) AS p50_duration_ms
FROM api_usage
WHERE created_at >= now() - interval '7 days'
GROUP BY domain
ORDER BY p95_duration_ms DESC;

-- ── 3. Error rate per tier (last 7 days) ────────────────────────────────────
SELECT
    tier,
    COUNT(*)                                       AS total_requests,
    COUNT(*) FILTER (WHERE status >= 400)          AS error_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status >= 400) / NULLIF(COUNT(*), 0),
        2
    )                                              AS error_rate_pct
FROM api_usage
WHERE created_at >= now() - interval '7 days'
GROUP BY tier
ORDER BY error_rate_pct DESC NULLS LAST;
