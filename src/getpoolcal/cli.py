"""Fetch the league fixture PDF and publish one team's fixtures as an iCalendar feed."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from . import fetch, ics, parse

CONFIG_PATHS = [Path("config.toml"), Path.home() / ".config" / "getpoolcal" / "config.toml"]


def load_config(path: str | None) -> dict:
    candidates = [Path(path)] if path else CONFIG_PATHS
    for p in candidates:
        if p.exists():
            return tomllib.loads(p.read_text())
    if path:
        sys.exit(f"Config file not found: {path}")
    return {}


def get_pdf(args, cfg: dict) -> bytes:
    if args.pdf:
        return Path(args.pdf).read_bytes()
    page = args.url or cfg.get("page_url")
    if not page:
        sys.exit("No page_url in config and no --url/--pdf given")
    pdf_url = fetch.find_pdf_url(page, cfg.get("pdf_link_pattern"))
    print(f"Schedule PDF: {pdf_url}", file=sys.stderr)
    return fetch.download(pdf_url)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="getpoolcal", description=__doc__)
    ap.add_argument("--config", help="path to config.toml")
    ap.add_argument("--url", help="page linking to the PDF (overrides config)")
    ap.add_argument("--pdf", help="use a local PDF instead of fetching")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dump", help="print the OCR'd fixture grid and team key")
    sub.add_parser("show", help="print your team's fixtures")
    sub.add_parser("ics", help="merge the fixtures into the event store and write the .ics feed")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    data = get_pdf(args, cfg)

    try:
        schedule = parse.parse_schedule(data)
    except parse.ParseError as e:
        sys.exit(str(e))

    if args.cmd == "dump":
        for row in schedule.grid:
            print(" ".join(f"{c:>7}" for c in row))
        print()
        for n, name in sorted(schedule.teams.items()):
            print(f"{n:>2}) {name}")
        return

    if not cfg.get("team"):
        sys.exit("config.toml needs 'team' (name or number from the fixture key)")
    try:
        events = parse.team_events(schedule, str(cfg["team"]), cfg.get("title_prefix", "Pool"))
    except parse.ParseError as e:
        sys.exit(str(e))
    if args.cmd == "show":
        for e in events:
            print(f"{e.start:%a %Y-%m-%d}  {e.title}")
        print(f"{len(events)} events", file=sys.stderr)
        return

    n, changed = ics.write(
        Path(cfg.get("store", "data/events.json")),
        Path(cfg.get("feed", "docs/pool.ics")),
        events,
        cfg.get("calendar_name", "Pool League"),
        cfg.get("time_zone", "Europe/London"),
    )
    print(f"{n} events in feed ({'updated' if changed else 'unchanged'})")

if __name__ == "__main__":
    main()
