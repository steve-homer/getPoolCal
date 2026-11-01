from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (getpoolcal schedule sync)"}


def find_pdf_url(page_url: str, pattern: str | None = None) -> str:
    """Return the absolute URL of the first PDF link on the page (matching `pattern`, if given)."""
    resp = httpx.get(page_url, headers=HEADERS, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    rx = re.compile(pattern, re.IGNORECASE) if pattern else None
    for a in soup.find_all("a", href=True):
        href = urljoin(str(resp.url), a["href"])
        if ".pdf" not in href.lower():
            continue
        if rx is None or rx.search(href) or rx.search(a.get_text(" ", strip=True)):
            return href
    raise LookupError(f"No PDF link{' matching ' + pattern if pattern else ''} found on {page_url}")


def download(url: str) -> bytes:
    resp = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=60)
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise ValueError(f"{url} did not return a PDF (content-type {resp.headers.get('content-type')})")
    return resp.content
