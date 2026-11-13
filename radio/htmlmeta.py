"""Read metadata (OGP, dates, links) out of an HTML page without executing anything."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.links: list[str] = []
        self.icons: list[str] = []
        self.times: list[str] = []
        self.jsonld: list[str] = []
        self.title = ""
        self._in_title = False
        self._in_jsonld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "link" and "icon" in a.get("rel", "").lower() and a.get("href"):
            self.icons.append(a["href"])
        elif tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_jsonld, self._buf = True, []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            self.jsonld.append("".join(self._buf))

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_jsonld:
            self._buf.append(data)


def _jsonld_dates(blobs: list[str]) -> tuple[str | None, str | None]:
    published = modified = None

    def walk(node):
        nonlocal published, modified
        if isinstance(node, dict):
            published = published or node.get("datePublished")
            modified = modified or node.get("dateModified")
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for blob in blobs:
        try:
            walk(json.loads(blob))
        except (json.JSONDecodeError, TypeError):
            continue
    return published, modified


def parse(html: str, base_url: str) -> dict:
    p = _MetaParser()
    try:
        p.feed(html)
    except Exception:  # malformed HTML: keep what was read so far
        pass
    m = p.meta
    ld_pub, ld_mod = _jsonld_dates(p.jsonld)
    published = m.get("article:published_time") or m.get("og:published_time") or ld_pub or m.get("date") \
        or m.get("datepublished") or (p.times[0] if p.times else None)
    modified = m.get("article:modified_time") or m.get("og:updated_time") or ld_mod
    image = m.get("og:image") or m.get("og:image:url") or m.get("twitter:image")
    icon = p.icons[0] if p.icons else None
    return {
        "title": (m.get("og:title") or m.get("twitter:title") or p.title or "").strip(),
        "site": m.get("og:site_name") or None,
        "description": (m.get("og:description") or m.get("description") or "").strip() or None,
        "image": urljoin(base_url, image) if image else None,
        "icon": urljoin(base_url, icon) if icon else None,
        "published": published,
        "modified": modified,
        "links": [urljoin(base_url, h) for h in p.links],
    }


TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def strip_tags(text: str, limit: int = 600) -> str:
    from html import unescape
    clean = WS_RE.sub(" ", unescape(TAG_RE.sub(" ", text or ""))).strip()
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"
