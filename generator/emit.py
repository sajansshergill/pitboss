"""Synthetic casino event generator.

Produces a believable stream of casino events. The point is not volume but
*shape*: realistic sequences (session -> deposit -> wagers -> wins), plus
deliberately planted fraud patterns the Neo4j layer is meant to detect, plus
optional failure injection for the "bad data day".

Usage
-----
    # clean run, write raw firehose to disk
    python generator/emit.py --players 200 --sink file

    # POST directly to the running Node collector
    python generator/emit.py --players 200 --sink http

    # inject data-quality failures
    python generator/emit.py --inject duplicates,schema-drift,late-batch
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as a script (python generator/emit.py) or as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RAW_FIREHOSE, INJECTABLE_FAILURES, ensure_dirs  # noqa: E402

try:
    from faker import Faker
    _fake = Faker()
except ImportError:  # generator still works without Faker, just less pretty
    _fake = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class World:
    """Holds the identity graph so fraud rings can share device/card/fingerprint."""

    def __init__(self, n_players: int, seed: int = 42):
        self.rng = random.Random(seed)
        self.players: list[str] = [f"P{ i:05d}" for i in range(n_players)]
        # Each honest player gets unique identity signals.
        self.device = {p: f"D{ self.rng.randrange(10**9):09d}" for p in self.players}
        self.card = {p: f"CARD-{ self.rng.randrange(10**8):08d}" for p in self.players}
        self.fingerprint = {p: f"FP{ self.rng.randrange(10**9):09d}" for p in self.players}
        self.excluded_at: dict[str, datetime] = {}
        self.rings: list[list[str]] = []
        self.referrals: list[tuple[str, str]] = []  # (referrer, referee)

    def uid(self) -> str:
        """Deterministic id derived from the seeded RNG (reproducible datasets)."""
        return "%032x" % self.rng.getrandbits(128)

    def plant_bonus_abuse_ring(self, size: int, promotion_id: str) -> list[str]:
        """A cluster of 'distinct' accounts that all share one payment card."""
        members = self.rng.sample(self.players, size)
        shared_card = f"CARD-RING-{ len(self.rings):03d}"
        for p in members:
            self.card[p] = shared_card
        self.rings.append(members)
        return members

    def plant_collusion_ring(self, size: int) -> list[str]:
        """Accounts linked by a shared device and fingerprint (same operator)."""
        members = self.rng.sample(self.players, size)
        shared_device = f"D-COLL-{ len(self.rings):03d}"
        shared_fp = f"FP-COLL-{ len(self.rings):03d}"
        for p in members:
            self.device[p] = shared_device
            self.fingerprint[p] = shared_fp
        self.rings.append(members)
        return members

    def plant_referral_chain(self, length: int) -> list[str]:
        chain = self.rng.sample(self.players, length)
        for a, b in zip(chain, chain[1:]):
            self.referrals.append((a, b))
        # Referral farming: whole chain shares a fingerprint.
        shared_fp = f"FP-REF-{ len(self.referrals):03d}"
        for p in chain:
            self.fingerprint[p] = shared_fp
        return chain


def _envelope(world: World, event_type: str, player: str, ts: datetime) -> dict:
    return {
        "event_id": world.uid(),
        "event_type": event_type,
        "player_id": player,
        "timestamp": _iso(ts),
    }


def _player_session(world: World, player: str, start: datetime) -> list[dict]:
    """Emit one realistic session for a player."""
    rng = world.rng
    events: list[dict] = []
    session_id = f"S-{world.uid()[:12]}"
    t = start

    e = _envelope(world, "session_start", player, t)
    e.update(session_id=session_id, device_id=world.device[player],
             ip_fingerprint=world.fingerprint[player])
    events.append(e)

    # ~40% of sessions open with a deposit.
    qualifying_deposit = 0.0
    if rng.random() < 0.4:
        t += timedelta(seconds=rng.randint(5, 60))
        deposit = round(rng.uniform(10, 500), 2)
        qualifying_deposit = deposit
        e = _envelope(world, "deposit", player, t)
        e.update(payment_instrument=world.card[player], amount=deposit)
        events.append(e)

        # A deposit sometimes triggers a bonus claim.
        if rng.random() < 0.5:
            t += timedelta(seconds=rng.randint(1, 10))
            bonus = round(min(deposit, deposit * rng.uniform(0.2, 1.0)), 2)
            e = _envelope(world, "bonus_claim", player, t)
            e.update(payment_instrument=world.card[player],
                     promotion_id=rng.choice(["WELCOME100", "RELOAD50", "VIP200"]),
                     amount=bonus, qualifying_deposit_amount=deposit)
            events.append(e)

    # A run of wagers, some of which win.
    for _ in range(rng.randint(3, 20)):
        t += timedelta(seconds=rng.randint(2, 40))
        game = rng.choice(["slots_aztec", "blackjack_hd", "roulette_eu",
                           "poker_texas", "slots_dragon"])
        stake = round(rng.uniform(0.5, 50), 2)
        e = _envelope(world, "wager", player, t)
        e.update(session_id=session_id, game_id=game, amount=stake)
        events.append(e)
        if rng.random() < 0.42:
            t += timedelta(seconds=1)
            payout = round(stake * rng.uniform(1.1, 8.0), 2)
            e = _envelope(world, "win", player, t)
            e.update(session_id=session_id, game_id=game, amount=payout)
            events.append(e)

    # Occasional withdrawal.
    if rng.random() < 0.2:
        t += timedelta(seconds=rng.randint(5, 30))
        e = _envelope(world, "withdrawal", player, t)
        e.update(payment_instrument=world.card[player],
                 amount=round(rng.uniform(10, 300), 2))
        events.append(e)

    t += timedelta(seconds=rng.randint(5, 60))
    e = _envelope(world, "session_end", player, t)
    e.update(session_id=session_id)
    events.append(e)
    return events


def generate_with_world(n_players: int = 200, seed: int = 42):
    """Same as generate() but also returns the World (for referral export)."""
    world = World(n_players, seed)

    # Plant fraud patterns the graph layer should catch.
    world.plant_bonus_abuse_ring(size=6, promotion_id="WELCOME100")
    world.plant_collusion_ring(size=5)
    world.plant_referral_chain(length=5)

    rng = world.rng
    base = _now() - timedelta(hours=6)
    events: list[dict] = []

    # A handful of players self-exclude partway through the window; any wager
    # after that timestamp is an invariant violation the quality layer catches.
    excluders = rng.sample(world.players, max(1, n_players // 50))
    for p in excluders:
        world.excluded_at[p] = base + timedelta(hours=rng.uniform(1, 3))

    for player in world.players:
        n_sessions = rng.randint(1, 4)
        for _ in range(n_sessions):
            start = base + timedelta(minutes=rng.uniform(0, 300))
            events.extend(_player_session(world, player, start))
            # Emit the self-exclusion event at its timestamp for excluders.
            if player in world.excluded_at and rng.random() < 0.3:
                events.append(_envelope(world, "self_exclusion", player,
                                        world.excluded_at[player]))

    # Bonus-abuse ring: every member claims the SAME promotion on the shared card.
    for ring in world.rings[:1]:
        for p in ring:
            t = base + timedelta(minutes=rng.uniform(0, 300))
            dep = round(rng.uniform(20, 100), 2)
            e = _envelope(world, "deposit", p, t)
            e.update(payment_instrument=world.card[p], amount=dep)
            events.append(e)
            e = _envelope(world, "bonus_claim", p, t + timedelta(seconds=3))
            e.update(payment_instrument=world.card[p], promotion_id="WELCOME100",
                     amount=round(dep, 2), qualifying_deposit_amount=dep)
            events.append(e)

    events.sort(key=lambda x: x["timestamp"])
    return events, world


def generate(n_players: int = 200, seed: int = 42) -> list[dict]:
    events, _ = generate_with_world(n_players, seed)
    return events


def write_referrals(world: "World", path: Path) -> None:
    """Dump referrer,referee pairs so the graph layer can build REFERRED_BY."""
    with open(path, "w") as fh:
        fh.write("referrer,referee\n")
        for referrer, referee in world.referrals:
            fh.write(f"{referrer},{referee}\n")


def inject_failures(events: list[dict], modes: list[str], seed: int = 7) -> list[dict]:
    """Corrupt a copy of the stream with the requested failure modes."""
    rng = random.Random(seed)
    out = list(events)

    if "duplicates" in modes:
        # Re-emit ~1% of events verbatim (same event_id) -> caught by dedup gate.
        dupes = rng.sample(out, max(1, len(out) // 100))
        out.extend(json.loads(json.dumps(d)) for d in dupes)

    if "schema-drift" in modes:
        # Rename `amount` -> `amt` and drop `timestamp` on a few events ->
        # rejected at the Node validation boundary into quarantine.
        victims = rng.sample([e for e in out if "amount" in e],
                             k=max(1, len(out) // 200))
        for e in victims:
            e["amt"] = e.pop("amount")
            if rng.random() < 0.5:
                e.pop("timestamp", None)

    if "late-batch" in modes:
        # Backdate a cluster of events by ~30 days -> freshness gate flags them.
        stale = rng.sample(out, max(1, len(out) // 100))
        for e in stale:
            ts = datetime.fromisoformat(e["timestamp"]) - timedelta(days=30)
            e["timestamp"] = _iso(ts)

    out.sort(key=lambda x: x.get("timestamp", ""))
    return out


def write_file(events: list[dict], path: Path = RAW_FIREHOSE) -> None:
    ensure_dirs()
    with open(path, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def post_http(events: list[dict], url: str) -> None:
    import urllib.request
    payload = json.dumps({"events": events}).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        print(resp.read().decode())


def main() -> None:
    ap = argparse.ArgumentParser(description="PitBoss synthetic event generator")
    ap.add_argument("--players", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sink", choices=("file", "http"), default="file")
    ap.add_argument("--url", default="http://localhost:8080/events")
    ap.add_argument("--inject", default="",
                    help=f"comma list of {INJECTABLE_FAILURES}")
    args = ap.parse_args()

    events, world = generate_with_world(args.players, args.seed)
    write_referrals(world, RAW_FIREHOSE.parent / "referrals.csv")
    if args.inject:
        modes = [m.strip() for m in args.inject.split(",") if m.strip()]
        bad = [m for m in modes if m not in INJECTABLE_FAILURES]
        if bad:
            ap.error(f"unknown failure modes: {bad}")
        events = inject_failures(events, modes)
        print(f"injected: {modes}")

    if args.sink == "file":
        write_file(events)
        print(f"wrote {len(events)} events -> {RAW_FIREHOSE}")
    else:
        post_http(events, args.url)


if __name__ == "__main__":
    main()