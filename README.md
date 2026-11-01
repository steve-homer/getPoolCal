# getpoolcal

Publishes Oxbridge's Yarm Pool League fixtures as a calendar feed
(`docs/pool.ics`, served by GitHub Pages) that Outlook, Google Calendar or
Apple Calendar can subscribe to.

A GitHub Action (`.github/workflows/update.yml`) runs every Monday, and on
each push or manual run. It:

1. finds the fixture PDF on <https://yarmpoolleague.co.uk/fixture-list/>;
2. reads it with tesseract OCR. The PDF is a picture of a table with no text
   layer, so the table's grid lines are located, each cell is OCR'd with
   several preprocessing passes and the majority reading wins;
3. checks the result (dates a week apart, every team at most once per week,
   a full 1..16 team key) and fails without touching the feed if any check
   fails. GitHub emails you when the workflow fails;
4. merges the team's fixtures into `data/events.json` and rewrites
   `docs/pool.ics`, committing only if something changed.

Each fixture is an all-day event such as `Pool: Oxbridge v Eagle "B" (home)`.
In a cell like `6-9` the first team is taken as the home team, and its name is
used as the location. A PDF covers part of a season, so a new PDF replaces
only the events within the dates it covers and earlier fixtures stay in the feed.

Settings (team, link pattern, feed name, paths) are in `config.toml`.

## Subscribing

Outlook.com / Microsoft 365: Calendar → Add calendar → Subscribe from web →
`https://<user>.github.io/<repo>/pool.ics`. Outlook refreshes subscribed
calendars every few hours, so changes can take a while to appear.

## Running locally

```sh
brew install tesseract
uv sync
uv run getpoolcal dump    # print the OCR'd fixture grid and team key
uv run getpoolcal show    # print the team's fixtures
uv run getpoolcal ics     # update data/events.json and docs/pool.ics
uv run pytest             # the real-PDF test is skipped without tesseract
```

`--pdf file.pdf` uses a local file instead of fetching; `--url` overrides the page.
