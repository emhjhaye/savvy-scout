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
