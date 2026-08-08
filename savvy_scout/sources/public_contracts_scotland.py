"""Public Contracts Scotland OCDS API client.
GET {base}/Notices?dateFrom=mm-yyyy&noticeType=<n>&outputType=0
Public, no authentication. Confirmed live against the real API 2026-07-28.

Unlike Find a Tender/Contracts Finder, this API has no date-range or
links.next pagination: it returns every notice of one type for one whole
calendar month in a single response. So sweeping "the last N days" means
looping over every (month, notice type) pair the lookback window touches."""

from collections.abc import Iterator
from datetime import datetime, timedelta

from savvy_scout.sources.ocds_client_base import paginate_release_packages
from savvy_scout.sources.ocds_parser import ParsedNotice, parse_release_package

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
    for month in _months_in_lookback(lookback_days):
        for notice_type in NOTICE_TYPES:
            url = f"{base}/Notices"
            params = {"dateFrom": month, "noticeType": str(notice_type), "outputType": "0"}
            for package in paginate_release_packages(url, params, SOURCE_LABEL):
                yield from parse_release_package(package, SOURCE_LABEL)
