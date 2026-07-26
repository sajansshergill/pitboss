-- dim_player: one row per player with conformed identity + lifecycle attributes.
-- Identity signals (device/card/fingerprint) are taken from the player's most
-- recent occurrence of each, which is what the graph layer keys on.
WITH latest_device AS (
    SELECT player_id, device_id,
           row_number() OVER (PARTITION BY player_id ORDER BY event_ts DESC) AS rn
    FROM raw_events
    WHERE event_type = 'session_start' AND device_id IS NOT NULL
),
latest_fp AS (
    SELECT player_id, ip_fingerprint,
           row_number() OVER (PARTITION BY player_id ORDER BY event_ts DESC) AS rn
    FROM raw_events
    WHERE event_type = 'session_start' AND ip_fingerprint IS NOT NULL
),
latest_card AS (
    SELECT player_id, payment_instrument,
           row_number() OVER (PARTITION BY player_id ORDER BY event_ts DESC) AS rn
    FROM raw_events
    WHERE payment_instrument IS NOT NULL
),
exclusion AS (
    SELECT player_id, min(event_ts) AS self_excluded_ts
    FROM raw_events
    WHERE event_type = 'self_exclusion'
    GROUP BY player_id
)
SELECT
    p.player_id,
    min(p.event_ts)                      AS first_seen_ts,
    max(p.event_ts)                      AS last_seen_ts,
    d.device_id                          AS primary_device,
    f.ip_fingerprint                     AS primary_fingerprint,
    c.payment_instrument                 AS primary_card,
    x.self_excluded_ts,
    (x.self_excluded_ts IS NOT NULL)     AS is_self_excluded
FROM raw_events p
LEFT JOIN latest_device d ON d.player_id = p.player_id AND d.rn = 1
LEFT JOIN latest_fp     f ON f.player_id = p.player_id AND f.rn = 1
LEFT JOIN latest_card   c ON c.player_id = p.player_id AND c.rn = 1
LEFT JOIN exclusion     x ON x.player_id = p.player_id
GROUP BY p.player_id, d.device_id, f.ip_fingerprint, c.payment_instrument,
         x.self_excluded_ts