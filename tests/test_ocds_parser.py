from savvy_scout.sources.ocds_parser import parse_release_package


def test_parses_real_sample_notice(sample_ocds_package):
    parsed_list = parse_release_package(sample_ocds_package, source="Find a Tender")
    assert len(parsed_list) == 1
    parsed = parsed_list[0]
    notice = parsed.notice

    assert notice.ref == "066188-2026"
    assert notice.ocid == "ocds-h6vhtk-06cac6"
    assert notice.title == "Legacy Infrastructure Support"
    assert notice.buyer == "Transport for London"
    assert notice.notice_type == "UK2"
    assert notice.uk_stage == "UK2"
    assert notice.indicative_value is None

    # This notice has no tender.classification or item classification, only
    # additionalClassifications, so the primary CPV is inferred from those.
    assert notice.cpv_primary == "48800000"
    assert notice.cpv_primary_inferred is True
    assert notice.cpv_additional == ["48800000", "50300000", "72100000"]

    assert parsed.tender_status == "planning"
    assert parsed.lot_statuses == ["planning"]
    assert parsed.tender_period_end is None
    assert parsed.pme_due_date == "2026-08-07T23:59:59+01:00"
    assert notice.deadline == "2026-08-07T23:59:59+01:00"
    assert parsed.future_notice_date == "2026-09-08T23:59:59+01:00"
    assert parsed.contract_end_date == "2031-07-12T23:59:59+01:00"
    assert parsed.is_award is False

    assert "legacy infrastructure support" in parsed.text_blob
    assert notice.raw_json  # full release JSON retained as an evidence snapshot
