"""Public Contracts Scotland OCDS API client.
GET {base}/Notices?dateFrom=mm-yyyy&noticeType=<n>&outputType=0
Public, no authentication. Confirmed live against the real API 2026-07-28.

Unlike Find a Tender/Contracts Finder, this API has no date-range or
links.next pagination: it returns every notice of one type for one whole
calendar month in a single response. So sweeping "the last N days" means
looping over every (month, notice type) pair the lookback window touches.

2026-08-13: each (month, noticeType) request is isolated the same way as
Sell2Wales' identical fix (see that module's docstring) -- one combination
failing after retries is logged and skipped rather than aborting the
whole generator, so a single bad combination doesn't discard every other
notice type's results. Only re-raises if every combination fails."""

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta

from savvy_scout.sources.ocds_client_base import paginate_release_packages
from savvy_scout.sources.ocds_parser import ParsedNotice, parse_release_package

logger = logging.getLogger(__name__)

SOURCE_LABEL = "Public Contracts Scotland"

# OJEU notice types plus PCS's own below-threshold "Site Notice" types.
# Excludes rarer types (corrigendum, qualification systems, design contest)
# to keep the sweep to a bounded number of requests per month.
NOTICE_TYPES = [1, 2, 3, 4, 5, 6, 24, 25, 101, 102, 103, 104]


def _months_in_lookback(lookback_days: int) -> list[str]:
    now = datetime.utcnow()
    start = now - timedelta(days=lookback_days)
    months = []
    cursor = start.replace(day=1)
    while cursor <= now:
        months.append(cursor.strftime("%m-%Y"))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def sweep_public_contracts_scotland(base_url: str, lookback_days: int) -> Iterator[ParsedNotice]:
    base = base_url.rstrip("/")
    combinations_attempted = 0
    combinations_failed = 0
    for month in _months_in_lookback(lookback_days):
        for notice_type in NOTICE_TYPES:
            combinations_attempted += 1
            url = f"{base}/Notices"
            params = {"dateFrom": month, "noticeType": str(notice_type), "outputType": "0"}
            try:
                for package in paginate_release_packages(url, params, SOURCE_LABEL):
                    yield from parse_release_package(package, SOURCE_LABEL)
            except Exception:
                combinations_failed += 1
                logger.warning(
                    "%s: month=%s noticeType=%s failed after retries, skipping this combination",
                    SOURCE_LABEL, month, notice_type, exc_info=True,
                )

    if combinations_attempted and combinations_failed == combinations_attempted:
        raise RuntimeError(
            f"{SOURCE_LABEL}: all {combinations_attempted} (month, noticeType) requests failed "
            "-- likely a total outage."
        )
