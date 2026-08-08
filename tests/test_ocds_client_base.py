from unittest.mock import MagicMock, patch

import pytest
import requests

from savvy_scout.sources.ocds_client_base import _get_with_retry, paginate_release_packages


def _fake_response(status_code, json_body=None, headers=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = json_body or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(f"{status_code} error")
    else:
        resp.raise_for_status.side_effect = None
    return resp


def test_get_with_retry_succeeds_after_a_429(monkeypatch):
    monkeypatch.setattr("savvy_scout.sources.ocds_client_base.time.sleep", lambda _seconds: None)
    responses = [_fake_response(429), _fake_response(200, {"releases": []})]
    with patch("savvy_scout.sources.ocds_client_base.requests.get", side_effect=responses):
        result = _get_with_retry("http://example.test", {})
    assert result.status_code == 200


def test_get_with_retry_respects_retry_after_header(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("savvy_scout.sources.ocds_client_base.time.sleep", sleep_calls.append)
    responses = [_fake_response(429, headers={"Retry-After": "3"}), _fake_response(200, {"releases": []})]
    with patch("savvy_scout.sources.ocds_client_base.requests.get", side_effect=responses):
        _get_with_retry("http://example.test", {})
    assert sleep_calls == [3.0]


def test_get_with_retry_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("savvy_scout.sources.ocds_client_base.time.sleep", lambda _seconds: None)
    responses = [_fake_response(429) for _ in range(10)]
    with patch("savvy_scout.sources.ocds_client_base.requests.get", side_effect=responses):
        with pytest.raises(requests.exceptions.HTTPError):
            _get_with_retry("http://example.test", {})


def test_paginate_release_packages_retries_mid_pagination(monkeypatch):
    monkeypatch.setattr("savvy_scout.sources.ocds_client_base.time.sleep", lambda _seconds: None)
    page1 = _fake_response(200, {"releases": ["a"], "links": {"next": "http://example.test/page2"}})
    page2_throttled = _fake_response(429)
    page2 = _fake_response(200, {"releases": ["b"]})
    with patch(
        "savvy_scout.sources.ocds_client_base.requests.get",
        side_effect=[page1, page2_throttled, page2],
    ):
        pages = list(paginate_release_packages("http://example.test", {}, "Test Source"))
    assert [p["releases"] for p in pages] == [["a"], ["b"]]
