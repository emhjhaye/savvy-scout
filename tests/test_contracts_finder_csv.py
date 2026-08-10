from unittest.mock import MagicMock, patch

from savvy_scout.sources.contracts_finder_csv import (
    _parse_cpv_codes,
    _parse_deadline,
    _parse_row,
    _parse_value,
    sweep_contracts_finder_csv,
)

SAMPLE_ROW = {
    "Notice Identifier": "SCMTCRec",
    "Notice Type": "Contract",
    "Organisation Name": "St Columb Major Town Council",
    "Status": "Open",
    "Published Date": "2026-08-10T12:27:12+01:00",
    "Title": "Recreation Ground Refurbishment",
    "Description": "Tenders are invited for Phase II of the Recreation Ground Refurbishment",
    "Region": "",
    "Cpv Codes": "92000000 45212140",
    "Contact Email": "clerk@stcolumbmajor-tc.gov.uk",
    "Contact Website": "",
    "Closing Date": "11/09/2026",
    "Closing Time": "12:00",
    "Value Low": "20000",
    "Value High": "",
}


def test_parse_row_maps_core_fields():
    parsed = _parse_row(SAMPLE_ROW, "Contracts Finder")

    assert parsed.notice.ref == "SCMTCRec"
    assert parsed.notice.title == "Recreation Ground Refurbishment"
    assert parsed.notice.buyer == "St Columb Major Town Council"
    assert parsed.notice.source == "Contracts Finder"
    assert parsed.notice.notice_type == "Contract"
    assert parsed.notice.uk_stage == "UK4"
    assert parsed.notice.cpv_primary == "92000000"
    assert parsed.notice.cpv_additional == ["45212140"]
    assert parsed.notice.published_at == "2026-08-10T12:27:12+01:00"
    assert parsed.notice.deadline == "2026-09-11T12:00:00"
    assert parsed.notice.indicative_value == "GBP 20000"
    assert parsed.tender_status == "Open"
    assert parsed.is_award is False
    assert parsed.is_publish_event is True


def test_parse_row_maps_preprocurement_and_pipeline_stages():
    pre = dict(SAMPLE_ROW, **{"Notice Type": "PreProcurement"})
    pipeline = dict(SAMPLE_ROW, **{"Notice Type": "Pipeline"})
    unknown = dict(SAMPLE_ROW, **{"Notice Type": "SomethingNew"})

    assert _parse_row(pre, "Contracts Finder").notice.uk_stage == "UK2"
    assert _parse_row(pipeline, "Contracts Finder").notice.uk_stage == "UK3"
    assert _parse_row(unknown, "Contracts Finder").notice.uk_stage == "UNVERIFIED"


def test_parse_row_requires_notice_identifier():
    bad_row = dict(SAMPLE_ROW, **{"Notice Identifier": ""})
    try:
        _parse_row(bad_row, "Contracts Finder")
        assert False, "expected ValueError for a row with no Notice Identifier"
    except ValueError:
        pass


def test_parse_deadline_combines_date_and_time():
    assert _parse_deadline("11/09/2026", "12:00") == "2026-09-11T12:00:00"


def test_parse_deadline_defaults_time_when_missing():
    assert _parse_deadline("11/09/2026", "") == "2026-09-11T00:00:00"


def test_parse_deadline_returns_none_for_empty_date():
    assert _parse_deadline("", "12:00") is None


def test_parse_value_combines_low_and_high():
    assert _parse_value("20000", "50000") == "GBP 20000 to 50000"
    assert _parse_value("20000", "") == "GBP 20000"
    assert _parse_value("", "50000") == "GBP up to 50000"
    assert _parse_value("", "") is None


def test_parse_cpv_codes_splits_on_whitespace():
    primary, additional = _parse_cpv_codes("92000000 45212140\n71000000")
    assert primary == "92000000"
    assert additional == ["45212140", "71000000"]
    assert _parse_cpv_codes("") == (None, [])
    assert _parse_cpv_codes(None) == (None, [])


def test_sweep_does_session_based_search_then_csv_fetch():
    """No stateless single-request API for this (see module docstring) --
    GET .../Search/Results must run first to set the search criteria in a
    server-side session, then GET .../Search/GetCsvFile reads from that
    same session. Confirmed live 2026-08-10: hitting GetCsvFile without a
    preceding search on the same session returns an empty CSV (header row
    only, 0 data rows)."""
    csv_body = (
        "Notice Identifier,Notice Type,Organisation Name,Status,Published Date,Title,Description,"
        "Region,Cpv Codes,Contact Email,Contact Website,Closing Date,Closing Time,Value Low,Value High\r\n"
        'SCMTCRec,Contract,"St Columb Major Town Council",Open,2026-08-10T12:27:12+01:00,'
        '"Recreation Ground Refurbishment","Tenders invited",,92000000,'
        'clerk@stcolumbmajor-tc.gov.uk,,11/09/2026,12:00,20000,\r\n'
    ).encode("utf-8")

    mock_session = MagicMock()
    search_response = MagicMock(status_code=200)
    csv_response = MagicMock(status_code=200, content=csv_body)
    mock_session.get.side_effect = [search_response, csv_response]

    with patch("savvy_scout.sources.contracts_finder_csv.requests.Session", return_value=mock_session):
        results = list(sweep_contracts_finder_csv("https://www.contractsfinder.service.gov.uk", 7))

    assert len(results) == 1
    assert results[0].notice.ref == "SCMTCRec"

    assert mock_session.get.call_count == 2
    first_call_url = mock_session.get.call_args_list[0].args[0]
    second_call_url = mock_session.get.call_args_list[1].args[0]
    assert first_call_url.endswith("/Search/Results")
    assert second_call_url.endswith("/Search/GetCsvFile")
