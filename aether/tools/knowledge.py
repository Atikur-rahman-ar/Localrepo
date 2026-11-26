"""Keyless knowledge sources: Wikipedia, arXiv and GitHub public APIs."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

from .base import Tool
from .web import HEADERS

# Wikimedia's robot policy asks automated clients for a descriptive User-Agent.
WIKI_HEADERS = {
    **HEADERS,
    "User-Agent": "AetherAgent/1.0 (autonomous agent framework; +https://github.com/Atikur-rahman-ar/Localrepo)",
}


class SearchWikipedia(Tool):
    name = "search_wikipedia"
    description = (
        "Search Wikipedia for article titles, snippets and URLs. "
        "Set full_page=true to also pull the plain-text article extract of "
        "the top hit. No API key."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "language": {
                "type": "string",
                "description": "Wikipedia language code (default 'en', e.g. 'de', 'bn', 'zh').",
            },
            "full_page": {
                "type": "boolean",
                "description": "Also return the extracted plain text of the top result (default false).",
            },
            "max_results": {"type": "integer", "description": "Default 5, max 10."},
        },
        "required": ["query"],
    }

    def run(self, args: dict) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            return "ERROR: 'query' is required."
        lang = re.sub(r"[^a-z-]", "", str(args.get("language") or "en").lower()) or "en"
        limit = min(int(args.get("max_results") or 5), 10)
        api = f"https://{lang}.wikipedia.org/w/api.php"

        try:
            resp = requests.get(
                api,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": limit,
                    "format": "json",
                },
                headers=WIKI_HEADERS,
                timeout=30,
            )
        except requests.RequestException as exc:
            return f"ERROR: Wikipedia search failed: {exc}"

        if resp.status_code == 429:
            return (
                "ERROR: Wikipedia is throttling automated requests from this "
                "network. Wait a minute and retry, or use web_search/fetch_url."
            )
        if not resp.ok:
            return f"ERROR: Wikipedia API returned HTTP {resp.status_code}."

        hits = resp.json().get("query", {}).get("search", [])

        if not hits:
            return f"No Wikipedia results for '{query}'."

        lines = [
            f"- {h.get('title', '')}\n"
            f"  https://{lang}.wikipedia.org/wiki/{quote(str(h.get('title', '')).replace(' ', '_'))}\n"
            f"  {re.sub(r'<[^>]+>', '', str(h.get('snippet', '')))}"
            for h in hits
        ]
        out = "\n".join(lines)

        if args.get("full_page"):
            try:
                ext = requests.get(
                    api,
                    params={
                        "action": "query",
                        "prop": "extracts",
                        "explaintext": 1,
                        "format": "json",
                        "titles": hits[0].get("title", ""),
                    },
                    headers=WIKI_HEADERS,
                    timeout=30,
                ).json()
                for page in ext.get("query", {}).get("pages", {}).values():
                    extract = str(page.get("extract", "")).strip()
                    out += (
                        f"\n\n--- Full text of '{page.get('title')}' "
                        f"(truncated) ---\n{extract[:6000]}"
                    )
                    break
            except requests.RequestException as exc:
                out += f"\n\n(full-page extract failed: {exc})"
        return out


class SearchArxiv(Tool):
    name = "search_arxiv"
    description = (
        "Search arXiv for papers: titles, authors, dates, abstracts and PDF "
        "links. Query can use arXiv syntax like 'cat:cs.LG AND attention'. "
        "No API key."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "description": "Default 5, max 20."},
        },
        "required": ["query"],
    }

    NS = {"a": "http://www.w3.org/2005/Atom"}

    def run(self, args: dict) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            return "ERROR: 'query' is required."
        limit = min(int(args.get("max_results") or 5), 20)
        search = query if ":" in query.split()[0] else f"all:{query}"

        try:
            resp = requests.get(
                "https://export.arxiv.org/api/query",
                params={"search_query": search, "max_results": limit, "sortBy": "relevance"},
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            entries = ET.fromstring(resp.text).findall("a:entry", self.NS)
        except (requests.RequestException, ET.ParseError) as exc:
            return f"ERROR: arXiv search failed: {exc}"

        if not entries:
            return f"No arXiv results for '{query}'."

        lines = []
        for e in entries:
            title = " ".join(e.findtext("a:title", default="", namespaces=self.NS).split())
            summary = " ".join(
                e.findtext("a:summary", default="", namespaces=self.NS).split()
            )[:400]
            authors = [
                a.findtext("a:name", default="", namespaces=self.NS)
                for a in e.findall("a:author", self.NS)
            ][:4]
            pdf = next(
                (
                    l.get("href")
                    for l in e.findall("a:link", self.NS)
                    if l.get("type") == "application/pdf"
                ),
                e.findtext("a:id", default="", namespaces=self.NS),
            )
            date = e.findtext("a:published", default="", namespaces=self.NS)[:10]
            lines.append(
                f"- {title} ({date})\n"
                f"  {', '.join(a for a in authors if a)}\n"
                f"  PDF: {pdf}\n"
                f"  {summary}"
            )
        return "\n\n".join(lines)


class SearchGitHub(Tool):
    name = "search_github"
    description = (
        "Search GitHub for repositories, issues or users through the public "
        "API with full search syntax (e.g. 'agent framework language:python "
        "stars:>500'). No API key; anonymous search is rate-limited to ~10 "
        "requests/minute."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "kind": {"type": "string", "description": "'repos' (default), 'issues' or 'users'."},
            "max_results": {"type": "integer", "description": "Default 5, max 20."},
        },
        "required": ["query"],
    }

    def run(self, args: dict) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            return "ERROR: 'query' is required."
        kind = str(args.get("kind") or "repos").lower()
        if kind not in ("repos", "issues", "users"):
            return "ERROR: 'kind' must be repos, issues or users."
        endpoint = {"repos": "repositories", "issues": "issues", "users": "users"}[kind]
        limit = min(int(args.get("max_results") or 5), 20)

        try:
            resp = requests.get(
                f"https://api.github.com/search/{endpoint}",
                params={"q": query, "per_page": limit},
                headers=HEADERS,
                timeout=30,
            )
        except requests.RequestException as exc:
            return f"ERROR: GitHub search failed: {exc}"

        if resp.status_code == 403 or resp.status_code == 429:
            return "ERROR: GitHub anonymous rate limit hit (~10 searches/min). Wait a minute and retry."
        if resp.status_code == 422:
            return "ERROR: GitHub rejected the query syntax."
        resp.raise_for_status()

        items = resp.json().get("items", [])
        if not items:
            return f"No GitHub {kind} matching '{query}'."

        lines = []
        for it in items:
            if kind == "repos":
                lines.append(
                    f"- {it.get('full_name')} (stars: {it.get('stargazers_count', 0)})\n"
                    f"  {it.get('html_url')}\n"
                    f"  {str(it.get('description') or '')[:200]}"
                )
            elif kind == "issues":
                lines.append(
                    f"- [#{it.get('number')}] {it.get('title')} (state: {it.get('state')})\n"
                    f"  {it.get('html_url')}"
                )
            else:
                lines.append(f"- {it.get('login')} ({it.get('type')})\n  {it.get('html_url')}")
        return "\n".join(lines)
