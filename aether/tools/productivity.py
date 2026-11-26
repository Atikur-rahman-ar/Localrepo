"""Productivity tools: email (SMTP) and calendar events (.ics files).

Both are free and dependency-free (standard library only). Neither stores
credentials anywhere: SMTP settings are read from the environment at call
time, so keys live in your shell profile or server unit file, never in code.

Environment variables for ``send_email``:

    AETHER_SMTP_HOST     e.g. smtp.gmail.com
    AETHER_SMTP_PORT     default 587
    AETHER_SMTP_USER     login username (usually your address)
    AETHER_SMTP_PASS     password or app-specific password
    AETHER_SMTP_STARTTLS "0" to disable STARTTLS (default on)
"""

from __future__ import annotations

import os
import re
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from .base import Tool

_EMAIL_SPLIT = re.compile(r"[;,]\s*")
_ICAL_TEXT_ESCAPE = {"\\": "\\\\", ";": "\\;", ",": "\\,", "\n": "\\n"}


def _ics_escape(text: str) -> str:
    return "".join(_ICAL_TEXT_ESCAPE.get(ch, ch) for ch in str(text))


def _ics_fold(line: str) -> str:
    """RFC 5545 line folding: max 75 octets per line, continuations start with a space."""
    out, encoded = [], line.encode("utf-8")
    while len(encoded) > 74:
        cut = 74
        # never split inside a UTF-8 multi-byte sequence
        while cut > 0 and (encoded[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(encoded[:cut].decode("utf-8"))
        encoded = b" " + encoded[cut:]
    out.append(encoded.decode("utf-8"))
    return "\r\n".join(out)


def _parse_local(value: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM' (local time) or a full ISO-8601 stamp."""
    value = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H"):
        try:
            return datetime.strptime(value, fmt).astimezone()
        except ValueError:
            continue
    dt = datetime.fromisoformat(value)  # full ISO string, incl. offsets
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def _ics_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class SendEmail(Tool):
    """SMTP email tool - configuration comes from the environment."""

    name = "send_email"
    description = (
        "Send an email via SMTP. Requires the server to set AETHER_SMTP_HOST, "
        "AETHER_SMTP_PORT, AETHER_SMTP_USER and AETHER_SMTP_PASS environment "
        "variables. Use dry_run=true to preview without sending."
    )
    parameters = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "One address, or several separated by ; or ,"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "cc": {"type": "string", "description": "Optional, same rules as 'to'"},
            "dry_run": {
                "type": "boolean",
                "description": "Render the message and return it without sending.",
            },
        },
        "required": ["to", "subject", "body"],
    }

    def _addresses(self, raw: str) -> list[str]:
        return [a.strip() for a in _EMAIL_SPLIT.split(raw or "") if a.strip()]

    def run(self, args: dict) -> str:
        host = os.environ.get("AETHER_SMTP_HOST", "")
        user = os.environ.get("AETHER_SMTP_USER", "")
        password = os.environ.get("AETHER_SMTP_PASS", "")
        port = int(os.environ.get("AETHER_SMTP_PORT", "587") or "587")
        starttls = os.environ.get("AETHER_SMTP_STARTTLS", "1") not in ("0", "false", "no")

        to = self._addresses(str(args.get("to", "")))
        cc = self._addresses(str(args.get("cc", "")))
        subject = str(args.get("subject", ""))
        body = str(args.get("body", ""))

        if not to:
            return "ERROR: 'to' must contain at least one email address."

        if not host or not user or not password:
            missing = [
                name
                for name, value in (
                    ("AETHER_SMTP_HOST", host),
                    ("AETHER_SMTP_USER", user),
                    ("AETHER_SMTP_PASS", password),
                )
                if not value
            ]
            return (
                "ERROR: send_email is not configured on this server. "
                "Set these environment variables first: " + ", ".join(missing)
            )

        msg = EmailMessage()
        msg["From"] = user
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        msg.set_content(body)
        msg["Message-ID"] = make_msgid()

        if args.get("dry_run"):
            preview = msg.as_string()
            return f"[dry run] message rendered, not sent:\n\n{preview}"

        context = ssl.create_default_context()
        try:
            if starttls:
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.login(user, password)
                    smtp.send_message(msg)
            else:  # implicit TLS (port 465 style)
                with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
                    smtp.login(user, password)
                    smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            return f"ERROR: SMTP send failed: {exc.__class__.__name__}: {exc}"

        recipients = ", ".join(to + cc)
        return f"Email sent to {recipients} (subject: {subject})."


class CreateCalendarEvent(Tool):
    """Write a standards-compliant .ics calendar event into the workspace.

    Pure standard library: the produced file imports into Google Calendar,
    Outlook, Apple Calendar and GNOME Calendar. Times given as local
    'YYYY-MM-DD HH:MM' are converted to UTC in the file.
    """

    name = "create_calendar_event"
    description = (
        "Create a calendar event file (.ics) in the workspace - importable into "
        "Google Calendar, Outlook and Apple Calendar. Give times as "
        "'YYYY-MM-DD HH:MM' (local time)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "start": {"type": "string", "description": "e.g. 2026-01-15 09:30 (local time)"},
            "end": {"type": "string", "description": "either end or duration_minutes"},
            "duration_minutes": {"type": "integer"},
            "location": {"type": "string"},
            "description": {"type": "string"},
            "filename": {"type": "string", "description": "output file name, .ics added if missing"},
        },
        "required": ["title", "start"],
    }

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def run(self, args: dict) -> str:
        title = str(args.get("title", "")).strip()
        start_raw = str(args.get("start", "")).strip()
        if not title or not start_raw:
            return "ERROR: 'title' and 'start' are required."

        try:
            start = _parse_local(start_raw)
        except ValueError:
            return "ERROR: 'start' must look like '2026-01-15 09:30' or a full ISO-8601 stamp."

        if args.get("end"):
            try:
                end = _parse_local(str(args["end"]))
            except ValueError:
                return "ERROR: 'end' must look like '2026-01-15 10:30' or a full ISO-8601 stamp."
            if end <= start:
                return "ERROR: 'end' must be after 'start'."
        else:
            minutes = int(args.get("duration_minutes", 30) or 30)
            end = start + timedelta(minutes=minutes)

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Aether//Calendar tool//EN",
            "CALSCALE:GREGORIAN",
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4().hex}@aether.local",
            f"DTSTAMP:{_ics_utc(datetime.now(timezone.utc))}",
            f"DTSTART:{_ics_utc(start)}",
            f"DTEND:{_ics_utc(end)}",
            f"SUMMARY:{_ics_escape(title)}",
        ]
        if args.get("location"):
            lines.append(f"LOCATION:{_ics_escape(str(args['location']))}")
        if args.get("description"):
            lines.append(f"DESCRIPTION:{_ics_escape(str(args['description']))}")
        lines += ["END:VEVENT", "END:VCALENDAR"]

        folded = "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"

        out_dir = self.workspace / "calendar"
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_name = str(args.get("filename") or "").strip()
        if raw_name:
            # basename only - never let the filename escape workspace/calendar
            raw_name = Path(raw_name.replace("\\", "/")).name
        if raw_name in ("", ".", ".."):
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "event"
            raw_name = f"{slug}-{start.strftime('%Y%m%d-%H%M')}"
        if not raw_name.endswith(".ics"):
            raw_name += ".ics"

        path = out_dir / raw_name
        path.write_text(folded, encoding="utf-8")
        return (
            f"Calendar event written: {path}\n"
            f"  '{title}' from {start.strftime('%Y-%m-%d %H:%M')} to "
            f"{end.strftime('%Y-%m-%d %H:%M')} (stored as UTC in the .ics file)."
        )
