"use strict";

/**
 * Canonical event schema — mirror of generator/schema.py.
 * Kept as plain JS (no external validator dep) so the ingestion service stays
 * dependency-light and the validation logic is fully visible.
 */

const COMMON_FIELDS = ["event_id", "event_type", "player_id", "timestamp"];

const TYPE_FIELDS = {
  session_start: ["session_id", "device_id", "ip_fingerprint"],
  session_end: ["session_id"],
  wager: ["session_id", "game_id", "amount"],
  win: ["session_id", "game_id", "amount"],
  deposit: ["payment_instrument", "amount"],
  withdrawal: ["payment_instrument", "amount"],
  bonus_claim: [
    "payment_instrument",
    "promotion_id",
    "amount",
    "qualifying_deposit_amount",
  ],
  self_exclusion: [],
};

const NUMERIC_FIELDS = new Set([
  "amount",
  "qualifying_deposit_amount",
]);

/**
 * Validate a single event. Returns { valid, errors }.
 * This is the edge contract: malformed payloads are rejected here, before
 * anything downstream ever sees them.
 */
function validateEvent(evt) {
  const errors = [];

  if (evt === null || typeof evt !== "object") {
    return { valid: false, errors: ["event is not an object"] };
  }

  const type = evt.event_type;
  if (!type || !(type in TYPE_FIELDS)) {
    return { valid: false, errors: [`unknown or missing event_type: ${type}`] };
  }

  const required = [...COMMON_FIELDS, ...TYPE_FIELDS[type]];
  for (const field of required) {
    if (!(field in evt) || evt[field] === null || evt[field] === "") {
      errors.push(`missing required field: ${field}`);
    }
  }

  for (const field of NUMERIC_FIELDS) {
    if (field in evt) {
      const v = evt[field];
      if (typeof v !== "number" || Number.isNaN(v)) {
        errors.push(`field ${field} must be numeric, got ${typeof v}`);
      } else if (v < 0) {
        errors.push(`field ${field} must be non-negative, got ${v}`);
      }
    }
  }

  // Timestamp must parse as a date.
  if (evt.timestamp && Number.isNaN(Date.parse(evt.timestamp))) {
    errors.push(`unparseable timestamp: ${evt.timestamp}`);
  }

  return { valid: errors.length === 0, errors };
}

module.exports = { validateEvent, COMMON_FIELDS, TYPE_FIELDS };