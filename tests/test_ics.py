from datetime import datetime, timedelta

from getpoolcal import ics
from getpoolcal.model import Event


def day(m, d, title="Pool: Oxbridge v Union (home)", y=2026):
    start = datetime(y, m, d)
    return Event(title, start, start + timedelta(days=1), "Oxbridge", "week 1", all_day=True)


def test_merge_replaces_only_the_new_range():
    first_half = [day(9, 23), day(12, 16), day(1, 13, y=2027)]
    second_half = [day(1, 13, "Pool: Tables v Oxbridge (away)", y=2027), day(3, 3, y=2027)]
    merged = ics.merge(first_half, second_half)
    assert [e.start.date().isoformat() for e in merged] == ["2026-09-23", "2026-12-16", "2027-01-13", "2027-03-03"]
    assert merged[2].title == "Pool: Tables v Oxbridge (away)"
    assert ics.merge(first_half, []) == first_half


def test_render_all_day_and_escaping():
    text = ics.render([day(9, 23, 'Pool: Oxbridge v Eagle "B", (home); x')], "Pool League", "Europe/London")
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20260923\r\n" in text and "DTEND;VALUE=DATE:20260924\r\n" in text
    assert 'SUMMARY:Pool: Oxbridge v Eagle "B"\\, (home)\; x\r\n' in text
    assert text == ics.render([day(9, 23, 'Pool: Oxbridge v Eagle "B", (home); x')], "Pool League", "Europe/London")


def test_long_lines_folded():
    text = ics.render([day(9, 23, "x" * 200)], "Pool League", "Europe/London")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert "x" * 200 in text.replace("\r\n ", "")


def test_write_round_trip(tmp_path):
    store, feed = tmp_path / "events.json", tmp_path / "pool.ics"
    assert ics.write(store, feed, [day(9, 23)], "Pool League", "Europe/London") == (1, True)
    assert ics.write(store, feed, [day(9, 23)], "Pool League", "Europe/London") == (1, False)
    assert ics.load(store) == [day(9, 23)]
