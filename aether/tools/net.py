"""Network tools: generic HTTP API calls and file downloads. No API keys."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from .base import Tool
from .files import _WorkspaceTool
from .web import HEADERS

MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024  # 200 MB safety cap
_INTERESTING_HEADERS = (
    "content-type", "content-length", "location", "server", "date", "allow",
)


class HttpRequest(Tool):
    name = "http_request"
    description = (
        "Call any HTTP(S) API with a chosen method, headers and body; returns "
        "the status code, key response headers and the body. Use this for JSON "
        "REST APIs - fetch_url is only for reading pages as text."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {
                "type": "string",
                "description": "GET (default), POST, PUT, PATCH, DELETE or HEAD.",
            },
            "headers": {"type": "object", "description": "Extra request headers."},
            "body": {"type": "string", "description": "Raw request body."},
            "json": {"type": "object", "description": "JSON body (takes priority over 'body')."},
            "timeout": {"type": "integer", "description": "Seconds (default 30, max 120)."},
        },
        "required": ["url"],
    }

    def run(self, args: dict) -> str:
        url = str(args.get("url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return "ERROR: provide a valid http(s) URL."

        method = str(args.get("method") or "GET").upper()
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"):
            return f"ERROR: unsupported method '{method}'."

        timeout = min(max(int(args.get("timeout") or 30), 1), 120)
        headers = dict(HEADERS)
        headers.update({str(k): str(v) for k, v in (args.get("headers") or {}).items()})

        json_body = args.get("json")
        if json_body is not None and not isinstance(json_body, dict):
            return "ERROR: 'json' must be an object (key/value map)."

        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                data=None if json_body is not None else str(args.get("body") or "") or None,
                json=json_body,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            return f"ERROR: request failed: {exc}"

        meta = [f"HTTP {resp.status_code} {resp.reason}", f"final_url: {resp.url}"]
        meta += [
            f"{k}: {v}"
            for k, v in resp.headers.items()
            if k.lower() in _INTERESTING_HEADERS
        ]
        payload = resp.content[:200_000].decode("utf-8", errors="replace")
        return "\n".join(meta) + "\n\n" + payload


class DownloadFile(_WorkspaceTool):
    name = "download_file"
    description = (
        "Download a file from a URL into the workspace - images, PDFs, "
        "archives, datasets, any binary that fetch_url refuses. Returns the "
        "saved path and size. Hard limit 200 MB."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "path": {
                "type": "string",
                "description": "Destination path in the workspace (default: filename from the URL).",
            },
        },
        "required": ["url"],
    }

    def run(self, args: dict) -> str:
        url = str(args.get("url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return "ERROR: provide a valid http(s) URL."

        default_name = Path(unquote(parsed.path)).name or "download.bin"
        dest = self._resolve(str(args.get("path") or "").strip() or default_name)
        if dest.is_dir():
            return f"ERROR: {dest} is a directory; pick a file path."
        dest.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        try:
            with requests.get(
                url, headers=HEADERS, timeout=60, stream=True, allow_redirects=True
            ) as resp:
                resp.raise_for_status()
                declared = int(resp.headers.get("Content-Length") or 0)
                if declared > MAX_DOWNLOAD_BYTES:
                    return (
                        f"ERROR: file is {declared} bytes; limit is "
                        f"{MAX_DOWNLOAD_BYTES}."
                    )
                with dest.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=65536):
                        written += len(chunk)
                        if written > MAX_DOWNLOAD_BYTES:
                            break
                        fh.write(chunk)
        except requests.RequestException as exc:
            dest.unlink(missing_ok=True)
            return f"ERROR: download failed: {exc}"

        if written > MAX_DOWNLOAD_BYTES:
            dest.unlink(missing_ok=True)
            return f"ERROR: download exceeded {MAX_DOWNLOAD_BYTES} bytes; aborted and removed."

        return f"Saved {dest} ({written} bytes)."
