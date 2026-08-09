"""SMTP email sending for dashboard account invites. Same SMTP-over-Graph
approach as the sibling app (new-app/notifications.py) -- Microsoft Graph
needs an Azure AD app registration that was never completed for this app
(see graph/mail.py), so invite emails go out over plain SMTP instead, using
whatever mailbox SMTP_* points at.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


class NotificationError(RuntimeError):
    """Raised when an email can't be sent. Never includes SMTP_PASSWORD (or
    any other credential) in the message."""


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise NotificationError(
            f"Missing required environment variable: {name}. Set it in your .env file."
        )
    return value


def send_email(to_address: str, subject: str, body: str) -> None:
    """Send a plain-text email via SMTP. Raises NotificationError on failure."""
    host = _require_env("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() not in ("false", "0", "no")
    sender = _require_env("NOTIFICATION_SENDER_EMAIL")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to_address
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password or "")
            smtp.send_message(message)
    except smtplib.SMTPException as exc:
        raise NotificationError(f"Failed to send email: {exc}") from exc
    except OSError as exc:
        raise NotificationError(f"Could not reach the SMTP server: {exc}") from exc


def send_account_invite_email(
    to_address: str, display_name: str, app_url: str, login_identifier: str, temp_password: str
) -> None:
    """Sent when the admin screen creates a new dashboard account."""
    body = (
        f"Hi {display_name},\n\n"
        f"An account has been created for you on Savvy Scout: {app_url}\n\n"
        "Log in with:\n"
        f"  Email: {login_identifier}\n"
        f"  Temporary password: {temp_password}\n\n"
        "This is a temporary password -- ask Mark to reset it if you'd like a new one.\n"
    )
    send_email(to_address, "Your Savvy Scout account is ready", body)


def send_account_link_email(to_address: str, display_name: str, app_url: str) -> None:
    """Sent when an admin sets an email on an account that ALREADY has
    access (2026-08-09) -- e.g. backfilling contact info for one of the four
    originally-seeded accounts. Deliberately no password here (unlike
    send_account_invite_email): this isn't a new account, just handing over
    the link since the person already knows their own login."""
    body = (
        f"Hi {display_name},\n\n"
        f"Your email is now linked to your existing Savvy Scout account: {app_url}\n\n"
        "Log in with your usual username/password.\n"
    )
    send_email(to_address, "Your Savvy Scout app link", body)


def send_new_opportunity_email(
    to_address: str, display_name: str, ref: str, title: str, buyer: str | None,
    deadline: str | None, app_url: str, notice_id: int,
) -> None:
    """Sent to a sector owner the first time a new notice is triaged and
    assigned to them (2026-08-09), so an opportunity doesn't just sit
    unnoticed in the in-app "needs attention" badge until they next open the
    dashboard."""
    body = (
        f"Hi {display_name},\n\n"
        f"A new opportunity has been assigned to you on Savvy Scout:\n\n"
        f"  {title}\n"
        f"  Buyer: {buyer or 'Unknown'}\n"
        f"  Reference: {ref}\n"
        f"  Deadline: {deadline or 'Not stated'}\n\n"
        f"View it here: {app_url}/notices/{notice_id}\n"
    )
    send_email(to_address, f"New opportunity: {title}", body)


def send_new_opportunity_teams_message(
    webhook_url: str, display_name: str, ref: str, title: str, buyer: str | None,
    deadline: str | None, app_url: str, notice_id: int,
) -> None:
    """Posts the same new-opportunity alert to the owner's configured Teams
    incoming webhook (2026-08-09). Uses the legacy Office 365 Connector
    MessageCard format -- still the format Teams incoming webhooks accept,
    and needs no Azure AD app registration (unlike a real per-user Graph
    chat message, which this app has no permissions for)."""
    import requests

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"New opportunity: {title}",
        "themeColor": "AF1F23",
        "title": f"New opportunity assigned to {display_name}",
        "text": (
            f"**{title}**\n\n"
            f"Buyer: {buyer or 'Unknown'}  \n"
            f"Reference: {ref}  \n"
            f"Deadline: {deadline or 'Not stated'}"
        ),
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "View in Savvy Scout",
                "targets": [{"os": "default", "uri": f"{app_url}/notices/{notice_id}"}],
            }
        ] if app_url else [],
    }
    try:
        response = requests.post(webhook_url, json=card, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise NotificationError(f"Failed to post Teams notification: {exc}") from exc
