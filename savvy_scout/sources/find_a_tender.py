"""Find a Tender OCDS release packages API client.
GET {base}/ocdsReleasePackages?updatedFrom=...&updatedTo=...&limit=100&stages=...
Public, no authentication. Paginates fully via links.next."""

from collections.abc import Iterator
from datetime import datetime, timedelta

from savvy_scout.sources.ocds_client_base import paginate_release_packages
from savvy_scout.sources.ocds_parser import ParsedNotice, parse_release_package

SOURCE_LABEL = "Find a Tender"


def _format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def sweep_find_a_tender(
    base_url: str, lookback_days: int, stages: str | None = None
) -> Iterator[ParsedNotice]:
    now = datetime.utcnow()
    updated_from = now - timedelta(days=lookback_days)

    params = {
        "updatedFrom": _format_datetime(updated_from),
        "updatedTo": _format_datetime(now),
        "limit": "100",
    }
    if stages:
        params["stages"] = stages

    first_url = f"{base_url.rstrip('/')}/ocdsReleasePackages"

    for package in paginate_release_packages(first_url, params, SOURCE_LABEL):
        yield from parse_release_package(package, SOURCE_LABEL)
