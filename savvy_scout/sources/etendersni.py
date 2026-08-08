"""eTendersNI client -- NOT IMPLEMENTED, and not scrapable at all as it
stands.

Investigated 2026-07-28, first by inspecting the raw HTML/API surface, then
by driving the real page with a headless browser (Playwright + Chromium) to
rule out a JS-rendering gap. Findings:

- No public API, RSS feed, or bulk export exists.
- The "List of opportunities" page (epps/prepareCurrentOpportunities.do,
  the one path that doesn't require login) renders zero result rows even
  after full JS execution and network-idle -- it fires no XHR/fetch calls
  at all. The only way to get a result set, on this page or the advanced
  search, is submitting a <form name="searchForm"> that has a mandatory
  CAPTCHA field (img#CAPTCHA, input#Captcha) alongside the search filters.

That CAPTCHA is a deliberate anti-automation control, not a missing
integration. Solving/bypassing it is out of scope -- this client
intentionally does not attempt that. Sweeping this source would need a
legitimate, sanctioned data-sharing arrangement with NI's Central
Procurement Directorate (who run eTendersNI), not a scraper.

The config_sources row for eTendersNI is seeded disabled with this
explanation in its notes; this function exists so runner.py's source
registry has something to dispatch to if it's ever enabled by mistake, and
so the gap is a loud, logged skip, not a crash."""

from collections.abc import Iterator

from savvy_scout.sources.ocds_parser import ParsedNotice

SOURCE_LABEL = "eTendersNI"


def sweep_etendersni(base_url: str, lookback_days: int) -> Iterator[ParsedNotice]:
    raise NotImplementedError(
        "eTendersNI has no public API/RSS, and its opportunity listings are "
        "gated behind a mandatory CAPTCHA on the only search form that "
        "returns results (confirmed live, including after full JS/headless-"
        "browser rendering). That's a deliberate anti-automation control, "
        "not a missing scraper -- this source needs a legitimate data-"
        "sharing arrangement with NI's Central Procurement Directorate, not "
        "a scraper, and should stay disabled in config_sources."
    )
    yield  # pragma: no cover -- makes this a generator, never reached
