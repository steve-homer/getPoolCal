"""Read the Yarm Pool League fixture grid out of its (image-only) PDF with tesseract.

The PDF is a single page holding a picture of a table: a row of week numbers,
a row of dates ("23-Sep"), then one row per match slot with cells like "1-14"
(home team number - away team number), and a numbered team key underneath.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageOps

from .model import Event

# Grid lines are located on a 300 dpi render; cells are read from a 600 dpi one.
GRID_DPI = 300
OCR_DPI = 600
# (scale, threshold) preprocessing passes for each cell. Each pass alone misreads
# a few cells (5 as 3 or 9, 11 as 14), but rarely the same ones, so the cell's
# value is the majority reading.
CELL_PASSES = [(0.5, 180), (0.5, 140), (1.0, 140), (1.0, 180)]
MATCH_CHARS = "0123456789-NA/"
DATE_CHARS = "0123456789- ADFJMNOSabcceghilnoprtuvy"
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


class ParseError(Exception):
    pass


@dataclass(frozen=True)
class Fixture:
    week: int
    day: date
    home: int
    away: int


@dataclass
class Schedule:
    teams: dict[int, str]
    fixtures: list[Fixture]
    grid: list[list[str]]  # raw cell readings, for `getpoolcal dump`
    weeks: dict[int, date] = field(default_factory=dict)  # every week in the PDF, weeks off included

    def name(self, n: int) -> str:
        return self.teams.get(n, f"Team {n}")


def _render(data: bytes, dpi: int, mode: str) -> Image.Image:
    page = pdfium.PdfDocument(data)[0]
    return page.render(scale=dpi / 72).to_pil().convert(mode)


def _tesseract(img: Image.Image, psm: int, whitelist: str | None = None) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    cmd = ["tesseract", "stdin", "stdout", "--psm", str(psm)]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    # Cells are read in parallel, so keep each tesseract single-threaded: OpenMP builds
    # (e.g. Ubuntu's) otherwise oversubscribe the CPUs and slow to a crawl.
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    return subprocess.run(
        cmd, input=buf.getvalue(), capture_output=True, check=True, env=env, timeout=60
    ).stdout.decode().strip()


def _line_positions(frac: np.ndarray, threshold: float) -> list[int]:
    """Centres of runs of indices where `frac` exceeds `threshold`."""
    runs: list[list[int]] = []
    for i in np.flatnonzero(frac > threshold):
        if runs and i - runs[-1][-1] <= 3:
            runs[-1].append(int(i))
        else:
            runs.append([int(i)])
    return [(r[0] + r[-1]) // 2 for r in runs]


def find_grid(img: Image.Image) -> tuple[list[int], list[int]]:
    """Row and column boundaries of the table, from its blue cell borders."""
    a = np.asarray(img, dtype=np.int16)
    r, b = a[..., 0], a[..., 2]
    blue = (b - r > 15) & (b < 225) & (r < 200)
    rows = _line_positions(blue.mean(axis=1), 0.4)
    if len(rows) < 4:
        raise ParseError(f"Could not find the fixture table's grid (found {len(rows)} horizontal lines)")
    cols = _line_positions(blue[rows[0] : rows[-1]].mean(axis=0), 0.5)
    if len(cols) < 2:
        raise ParseError("Could not find the fixture table's columns")
    return rows, cols


def _read_cell(img: Image.Image, box: tuple[int, int, int, int], whitelist: str, passes) -> str:
    readings = []
    for scale, threshold in passes:
        c = img.crop(box)
        if scale != 1:
            c = c.resize((int(c.width * scale), int(c.height * scale)), Image.LANCZOS)
        c = ImageOps.expand(c.point(lambda v: 255 if v > threshold else 0), 30, fill=255)
        readings.append(_tesseract(c, 7, whitelist))
    return Counter(readings).most_common(1)[0][0]


def read_grid(data: bytes) -> tuple[list[list[str]], Image.Image, int, int]:
    """OCR every cell. Returns the cell texts, the OCR render, and the table's top and bottom edges in it."""
    rows, cols = find_grid(_render(data, GRID_DPI, "RGB"))
    k = OCR_DPI // GRID_DPI
    img = _render(data, OCR_DPI, "L")
    m = 6 * k  # stay clear of the borders
    jobs = []
    for ri in range(len(rows) - 1):
        for ci in range(len(cols) - 1):
            box = (cols[ci] * k + m, rows[ri] * k + m, cols[ci + 1] * k - m, rows[ri + 1] * k - m)
            if ri == 1:
                jobs.append((box, DATE_CHARS, CELL_PASSES[2:3]))
            else:
                jobs.append((box, MATCH_CHARS, CELL_PASSES))
    with ThreadPoolExecutor(8) as ex:
        texts = list(ex.map(lambda j: _read_cell(img, *j), jobs))
    width = len(cols) - 1
    grid = [texts[i : i + width] for i in range(0, len(texts), width)]
    return grid, img, rows[0] * k, rows[-1] * k


def read_title_year(img: Image.Image, table_top: int) -> int:
    title = _tesseract(img.crop((0, 0, img.width, table_top)), 6)
    years = [int(y) for y in re.findall(r"\b(20\d\d)\b", title)]
    if not years:
        raise ParseError(f"No season year found in title {title!r}")
    return min(years)


