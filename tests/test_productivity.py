"""Productivity tools: send_email (dry-run) and create_calendar_event (.ics)."""

from __future__ import annotations


def test_send_email_requires_recipients(registry):
    out = registry.call("send_email", {"to": "", "subject": "s", "body": "b"})
    assert out.startswith("ERROR") and "'to'" in out


def test_send_email_requires_smtp_env(registry, monkeypatch):
    for var in ("AETHER_SMTP_HOST", "AETHER_SMTP_USER", "AETHER_SMTP_PASS"):
        monkeypatch.delenv(var, raising=False)
    out = registry.call("send_email", {"to": "a@b.co", "subject": "s", "body": "b"})
    assert out.startswith("ERROR") and "not configured" in out
    assert "AETHER_SMTP_HOST" in out


def test_send_email_dry_run_renders_message(registry, monkeypatch):
    monkeypatch.setenv("AETHER_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AETHER_SMTP_USER", "me@example.com")
    monkeypatch.setenv("AETHER_SMTP_PASS", "not-a-real-password")
    out = registry.call("send_email", {
        "to": "you@example.com, other@example.com",
        "subject": "hello",
        "body": "line one",
        "dry_run": True,
    })
    assert out.startswith("[dry run]")
    assert "you@example.com, other@example.com" in out
    assert "Subject: hello" in out
    assert "line one" in out


def test_calendar_event_written(registry, workspace):
    out = registry.call("create_calendar_event", {
        "title": "Standup",
        "start": "2026-01-15 09:30",
        "duration_minutes": 15,
        "location": "zoom",
    })
    assert "Calendar event written" in out
    ics_files = list((workspace / "calendar").glob("*.ics"))
    assert len(ics_files) == 1
    content = ics_files[0].read_text(encoding="utf-8")
    assert content.startswith("BEGIN:VCALENDAR")
    assert "SUMMARY:Standup" in content
    assert "LOCATION:zoom" in content
    assert "DTSTART:20260115" in content  # UTC-stamped
    assert b"\r\n" in ics_files[0].read_bytes()  # CRLF line endings per RFC 5545


def test_calendar_validation(registry):
    assert registry.call("create_calendar_event", {"start": "2026-01-15 09:30"}).startswith("ERROR")
    assert registry.call("create_calendar_event", {"title": "x", "start": "nonsense"}).startswith("ERROR")
    out = registry.call("create_calendar_event", {
        "title": "x", "start": "2026-01-15 10:00", "end": "2026-01-15 09:00",
    })
    assert out.startswith("ERROR") and "after" in out


def test_calendar_filename_cannot_escape(registry, workspace):
    out = registry.call("create_calendar_event", {
        "title": "Esc", "start": "2026-01-15 09:30",
        "filename": "../evil.ics",
    })
    assert "Calendar event written" in out
    assert (workspace / "evil.ics").exists() is False
    assert (workspace / "calendar" / "evil.ics").exists()
