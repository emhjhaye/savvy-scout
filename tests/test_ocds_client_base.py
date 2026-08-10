from pathlib import Path
from unittest.mock import MagicMock, patch

import certifi
import pytest
import requests

from savvy_scout.sources import ocds_client_base
from savvy_scout.sources.ocds_client_base import _build_ca_bundle_path, _get_with_retry, paginate_release_packages


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


def test_get_with_retry_passes_the_merged_ca_bundle(monkeypatch):
    """2026-08-10 fix: Public Contracts Scotland/Sell2Wales send only their
    own leaf certificate, never the intermediate CA that issued it -- a
    server-side misconfiguration, confirmed live via openssl s_client
    -showcerts against both hosts. Every request through this module must
    use the merged bundle (certifi + the missing intermediate), not
    requests' plain default, or the fix has no effect."""
    monkeypatch.setattr("savvy_scout.sources.ocds_client_base.time.sleep", lambda _seconds: None)
    with patch(
        "savvy_scout.sources.ocds_client_base.requests.get",
        return_value=_fake_response(200, {"releases": []}),
    ) as mock_get:
        _get_with_retry("http://example.test", {})
    assert mock_get.call_args.kwargs["verify"] == ocds_client_base.CA_BUNDLE_PATH


def test_build_ca_bundle_path_merges_certifi_with_extra_certs():
    bundle_path = _build_ca_bundle_path()
    bundle_content = Path(bundle_path).read_bytes()

    assert Path(certifi.where()).read_bytes() in bundle_content

    extra_certs = list((Path(ocds_client_base.__file__).parent / "extra_ca_certs").glob("*.pem"))
    assert extra_certs, "expected at least the Sectigo intermediate cert to be present"
    for cert_path in extra_certs:
        assert cert_path.read_bytes() in bundle_content


def test_build_ca_bundle_path_falls_back_to_certifi_when_no_extra_certs(tmp_path, monkeypatch):
    empty_dir = tmp_path / "empty_extra_certs"
    empty_dir.mkdir()
    monkeypatch.setattr(ocds_client_base, "_EXTRA_CA_CERT_DIR", empty_dir)

    assert _build_ca_bundle_path() == certifi.where()
