"""Sell2Wales OCDS API client.
GET {base}/Notices?dateFrom=mm-yyyy&noticeType=<n>&outputType=0&locale=2057
Public, no authentication. Same platform/shape as Public Contracts Scotland
(same "OCDS Web API" help page, same query params) -- see
public_contracts_scotland.py for the month/notice-type looping rationale.

As of 2026-07-28 the live Sell2Wales API intermittently returns a 500
("Error converting data type nvarchar to float") that is a bug on their own
end, not a bad request from us -- confirmed by hitting their own
documented example query. paginate_release_packages already retries 5xx
with backoff; if it keeps failing the sweep should skip this source for
the run rather than dying, which run_sweep's per-source try/except handles."""

from collections.abc import Iterator
from datetime import datetime, timedelta

from savvy_scout.sources.ocds_client_base import paginate_release_packages
from savvy_scout.sources.ocds_parser import ParsedNotice, parse_release_package

SOURCE_LABEL = "Sell2Wales"

# OJEU notice types plus Sell2Wales's own below-threshold "Site Notice"
# types (51-56; Scotland numbers the equivalent 101-104, a different range).
NOTICE_TYPES = [1, 2, 3, 4, 5, 6, 24, 25, 51, 52, 53, 54, 55, 56]

LOCALE_EN = "2057"


def _months_in_lookback(lookback_days: int) -> list[str]:
    now = datetime.utcnow()
    start = now - timedelta(days=lookback_days)
    months = []
    cursor = start.replace(day=1)
    while cursor <= now:
        months.append(cursor.strftime("%m-%Y"))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def sweep_sell2wales(base_url: str, lookback_days: int) -> Iterator[ParsedNotice]:
    base = base_url.rstrip("/")
    for month in _months_in_lookback(lookback_days):
        for notice_type in NOTICE_TYPES:
            url = f"{base}/Notices"
            params = {
                "dateFrom": month,
                "noticeType": str(notice_type),
                "outputType": "0",
                "locale": LOCALE_EN,
            }
            for package in paginate_release_packages(url, params, SOURCE_LABEL):
                yield from parse_release_package(package, SOURCE_LABEL)
