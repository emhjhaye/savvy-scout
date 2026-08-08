"""Contracts Finder OCDS notices client.
GET {base}?publishedFrom=...&publishedTo=...&limit=100
Public, no authentication. Paginates fully via links.next."""

from collections.abc import Iterator
from datetime import datetime, timedelta

from savvy_scout.sources.ocds_client_base import paginate_release_packages
from savvy_scout.sources.ocds_parser import ParsedNotice, parse_release_package

SOURCE_LABEL = "Contracts Finder"


def _format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def sweep_contracts_finder(base_url: str, lookback_days: int) -> Iterator[ParsedNotice]:
    now = datetime.utcnow()
    published_from = now - timedelta(days=lookback_days)

    params = {
        "publishedFrom": _format_date(published_from),
        "publishedTo": _format_date(now),
        "limit": "100",
    }

    for package in paginate_release_packages(base_url, params, SOURCE_LABEL):
        yield from parse_release_package(package, SOURCE_LABEL)
