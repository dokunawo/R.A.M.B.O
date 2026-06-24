import echo_messaging


def _clear(monkeypatch):
    for v in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "ECHO_DEFAULT_TO"):
        monkeypatch.delenv(v, raising=False)


def test_offline_when_unconfigured(monkeypatch):
    _clear(monkeypatch)
    assert echo_messaging.is_configured() is False
    assert echo_messaging.status()["status"] == "OFFLINE"
    r = echo_messaging.send_email("hi", "body")
    assert r["sent"] is False
    assert "OFFLINE" in r["detail"]


def test_connected_status_when_configured(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "u@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    # SMTP_FROM defaults to SMTP_USER when unset.
    assert echo_messaging.is_configured() is True
    s = echo_messaging.status()
    assert s["status"] == "CONNECTED"
    assert s["agent"] == "echo"


def test_send_needs_recipient(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "u@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    # configured but no recipient and no ECHO_DEFAULT_TO
    r = echo_messaging.send_email("subject", "body")
    assert r["sent"] is False
    assert "recipient" in r["detail"].lower()
