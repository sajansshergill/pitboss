-- fact_session: grain = one play session, pairing start and end events.
WITH starts AS (
    SELECT session_id, player_id, device_id, ip_fingerprint,
           event_ts AS start_ts
    FROM raw_events
    WHERE event_type = 'session_start'
),
ends AS (
    SELECT session_id, max(event_ts) AS end_ts
    FROM raw_events
    WHERE event_type = 'session_end'
    GROUP BY session_id
)
SELECT
    s.session_id,
    s.player_id,
    s.device_id,
    s.ip_fingerprint,
    s.start_ts,
    e.end_ts,
    date_diff('second', s.start_ts, e.end_ts) AS duration_seconds
FROM starts s
LEFT JOIN ends e ON e.session_id = s.session_id