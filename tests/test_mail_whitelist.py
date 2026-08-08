from unittest.mock import patch

import pytest

from savvy_scout.graph.mail import WhitelistViolation, assert_whitelisted, send_escalation_email


def test_assert_whitelisted_allows_bidsavvy_domain():
    assert_whitelisted("victoria.milan@bidsavvy.io")  # should not raise


def test_assert_whitelisted_rejects_other_domains():
    with pytest.raises(WhitelistViolation):
        assert_whitelisted("buyer@some-council.gov.uk")


def test_assert_whitelisted_rejects_malformed_address():
    with pytest.raises(WhitelistViolation):
        assert_whitelisted("not-an-email")


def test_send_escalation_email_never_calls_graph_for_non_whitelisted_recipient(tmp_path):
    attachment = tmp_path / "brief.docx"
    attachment.write_bytes(b"fake docx content")

    with patch("savvy_scout.graph.mail.requests.post") as mock_post:
        with pytest.raises(WhitelistViolation):
            send_escalation_email(
                recipient="buyer@some-council.gov.uk",
                subject="TRIAGE ESCALATION: Test",
                body_text="body",
                attachment_path=str(attachment),
                sender_upn="sender@bidsavvy.io",
                tenant_id="tenant",
                client_id="client",
                client_secret="secret",
            )
        mock_post.assert_not_called()
