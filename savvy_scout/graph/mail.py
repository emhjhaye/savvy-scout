"""Microsoft Graph mail sending. SPEC.md non-negotiable 2: outbound email is
whitelisted to @bidsavvy.io addresses only, the tool must never contact a
buyer, a portal, or Trifork directly. assert_whitelisted() is a hard,
non-bypassable check run before every single send in this module -- there is
no send path that skips it.

Needs an Azure AD app registration (client credentials flow, Mail.Send
application permission) -- an external setup step, see README. The send
function is written and unit-testable (the whitelist gate) before that
registration exists."""

import base64
from pathlib import Path

import requests

ALLOWED_DOMAIN = "bidsavvy.io"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
REQUEST_TIMEOUT_SECONDS = 30


class WhitelistViolation(ValueError):
    pass


def assert_whitelisted(recipient: str) -> None:
    """Raises WhitelistViolation unless recipient is an @bidsavvy.io address.
    Call this before every Graph send; never send conditionally on a flag."""
    if "@" not in recipient:
        raise WhitelistViolation(f"'{recipient}' is not a valid email address")
    domain = recipient.rsplit("@", 1)[-1].lower()
    if domain != ALLOWED_DOMAIN:
        raise WhitelistViolation(
            f"Refusing to send to {recipient}: outbound email is whitelisted to "
            f"@{ALLOWED_DOMAIN} addresses only (SPEC.md non-negotiable 2)."
        )


def _get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    response = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def send_escalation_email(
    recipient: str,
    subject: str,
    body_text: str,
    attachment_path: str,
    sender_upn: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
) -> None:
    """Sends one email with one file attachment via Microsoft Graph, from
    sender_upn's mailbox (a service account or an @bidsavvy.io mailbox with
    delegated send-as rights). Raises WhitelistViolation before any network
    call if recipient is not @bidsavvy.io."""
    assert_whitelisted(recipient)

    token = _get_access_token(tenant_id, client_id, client_secret)
    attachment_bytes = Path(attachment_path).read_bytes()

    message = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body_text},
            "toRecipients": [{"emailAddress": {"address": recipient}}],
            "attachments": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": Path(attachment_path).name,
                    "contentBytes": base64.b64encode(attachment_bytes).decode("ascii"),
                }
            ],
        },
        "saveToSentItems": "true",
    }

    response = requests.post(
        f"{GRAPH_BASE_URL}/users/{sender_upn}/sendMail",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=message,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
