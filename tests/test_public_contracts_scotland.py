from unittest.mock import patch

import pytest

from savvy_scout.sources.public_contracts_scotland import (
    NOTICE_TYPES,
    sweep_public_contracts_scotland,
)


def test_one_failing_combination_does_not_discard_the_others():
    def fake_paginate(url, params, label):
        if params["noticeType"] == "2":
            raise RuntimeError("500 Error converting data type nvarchar to float")
        yield {"releases": [{"id": params["noticeType"]}]}

    with patch(
        "savvy_scout.sources.public_contracts_scotland.paginate_release_packages",
        side_effect=fake_paginate,
    ), patch(
        "savvy_scout.sources.public_contracts_scotland.parse_release_package",
        side_effect=lambda pkg, label: [pkg],
    ):
        results = list(
            sweep_public_contracts_scotland("https://api.publiccontractsscotland.gov.uk/v1", lookback_days=1)
        )

    assert len(results) == len(NOTICE_TYPES) - 1


def test_every_combination_failing_raises():
    def fake_paginate_all_fail(url, params, label):
        raise RuntimeError("500 Error converting data type nvarchar to float")
        yield  # pragma: no cover -- unreachable, keeps this a generator function

    with patch(
        "savvy_scout.sources.public_contracts_scotland.paginate_release_packages",
        side_effect=fake_paginate_all_fail,
    ):
        with pytest.raises(RuntimeError, match="all .* requests failed"):
            list(sweep_public_contracts_scotland("https://api.publiccontractsscotland.gov.uk/v1", lookback_days=1))
