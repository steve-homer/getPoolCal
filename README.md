# getpoolcal

Publishes Oxbridge's Yarm Pool League fixtures as a calendar feed
(`docs/pool.ics`, served by GitHub Pages) that Outlook, Google Calendar or
Apple Calendar can subscribe to.

A Linux server runs `run` weekly from a systemd timer (see
[Server setup](#server-setup)). Each run:

1. pulls the latest `main` of this repo;
2. finds the fixture PDF on <https://yarmpoolleague.co.uk/fixture-list/>;
3. reads it with tesseract OCR. The PDF is a picture of a table with no text
   layer, so the table's grid lines are located, each cell is OCR'd with
   several preprocessing passes and the majority reading wins;
4. checks the result (dates a week apart, every team at most once per week,
   a full 1..16 team key) and fails without touching the feed if any check fails;
5. merges the team's fixtures into the event store, rewrites the feed and
   copies `pool.ics` and `index.html` to the server's web root;
6. copies the store and feed to `data/events.json` and `docs/pool.ics`, and
   commits and pushes (with a deploy key) only if something changed.
   GitHub Pages then serves the new feed.

The GitHub Action only runs the tests on each push.

Each fixture is an all-day event such as `Pool: Oxbridge v Eagle "B" (home)`.
In a cell like `6-9` the first team is taken as the home team, and its name is
used as the location. A PDF covers part of a season, so a new PDF replaces
only the events within the dates it covers and earlier fixtures stay in the feed.

Settings (team, link pattern, feed name, paths) are in `config.toml`.

## Subscribing

Outlook.com / Microsoft 365: Calendar → Add calendar → Subscribe from web →
`https://<user>.github.io/<repo>/pool.ics`. Outlook refreshes subscribed
calendars every few hours, so changes can take a while to appear.

## Server setup

The server follows the `/srv/jobs` convention: an unprivileged `jobs` user,
uv, user-level systemd units, and Caddy serving `/srv/www`. Needs the
`tesseract-ocr` apt package.

```sh
sudo apt-get install tesseract-ocr
# as jobs:
ssh-keygen -t ed25519 -N "" -f ~/.ssh/getpoolcal_deploy   # add the .pub as a deploy key with write access
/srv/jobs/new-job getpoolcal https://github.com/steve-homer/getPoolCal.git "Mon *-*-* 06:15"
systemctl --user start job@getpoolcal && journalctl --user -u job@getpoolcal -e
```

`run` keeps the event store in `$STATE_DIRECTORY` (`~/.local/state/getpoolcal`,
seeded from `data/events.json` on the first run), because it accumulates fixtures
across PDFs and must survive the `git reset` at the start of each run. It writes
a copy of `config.toml` there with `store` and `feed` pointing into that directory.

Environment: `WWW_DIR` (default `/srv/www/getpoolcal`), `DEPLOY_KEY` (default
`~/.ssh/getpoolcal_deploy`), `PUSH=0` to skip committing and pushing to GitHub.
`deploy/github_known_hosts` holds GitHub's published SSH host keys, so pushes
verify the host.

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
