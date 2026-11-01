# Runtime for the weekly feed update: Python, the locked dependencies and tesseract.
# The code itself is pulled from the repo on every run (deploy/run.sh), so pushing
# a change to main takes effect without rebuilding the image.
FROM python:3.12-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr git openssh-client ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv

# GitHub's published SSH host keys, so pushes verify the host (no trust-on-first-use).
COPY deploy/github_known_hosts /etc/ssh/ssh_known_hosts

RUN useradd --create-home --uid 1000 app && mkdir -p /opt/venv /work && chown app:app /opt/venv /work
USER app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1

# Install the dependencies at build time; run.sh's `uv run --locked` then only
# has to install something if uv.lock has changed since.
COPY --chown=app:app pyproject.toml uv.lock /tmp/build/
RUN cd /tmp/build && uv sync --locked --no-dev --no-install-project && rm -rf /tmp/build

COPY --chmod=755 deploy/run.sh /usr/local/bin/getpoolcal-update
WORKDIR /work
ENTRYPOINT ["getpoolcal-update"]