def read_teams(img: Image.Image, table_bottom: int) -> dict[int, str]:
    """The numbered team key below the table, laid out in two centred columns."""
    teams: dict[int, str] = {}
    for x0, x1 in [(0, img.width // 2), (img.width // 2, img.width)]:
        text = _tesseract(img.crop((x0, table_bottom, x1, img.height)), 6)
        for line in text.splitlines():
            if m := re.match(r"\s*(\d{1,2})\s*\)\s*(.+?)\s*$", line):
                teams[int(m.group(1))] = m.group(2).replace("“", '"').replace("”", '"')
    return teams


def parse_date(text: str, season_start: int, first_month: int | None) -> date:
    m = re.fullmatch(r"\s*(\d{1,2})\s*-\s*([A-Za-z]{3})[a-z]*\s*", text)
    if not m or m.group(2).lower() not in MONTHS:
        raise ParseError(f"Unreadable date cell {text!r}")
    month = MONTHS[m.group(2).lower()]
    # The season runs autumn to spring: months before the first one are next year.
    year = season_start + (1 if first_month and month < first_month else 0)
    return date(year, month, int(m.group(1)))


def _parse_match(text: str) -> tuple[int, int] | None:
    t = text.replace(" ", "")
    if t in ("", "N/A", "NA"):
        return None
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", t)
    if not m:
        raise ParseError(f"Unreadable fixture cell {text!r}")
    return int(m.group(1)), int(m.group(2))


def parse_schedule(data: bytes) -> Schedule:
    if not shutil.which("tesseract"):
        raise ParseError("tesseract is not installed (brew install tesseract)")
    grid, img, table_top, table_bottom = read_grid(data)
    if len(grid) < 3:
        raise ParseError("Fixture table has too few rows")
    season_start = read_title_year(img, table_top)
    teams = read_teams(img, table_bottom)

    fixtures: list[Fixture] = []
    weeks: dict[int, date] = {}
    problems: list[str] = []
    first_month = None
    prev_day = None
    for ci in range(len(grid[0])):
        week = int(grid[0][ci]) if grid[0][ci].isdigit() else ci + 1
        day = parse_date(grid[1][ci], season_start, first_month)
        first_month = first_month or day.month
        if prev_day and (day - prev_day).days % 7:
            problems.append(f"week {week}: {day} is not a whole number of weeks after {prev_day}")
        prev_day = day
        weeks[week] = day
        matches = [m for m in (_parse_match(grid[ri][ci]) for ri in range(2, len(grid))) if m]
        if not matches:
            continue  # a week off (N/A)
        seen = Counter(t for m in matches for t in m)
        if dupes := sorted(t for t, n in seen.items() if n > 1):
            problems.append(f"week {week} ({day}): teams {dupes} appear more than once in {matches}")
        if any(h == a for h, a in matches):
            problems.append(f"week {week} ({day}): a team plays itself in {matches}")
        fixtures += [Fixture(week, day, h, a) for h, a in matches]

    team_count = 2 * (len(grid) - 2)
    if sorted(teams) != list(range(1, team_count + 1)):
        problems.append(f"team key lists {sorted(teams)}, expected 1..{team_count}")
    if bad := sorted({t for f in fixtures for t in (f.home, f.away) if not 1 <= t <= team_count}):
        problems.append(f"fixtures mention unknown team numbers {bad}")
    if problems:
        raise ParseError("The fixture grid did not read cleanly:\n  " + "\n  ".join(problems))
    return Schedule(teams, fixtures, grid, weeks)


def team_number(schedule: Schedule, team: str) -> int:
    if team.isdigit():
        return int(team)
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    matches = [n for n, name in schedule.teams.items() if norm(name) == norm(team)]
    if len(matches) != 1:
        raise ParseError(f"Team {team!r} not found in key: {schedule.teams}")
    return matches[0]


def team_events(schedule: Schedule, team: str, prefix: str = "Pool") -> list[Event]:
    """One all-day event per week of the PDF for one team.

    A week the team plays is "<prefix>: Home v Away (home|away)", located at the
    first-listed (home) team's venue. A week it doesn't, including a week off
    for the whole league, is "<prefix>: No <team> Match". Each event's
    description lists the week's other matches.
    """
    me = team_number(schedule, team)
    weeks = schedule.weeks or {f.week: f.day for f in schedule.fixtures}
    events = []
    for week, day in sorted(weeks.items()):
        fixtures = [f for f in schedule.fixtures if f.week == week]
        mine = next((f for f in fixtures if me in (f.home, f.away)), None)
        others = [f"{schedule.name(f.home)} v {schedule.name(f.away)}" for f in fixtures if f is not mine]
        notes = f"Yarm Pool League week {week}\n\n"
        if others:
            notes += ("Other matches:\n" if mine else "Matches:\n") + "\n".join(others)
        else:
            notes += "No league matches this week."
        start = datetime(day.year, day.month, day.day)
        if mine:
            home = schedule.name(mine.home)
            side = "home" if mine.home == me else "away"
            title, location = f"{prefix}: {home} v {schedule.name(mine.away)} ({side})", home
        else:
            title, location = f"{prefix}: No {schedule.name(me)} Match", ""
        events.append(Event(title, start, start + timedelta(days=1), location, notes, all_day=True))
    return events
