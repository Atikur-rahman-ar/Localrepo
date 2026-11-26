"""Free web access: DuckDuckGo search + page fetching. No API keys."""

from __future__ import annotations

import html as html_mod
import re
from urllib.parse import parse_qs, unquote, urlparse

import requests

from .base import Tool

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _strip_tags(raw: str) -> str:
    raw = html_mod.unescape(raw)
    raw = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()


def _clean_ddg_url(raw: str) -> str:
    if raw.startswith("//"):
        raw = "https:" + raw
    if "uddg=" in raw:
        try:
            qs = parse_qs(urlparse(raw).query)
            return unquote(qs["uddg"][0])
        except Exception:  # noqa: BLE001
            pass
    return raw


class WebSearch(Tool):
    name = "web_search"
    description = (
        "Search the web with DuckDuckGo and get titles, URLs and snippets. "
        "No API key needed."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "description": "Default 6, max 10."},
        },
        "required": ["query"],
    }

    def run(self, args: dict) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            return "ERROR: 'query' is required."
        max_results = min(int(args.get("max_results") or 6), 10)

        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()

        results = []
        for block in re.split(r'class="result\b', resp.text)[1:]:
            link = re.search(
                r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                re.S,
            )
            if not link:
                continue
            url = _clean_ddg_url(link.group(1))
            title = _strip_tags(link.group(2))
            snippet_m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
            snippet = _strip_tags(snippet_m.group(1)) if snippet_m else ""
            if url:
                results.append(f"- {title}\n  {url}\n  {snippet[:300]}")
            if len(results) >= max_results:
                break

        if not results:
            return "No results parsed (DuckDuckGo markup may have changed). Try fetch_url on a known site."
        return "\n".join(results)


class FetchURL(Tool):
    name = "fetch_url"
    description = "Fetch a web page and return its readable text (HTML stripped)."
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    def run(self, args: dict) -> str:
        url = str(args.get("url", "")).strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return "ERROR: provide a valid http(s) URL."
        resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type and "text" not in content_type:
            return f"[non-text content: {content_type}; {len(resp.content)} bytes]"
        return _strip_tags(resp.text)
