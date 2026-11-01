"""Keep a season's events in a JSON store and render them as an iCalendar feed.

The fixture PDF only covers part of a season (the next one replaces it), so each
run replaces the stored events within the dates the current PDF covers and keeps
the rest, rather than letting earlier fixtures vanish from the feed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .model import Event


def load(path: Path) -> list[Event]:
    if not path.exists():
        return []
    return [
        Event(e["title"], datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"]),
              e.get("location", ""), e.get("notes", ""), e.get("all_day", False))
        for e in json.loads(path.read_text())
    ]


def save(path: Path, events: list[Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"title": e.title, "start": e.start.isoformat(), "end": e.end.isoformat(),
         "location": e.location, "notes": e.notes, "all_day": e.all_day}
        for e in events
    ]
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")


def merge(stored: list[Event], new: list[Event]) -> list[Event]:
    """Replace stored events in the date range `new` covers with `new`. An empty `new` changes nothing."""
    if not new:
        return stored
    first = min(e.start.date() for e in new)
    last = max(e.start.date() for e in new)
    kept = [e for e in stored if not first <= e.start.date() <= last]
    return sorted(kept + new, key=lambda e: (e.start, e.title))


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Fold to 75-octet lines as RFC 5545 requires."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode())
            cur = b""
        cur += b
    out.append(cur.decode())
    return "\r\n ".join(out)


def render(events: list[Event], name: str, tz: str) -> str:
    """The feed. DTSTAMP is fixed per event so an unchanged schedule renders byte-identically."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//getpoolcal//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        f"X-WR-TIMEZONE:{tz}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    for e in events:
        uid = hashlib.sha256(e.key.encode()).hexdigest()[:24] + "@getpoolcal"
        stamp = datetime(e.start.year, 1, 1, tzinfo=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}"]
        if e.all_day:
            lines += [f"DTSTART;VALUE=DATE:{e.start:%Y%m%d}", f"DTEND;VALUE=DATE:{e.end:%Y%m%d}"]
        else:
            lines += [f"DTSTART;TZID={tz}:{e.start:%Y%m%dT%H%M%S}", f"DTEND;TZID={tz}:{e.end:%Y%m%dT%H%M%S}"]
        lines += [f"SUMMARY:{_escape(e.title)}", "TRANSP:TRANSPARENT"]
        if e.location:
            lines.append(f"LOCATION:{_escape(e.location)}")
        if e.notes:
            lines.append(f"DESCRIPTION:{_escape(e.notes)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def write(store: Path, feed: Path, new: list[Event], name: str, tz: str) -> tuple[int, bool]:
    """Merge `new` into the store and rewrite the feed. Returns (event count, whether the feed changed)."""
    events = merge(load(store), new)
    save(store, events)
    data = render(events, name, tz).encode()
    changed = not feed.exists() or feed.read_bytes() != data
    if changed:
        feed.parent.mkdir(parents=True, exist_ok=True)
        feed.write_bytes(data)
    return len(events), changed
