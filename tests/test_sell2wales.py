from unittest.mock import patch

import pytest

from savvy_scout.sources.sell2wales import NOTICE_TYPES, sweep_sell2wales


def test_one_failing_combination_does_not_discard_the_others():
    # Regression (2026-08-13): confirmed live, noticeType=2 500'd while
    # noticeType=1 succeeded in the same sweep run -- the old code let one
    # bad (month, noticeType) combination's exception propagate out of the
    # whole generator, discarding every other type's results for the run.
    def fake_paginate(url, params, label):
        if params["noticeType"] == "2":
            raise RuntimeError("500 Error converting data type nvarchar to float")
        yield {"releases": [{"id": params["noticeType"]}]}

    with patch("savvy_scout.sources.sell2wales.paginate_release_packages", side_effect=fake_paginate), \
         patch("savvy_scout.sources.sell2wales.parse_release_package", side_effect=lambda pkg, label: [pkg]):
        results = list(sweep_sell2wales("https://api.sell2wales.gov.wales/v1", lookback_days=1))

    assert len(results) == len(NOTICE_TYPES) - 1


def test_every_combination_failing_raises():
    # A genuine total outage must still surface as a failed source in Sweep
    # History, not a silent "success, 0 pulled".
    def fake_paginate_all_fail(url, params, label):
        raise RuntimeError("500 Error converting data type nvarchar to float")
        yield  # pragma: no cover -- unreachable, keeps this a generator function

    with patch("savvy_scout.sources.sell2wales.paginate_release_packages", side_effect=fake_paginate_all_fail):
        with pytest.raises(RuntimeError, match="all .* requests failed"):
            list(sweep_sell2wales("https://api.sell2wales.gov.wales/v1", lookback_days=1))
