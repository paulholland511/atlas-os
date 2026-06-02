"""Tests for scripts/send_email.py — credential handling and SMTP send flow."""

from __future__ import annotations

import pytest

import send_email


def test_module_imports() -> None:
    assert hasattr(send_email, "send_email")
    assert hasattr(send_email, "get_app_password")


class TestGetAppPassword:
    def test_returns_password_when_set(self, monkeypatch) -> None:
        monkeypatch.setenv("SMTP_APP_PASSWORD", "  hunter2  ")
        assert send_email.get_app_password() == "hunter2"

    def test_exits_when_missing(self, monkeypatch) -> None:
        monkeypatch.delenv("SMTP_APP_PASSWORD", raising=False)
        with pytest.raises(SystemExit):
            send_email.get_app_password()


class _FakeSMTP:
    """Records interactions instead of touching the network."""

    instances: list["_FakeSMTP"] = []

    def __init__(self, server: str, port: int) -> None:
        self.server = server
        self.port = port
        self.started_tls = False
        self.logged_in: tuple[str, str] | None = None
        self.sent: tuple[str, list[str], str] | None = None
        self.quit_called = False
        _FakeSMTP.instances.append(self)

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.logged_in = (user, password)

    def sendmail(self, sender: str, recipients: list[str], message: str) -> None:
        self.sent = (sender, recipients, message)

    def quit(self) -> None:
        self.quit_called = True


@pytest.fixture
def fake_smtp(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(send_email.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(send_email, "SENDER_EMAIL", "atlas@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "app-pass")
    return _FakeSMTP


def test_send_email_success(fake_smtp) -> None:
    ok = send_email.send_email(
        to="someone@example.com",
        subject="Hi",
        body_html="<p>Hello</p>",
    )
    assert ok is True
    smtp = fake_smtp.instances[0]
    assert smtp.started_tls is True
    assert smtp.logged_in == ("atlas@example.com", "app-pass")
    assert smtp.sent is not None
    assert smtp.sent[1] == ["someone@example.com"]
    assert smtp.quit_called is True


def test_send_email_multiple_recipients(fake_smtp) -> None:
    ok = send_email.send_email(
        to=["a@example.com", "b@example.com"],
        subject="Hi",
        body_text="plain",
    )
    assert ok is True
    assert fake_smtp.instances[0].sent[1] == ["a@example.com", "b@example.com"]


def test_send_email_with_attachment(fake_smtp, tmp_path) -> None:
    attachment = tmp_path / "report.pdf"
    attachment.write_bytes(b"%PDF-1.4 fake")
    ok = send_email.send_email(
        to="someone@example.com",
        subject="Report",
        body_html="<p>see attached</p>",
        attachments=[str(attachment)],
    )
    assert ok is True
    # filename should appear in the MIME payload
    assert "report.pdf" in fake_smtp.instances[0].sent[2]


def test_send_email_missing_attachment_still_sends(fake_smtp, tmp_path) -> None:
    ok = send_email.send_email(
        to="someone@example.com",
        subject="Report",
        body_text="body",
        attachments=[str(tmp_path / "does-not-exist.pdf")],
    )
    assert ok is True


def test_send_email_returns_false_on_smtp_failure(monkeypatch) -> None:
    def boom(server, port):
        raise OSError("connection refused")

    monkeypatch.setattr(send_email.smtplib, "SMTP", boom)
    monkeypatch.setattr(send_email, "SENDER_EMAIL", "atlas@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "app-pass")
    ok = send_email.send_email(to="x@example.com", subject="s", body_text="b")
    assert ok is False
