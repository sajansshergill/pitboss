-- dim_game: one row per game, with category derived from the game_id prefix.
SELECT DISTINCT
    game_id,
    split_part(game_id, '_', 1) AS game_category
FROM raw_events
WHERE game_id IS NOT NULL