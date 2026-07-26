"""Canonical event schema.

Every casino event shares a common envelope plus type-specific fields. This
module is the reference the Node ingestion service validates against (mirrored
in ingest/schema.js) and the transform layer models against.
"""
from __future__ import annotations

# Common envelope fields present on every event.
COMMON_FIELDS = ("event_id", "event_type", "player_id", "timestamp")

# Type-specific required fields (in addition to the common envelope).
TYPE_FIELDS: dict[str, tuple[str, ...]] = {
    "session_start": ("session_id", "device_id", "ip_fingerprint"),
    "session_end": ("session_id",),
    "wager": ("session_id", "game_id", "amount"),
    "win": ("session_id", "game_id", "amount"),
    "deposit": ("payment_instrument", "amount"),
    "withdrawal": ("payment_instrument", "amount"),
    # qualifying_deposit_amount lets the quality layer enforce
    # "bonus never exceeds the deposit that qualified it".
    "bonus_claim": ("payment_instrument", "promotion_id", "amount",
                    "qualifying_deposit_amount"),
    "self_exclusion": (),
}


def required_fields(event_type: str) -> tuple[str, ...]:
    return COMMON_FIELDS + TYPE_FIELDS.get(event_type, ())