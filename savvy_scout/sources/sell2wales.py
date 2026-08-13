"""Sell2Wales OCDS API client.
GET {base}/Notices?dateFrom=mm-yyyy&noticeType=<n>&outputType=0&locale=2057
Public, no authentication. Same platform/shape as Public Contracts Scotland
(same "OCDS Web API" help page, same query params) -- see
public_contracts_scotland.py for the month/notice-type looping rationale.

As of 2026-07-28 the live Sell2Wales API intermittently returns a 500
("Error converting data type nvarchar to float") that is a bug on their own
end, not a bad request from us -- confirmed by hitting their own
documented example query. paginate_release_packages already retries 5xx
with backoff.

2026-08-13 fix: this 500 is specific to certain (month, noticeType)
combinations, not the whole API -- confirmed live, noticeType=1 succeeded
while noticeType=2 500'd in the same sweep run. The previous version let
one bad combination's exception propagate out of the whole generator,
which run_sweep's per-source try/except caught and marked the ENTIRE
source failed for the run -- silently discarding every other notice
type's results too, even ones that had already succeeded or would have.
Each (month, noticeType) request is now isolated: a failure after
paginate_release_packages' own retries are exhausted is logged and
skipped, not propagated, so the rest of the sweep still runs. Only if
every single combination fails does this re-raise, so a genuine total
outage still surfaces as a failed source in Sweep History rather than a
silent "success, 0 pulled"."""

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta

from savvy_scout.sources.ocds_client_base import paginate_release_packages
from savvy_scout.sources.ocds_parser import ParsedNotice, parse_release_package

logger = logging.getLogger(__name__)

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
    combinations_attempted = 0
    combinations_failed = 0
    for month in _months_in_lookback(lookback_days):
        for notice_type in NOTICE_TYPES:
            combinations_attempted += 1
            url = f"{base}/Notices"
            params = {
                "dateFrom": month,
                "noticeType": str(notice_type),
                "outputType": "0",
                "locale": LOCALE_EN,
            }
            try:
                for package in paginate_release_packages(url, params, SOURCE_LABEL):
                    yield from parse_release_package(package, SOURCE_LABEL)
            except Exception:
                combinations_failed += 1
                logger.warning(
                    "%s: month=%s noticeType=%s failed after retries, skipping this "
                    "combination (their known intermittent 500)",
                    SOURCE_LABEL, month, notice_type, exc_info=True,
                )

    if combinations_attempted and combinations_failed == combinations_attempted:
        raise RuntimeError(
            f"{SOURCE_LABEL}: all {combinations_attempted} (month, noticeType) requests "
            "failed -- likely a total outage, not the usual intermittent per-combination 500."
        )
