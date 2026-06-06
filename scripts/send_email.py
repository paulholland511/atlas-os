#!/usr/bin/env python3
"""
Eidetic OS Email Sender — sends email via SMTP (e.g. Gmail) with optional
attachments.

This is a TEMPLATE. It contains NO credentials. The SMTP app password is read
from the SMTP_APP_PASSWORD environment variable; the sender address and SMTP
server are configurable via environment variables too. Nothing is hardcoded.

For Gmail, generate an app password at
https://myaccount.google.com/apppasswords (requires 2FA), then export it:

    export SMTP_APP_PASSWORD="your-16-char-app-password"
    export SENDER_EMAIL="your-eidetic-account@example.com"

Environment variables:
    SMTP_APP_PASSWORD   App password / SMTP password   (required)
    SENDER_EMAIL        From address                   (required)
    SENDER_NAME         Display name                   (default: Eidetic)
    SMTP_SERVER         SMTP host                      (default: smtp.gmail.com)
    SMTP_PORT           SMTP port                      (default: 587)

Usage:
    python send_email.py '{"to":"someone@example.com","subject":"Hi",
                           "body_html":"<p>Hello</p>","attachments":["/path/file.pdf"]}'
"""
import json
import os
import smtplib
import socket
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from _bootstrap import ensure_eidetic_os

ensure_eidetic_os()
from eidetic_os import retry as retrylib  # noqa: E402
from eidetic_os import scriptkit  # noqa: E402

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SENDER_NAME = os.environ.get("SENDER_NAME", "Eidetic")
# Socket timeout (seconds) for every SMTP operation, so a wedged server can't
# hang the send forever. Overridable via SMTP_TIMEOUT.
SMTP_TIMEOUT = float(os.environ.get("SMTP_TIMEOUT", "30"))

# Transient SMTP/socket failures worth retrying with backoff. A bare ``OSError``
# (e.g. a definitive misconfiguration) is intentionally *not* here, so it fails
# fast instead of retrying pointlessly.
_SMTP_TRANSIENT: tuple[type[BaseException], ...] = (
    smtplib.SMTPConnectError,
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPHeloError,
    ConnectionError,
    TimeoutError,
    socket.timeout,
    socket.gaierror,
)
_SMTP_RETRY_POLICY = retrylib.RetryPolicy(
    attempts=3, base_delay=1.0, backoff=2.0, retry_on=_SMTP_TRANSIENT
)


def get_app_password() -> str:
    """Read the SMTP app password from the environment. Never hardcode secrets."""
    password = os.environ.get("SMTP_APP_PASSWORD", "").strip()
    if not password:
        print("ERROR: SMTP_APP_PASSWORD environment variable is not set.")
        print("To set up (Gmail):")
        print("  1. Go to https://myaccount.google.com/apppasswords")
        print("  2. Generate an app password for 'Mail'")
        print("  3. export SMTP_APP_PASSWORD='your-app-password'")
        sys.exit(scriptkit.EXIT_CONFIG)
    return password


def _deliver(msg: MIMEMultipart, recipients: list[str], app_password: str) -> None:
    """One SMTP delivery attempt with an explicit timeout (retried by caller)."""
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=SMTP_TIMEOUT)
    try:
        server.starttls()
        server.login(SENDER_EMAIL, app_password)
        server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 - closing a broken connection is best-effort
            pass


def send_email(to, subject, body_html=None, body_text=None, attachments=None) -> bool:
    """Send an email via SMTP with STARTTLS."""
    if not SENDER_EMAIL:
        print("ERROR: SENDER_EMAIL environment variable is not set.")
        sys.exit(scriptkit.EXIT_CONFIG)

    app_password = get_app_password()

    msg = MIMEMultipart("mixed")
    msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"] = to if isinstance(to, str) else ", ".join(to)
    msg["Subject"] = subject

    alt = MIMEMultipart("alternative")
    if body_text:
        alt.attach(MIMEText(body_text, "plain"))
    if body_html:
        alt.attach(MIMEText(body_html, "html"))
    elif body_text:
        alt.attach(MIMEText(body_text, "plain"))
    msg.attach(alt)

    if attachments:
        for filepath in attachments:
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{os.path.basename(filepath)}"',
                )
                msg.attach(part)
            else:
                print(f"WARNING: Attachment not found: {filepath}")

    recipients = [to] if isinstance(to, str) else list(to)

    def _on_retry(exc: BaseException, attempt: int, delay: float) -> None:
        print(
            f"SMTP attempt {attempt} failed ({exc}); retrying in {delay:.0f}s…",
            file=sys.stderr,
        )

    try:
        retrylib.retry_call(
            _deliver, msg, recipients, app_password,
            policy=_SMTP_RETRY_POLICY, on_retry=_on_retry,
        )
        print(f"Email sent successfully to {msg['To']}")
        return True
    except Exception as e:  # noqa: BLE001 - report any send failure, never traceback
        print(f"ERROR sending email: {e}")
        return False


def main() -> int:
    if len(sys.argv) <= 1:
        print(
            'Usage: python send_email.py \'{"to":"someone@example.com",'
            '"subject":"sub","body_html":"<p>content</p>",'
            '"attachments":["/path/file.pdf"]}\''
        )
        return scriptkit.EXIT_CONFIG
    try:
        data = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        return scriptkit.emit_error(f"Invalid JSON payload: {exc}", code=scriptkit.EXIT_CONFIG)
    ok = send_email(
        to=data["to"],
        subject=data["subject"],
        body_html=data.get("body_html"),
        body_text=data.get("body_text"),
        attachments=data.get("attachments"),
    )
    return scriptkit.EXIT_OK if ok else scriptkit.EXIT_ERROR


if __name__ == "__main__":
    with scriptkit.error_boundary():
        sys.exit(main())
