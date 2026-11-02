import shutil
from datetime import date
from pathlib import Path

import pytest

from getpoolcal.parse import Fixture, ParseError, Schedule, _parse_match, parse_date, parse_schedule, team_events

PDF = Path(__file__).parent / "data" / "fixtures-2026-27.pdf"

# Hand transcription of tests/data/fixtures-2026-27.pdf (weeks 14 and 15 are N/A).
EXPECTED = """1-14 15-1 1-16 13-1 1-12 11-1 1-10 9-1 1-8 1-6 7-1 1-4 5-1 - - 1-2 3-1
2-13 14-2 2-15 12-2 2-11 10-2 2-9 8-2 2-7 2-5 6-2 2-3 4-2 - - 9-16 16-2
3-12 13-3 3-14 11-3 3-10 9-3 3-8 7-3 3-6 3-4 5-3 10-16 16-3 - - 10-8 9-10
4-11 12-4 4-13 10-4 4-9 8-4 4-7 6-4 4-5 11-16 4-16 11-9 10-11 - - 11-7 8-11
5-10 11-5 5-12 9-5 5-8 7-5 6-5 5-16 16-12 12-10 11-12 12-8 9-12 - - 12-6 7-12
6-9 10-6 6-11 8-6 6-7 16-6 13-16 12-13 13-11 13-9 10-13 13-7 8-13 - - 13-5 6-13
7-8 9-7 7-10 16-7 16-14 14-13 12-14 14-11 10-14 14-8 9-14 14-6 7-14 - - 14-4 5-14
15-16 16-8 8-9 14-15 15-13 12-15 15-11 10-15 15-9 15-7 8-15 15-5 6-15 - - 15-3 4-15"""


def test_parse_date_rolls_into_next_year():
    assert parse_date("23-Sep", 2026, None) == date(2026, 9, 23)
    assert parse_date("7 - Oct", 2026, 9) == date(2026, 10, 7)
    assert parse_date("13-Jan", 2026, 9) == date(2027, 1, 13)
    with pytest.raises(ParseError):
        parse_date("3O-Sep", 2026, 9)


def test_parse_match():
    assert _parse_match("10-16") == (10, 16)
    assert _parse_match("N/A") is None
    assert _parse_match("") is None
    with pytest.raises(ParseError):
        _parse_match("1016")


def test_team_events():
    s = Schedule({1: "Beckfields", 2: "Eagle \"A\"", 6: "Oxbridge", 9: 'Eagle "B"'},
                 [Fixture(1, date(2026, 9, 23), 6, 9), Fixture(1, date(2026, 9, 23), 1, 2),
                  Fixture(2, date(2026, 9, 30), 1, 6), Fixture(2, date(2026, 9, 30), 9, 2),
                  Fixture(4, date(2026, 10, 14), 9, 1)],
                 [], {1: date(2026, 9, 23), 2: date(2026, 9, 30), 3: date(2026, 10, 7), 4: date(2026, 10, 14)})
    evs = team_events(s, "oxbridge")
    assert [e.title for e in evs] == ['Pool: Oxbridge v Eagle "B" (home)', "Pool: Beckfields v Oxbridge (away)",
                                      "Pool: No Oxbridge Match", "Pool: No Oxbridge Match"]
    assert [e.start.date() for e in evs] == [date(2026, 9, 23), date(2026, 9, 30), date(2026, 10, 7), date(2026, 10, 14)]
    assert evs[1].location == "Beckfields" and evs[1].all_day
    assert evs[2].location == "" and evs[2].all_day
    assert (evs[0].end - evs[0].start).days == 1
    assert evs[0].notes == 'Yarm Pool League week 1\n\nOther matches:\nBeckfields v Eagle "A"'
    assert evs[1].notes == 'Yarm Pool League week 2\n\nOther matches:\nEagle "B" v Eagle "A"'
    assert evs[2].notes == "Yarm Pool League week 3\n\nNo league matches this week."
    assert evs[3].notes == 'Yarm Pool League week 4\n\nMatches:\nEagle "B" v Beckfields'
    with pytest.raises(ParseError):
        team_events(s, "Nobody")


def test_team_events_without_week_list():
    s = Schedule({1: "Beckfields", 6: "Oxbridge"}, [Fixture(1, date(2026, 9, 23), 6, 1)], [])
    assert [e.title for e in team_events(s, "Oxbridge")] == ["Pool: Oxbridge v Beckfields (home)"]


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_real_pdf():
    s = parse_schedule(PDF.read_bytes())
    weeks = list(zip(*[row.split() for row in EXPECTED.splitlines()]))
    expected = {(i, tuple(map(int, c.split("-")))) for i, week in enumerate(weeks) for c in week if c != "-"}
    got = {(f.week - 1, (f.home, f.away)) for f in s.fixtures}
    assert got == expected
    assert s.teams[6] == "Oxbridge" and len(s.teams) == 16
    assert s.fixtures[0].day == date(2026, 9, 23) and s.fixtures[-1].day == date(2027, 1, 13)
    assert len(s.weeks) == 17 and s.weeks[14] == date(2026, 12, 23) and s.weeks[15] == date(2026, 12, 30)
