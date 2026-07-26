-- fact_bonus_claim: grain = one bonus claim, carrying the deposit that
-- qualified it so the quality layer can enforce bonus <= qualifying deposit.
SELECT
    event_id                    AS bonus_event_id,
    player_id,
    payment_instrument,
    promotion_id,
    amount                      AS bonus_amount,
    qualifying_deposit_amount,
    event_ts
FROM raw_events
WHERE event_type = 'bonus_claim'