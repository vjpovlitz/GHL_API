import pytest

from ghl_api import alerts


def test_macos_enabled_respects_env(monkeypatch):
    monkeypatch.setenv("ALERT_MACOS", "1")
    assert alerts._macos_enabled() is True
    monkeypatch.setenv("ALERT_MACOS", "0")
    assert alerts._macos_enabled() is False
    monkeypatch.setenv("ALERT_MACOS", "yes")
    assert alerts._macos_enabled() is True


def test_webhook_only_fires_when_url_set(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setenv("ALERT_MACOS", "0")

    def fake_post(url, json, timeout):
        calls.append((url, json))
        class R:
            def raise_for_status(self): pass
        return R()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)

    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    alerts.send_alert("subj", "body")
    assert calls == []

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example/x")
    alerts.send_alert("subj", "body")
    assert len(calls) == 1
    url, payload = calls[0]
    assert url == "https://hooks.example/x"
    # Slack ("text") and Discord ("content") keys both present.
    assert "text" in payload and "content" in payload


def test_send_alert_never_raises_when_channel_throws(monkeypatch):
    monkeypatch.setenv("ALERT_MACOS", "1")
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example/x")

    def boom(*a, **k):
        raise RuntimeError("channel down")

    monkeypatch.setattr(alerts.subprocess, "run", boom)
    import httpx
    monkeypatch.setattr(httpx, "post", boom)

    # Must swallow both failures and return None without raising.
    assert alerts.send_alert("subj", "body") is None


def test_macos_disabled_skips_osascript(monkeypatch):
    monkeypatch.setenv("ALERT_MACOS", "0")
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    called = []
    monkeypatch.setattr(alerts.subprocess, "run", lambda *a, **k: called.append(a))
    alerts.send_alert("subj", "body")
    assert called == []
