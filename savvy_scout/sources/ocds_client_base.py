"""Shared pagination for the Find a Tender and Contracts Finder OCDS APIs.
Both expose a public GET endpoint returning a release package with an
optional 'links.next' cursor URL (confirmed live against both services on
2026-07-19); neither requires authentication for these public endpoints.

Both are public APIs with a rate limit; a daily scheduled sweep (SPEC.md's
Windows Task Scheduler job) will hit a 429 sooner or later, especially on a
7-day lookback with many pages. Retry with backoff rather than letting the
whole sweep die on one rate-limited page."""

import time
from collections.abc import Iterator

import requests

REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2

# Public Contracts Scotland and Sell2Wales's IIS servers 403 the default
# "python-requests/x.y.z" User-Agent outright (confirmed live 2026-07-29);
# Find a Tender/Contracts Finder don't seem to filter on it, but sending a
# normal browser-style UA everywhere is harmless and one less thing to break
# if that ever changes.
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _get_with_retry(url: str, params: dict[str, str] | None) -> requests.Response:
    for attempt in range(MAX_RETRIES + 1):
        response = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == MAX_RETRIES:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else BACKOFF_BASE_SECONDS * (2**attempt)
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response
    raise RuntimeError("unreachable")  # loop always returns or raises above


def paginate_release_packages(
    first_url: str, params: dict[str, str], source_label: str
) -> Iterator[dict]:
    """Yields each release package page in full, following links.next until
    exhausted. Public endpoint: no auth headers are sent. Retries 429/5xx
    responses with backoff, honouring Retry-After when the server sends one."""
    url = first_url
    next_params: dict[str, str] | None = params

    while url:
        response = _get_with_retry(url, next_params)
        package = response.json()
        yield package

        next_url = (package.get("links") or {}).get("next")
        url = next_url
        next_params = None  # the next link already carries all query params
