"""Path of Exile league start times (UTC). The tracker names a run after the
league whose start is the latest one before you entered The Twilight Strand.
New leagues get added here; installed copies pick this file up with updates.
"""
from datetime import datetime, timezone

LEAGUES = [
    ("Affliction",            "2023-12-08 20:00"),
    ("Necropolis",            "2024-03-29 19:00"),
    ("Settlers of Kalguur",   "2024-07-26 19:00"),
    ("Phrecia",               "2025-02-20 20:00"),
    ("Secrets of the Atlas",  "2025-06-13 19:00"),
    ("Keepers of the Flame",  "2025-10-31 19:00"),
    ("Mirage",                "2026-03-06 19:00"),
    ("Curse of the Allflame", "2026-07-24 20:00"),
    ("Covens of Umbra",       "2026-11-13 19:00"),
]


def league_at(when):
    """The league running at `when` (a local-time datetime, like Client.txt's)."""
    when_utc = when.astimezone(timezone.utc)   # a time without a zone is taken as local time
    current = None
    for name, start in LEAGUES:
        if datetime.strptime(start, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc) <= when_utc:
            current = name
    return current or "Standard"
