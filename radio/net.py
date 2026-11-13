"""HTTP access with a polite User-Agent, robots.txt checks and URL normalisation.

Everything fetched from the web is untrusted data: callers only parse it, never execute it.
"""
from __future__ import annotations

import time
import urllib.robotparser
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from .config import settings

TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref_src"}
MAX_BYTES = 3_000_000


def user_agent() -> str:
    return settings().get("collect", {}).get("user_agent", "AIDiscoveryRadio/0.1")


def timeout() -> int:
    return int(settings().get("collect", {}).get("timeout_sec", 20))


_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": user_agent(), "Accept-Language": "en,ja;q=0.8"})
    return _session


def normalize_url(url: str) -> str:
    """Canonical form for de-duplication: https, no tracking params, no fragment, no trailing slash."""
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, parts.netloc.lower(), path, urlencode(query), ""))


@lru_cache(maxsize=256)
def _robots(origin: str) -> urllib.robotparser.RobotFileParser | None:
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = session().get(origin + "/robots.txt", timeout=timeout())
    except requests.RequestException:
        return None  # robots.txt unreachable: treat as no rules
    if r.status_code in (401, 403):
        rp.disallow_all = True
        return rp
    if r.status_code >= 400:
        return None
    rp.parse(r.text.splitlines())
    return rp


def robots_allowed(url: str) -> bool:
    parts = urlsplit(url)
    rp = _robots(f"{parts.scheme}://{parts.netloc}")
    return True if rp is None else rp.can_fetch(user_agent(), url)


def get(url: str, *, check_robots: bool = False, retries: int = 1, **kw) -> requests.Response:
    if check_robots and not robots_allowed(url):
        raise PermissionError(f"robots.txt disallows {url}")
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = session().get(url, timeout=timeout(), stream=True, **kw)
            r._content = r.raw.read(MAX_BYTES, decode_content=True)  # cap the size of what we read
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]


def check_url(url: str) -> int:
    """HTTP status of a URL (GET, redirects followed). 0 means it could not be reached at all."""
    if urlsplit(url).scheme not in ("http", "https"):
        return 0
    try:
        r = session().get(url, timeout=timeout(), stream=True, allow_redirects=True)
        r.close()
        return r.status_code
    except requests.RequestException:
        return 0
