"""Shared pagination for the Find a Tender, Contracts Finder, Public
Contracts Scotland and Sell2Wales OCDS APIs. Each exposes a public GET
endpoint returning a release package with an optional 'links.next' cursor
URL (confirmed live against Find a Tender/Contracts Finder 2026-07-19);
neither requires authentication for these public endpoints.

Both are public APIs with a rate limit; a daily scheduled sweep (SPEC.md's
Windows Task Scheduler job) will hit a 429 sooner or later, especially on a
7-day lookback with many pages. Retry with backoff rather than letting the
whole sweep die on one rate-limited page.

Public Contracts Scotland/Sell2Wales root cause found (2026-08-10): both
sites' TLS setup sends only their own leaf certificate, never the
intermediate CA that issued it ("Sectigo Public Server Authentication CA DV
R36", confirmed live via openssl s_client -showcerts against both hosts) --
a server-side misconfiguration, not anything about our request. Windows
auto-fetches/caches missing intermediates via its own trust-store updates
(why this always worked when tested from a developer's machine), but a
plain Linux container and Python's default SSL verification don't do that,
so every request failed outright with CERTIFICATE_VERIFY_FAILED /
"unable to get local issuer certificate" -- explaining months of Public
Contracts Scotland showing zero notices in production despite working
locally. Fix: supply the missing intermediate ourselves (see
extra_ca_certs/) merged with certifi's normal trusted roots (the root that
issued it, "Sectigo Public Server Authentication Root R46", is already in
certifi -- confirmed present) -- this only ADDS the ability to complete a
legitimate chain through one real, valid CA; it doesn't relax verification
for any other host. Applied to every request through this shared module
since it's a pure addition, not a per-domain workaround."""

import time
from collections.abc import Iterator
from pathlib import Path

import certifi
import requests

REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2

_EXTRA_CA_CERT_DIR = Path(__file__).parent / "extra_ca_certs"


def _build_ca_bundle_path() -> str:
    """Merges certifi's bundle with every PEM file in extra_ca_certs/ into
    one temp file, regenerated from whatever certifi is currently installed
    (rather than vendoring a copy of certifi's own bundle here, which would
    go stale on a certifi upgrade). Falls back to certifi's own bundle if
    there's nothing to merge or the merge fails for any reason -- this must
    never be the reason a sweep can't run at all."""
    extra_certs = sorted(_EXTRA_CA_CERT_DIR.glob("*.pem")) if _EXTRA_CA_CERT_DIR.is_dir() else []
    if not extra_certs:
        return certifi.where()
    try:
        import tempfile

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as tmp:
            tmp.write(Path(certifi.where()).read_bytes())
            for cert_path in extra_certs:
                tmp.write(b"\n")
                tmp.write(cert_path.read_bytes())
            return tmp.name
    except OSError:
        return certifi.where()


CA_BUNDLE_PATH = _build_ca_bundle_path()

# Public Contracts Scotland and Sell2Wales's IIS servers 403 the default
# "python-requests/x.y.z" User-Agent outright (confirmed live 2026-07-29);
# Find a Tender/Contracts Finder don't seem to filter on it, but sending a
# normal browser-style UA everywhere is harmless and one less thing to break
# if that ever changes.
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _get_with_retry(url: str, params: dict[str, str] | None) -> requests.Response:
    for attempt in range(MAX_RETRIES + 1):
        response = requests.get(
            url, params=params, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS, verify=CA_BUNDLE_PATH
        )
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
