-- fact_wager: grain = one settled wager. Optional matching win payout is joined
-- on (session, game, next event) so net position is available per wager.
SELECT
    w.event_id                 AS wager_event_id,
    w.player_id,
    w.game_id,
    w.session_id,
    w.event_ts,
    w.amount                   AS stake_amount
FROM raw_events w
WHERE w.event_type = 'wager'