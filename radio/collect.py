"""Step 1: gather candidate news from config/sources.yaml into work/candidates.json.

A source that fails is recorded in the report and skipped; the run goes on with the rest.
Only items with a verifiable publish date inside the window are kept.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import re
import sys
import time
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser

from . import htmlmeta, net
from .config import DATA_DIR, WORK_DIR, RadioError, load_yaml, now, read_json, settings, write_json

TRUST_WEIGHT = {"primary": 30, "secondary": 18, "community": 10}


def parse_date(value) -> dt.datetime | None:
    if not value:
        return None
    if isinstance(value, time.struct_time):
        return dt.datetime.fromtimestamp(calendar.timegm(value), dt.timezone.utc)
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, dt.timezone.utc)
    s = str(value).strip()
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            t = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _keyword_hit(text: str, keywords: list[str]) -> bool:
    low = text.lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(k.lower()) + r"(?![a-z0-9])", low) for k in keywords)


def _item(src: dict, title: str, url: str, published, updated=None, summary: str = "", extra: dict | None = None) -> dict:
    return {
        "title": htmlmeta.strip_tags(title, 300),
        "url": url,
        "published": published,
        "updated": updated,
        "summary": htmlmeta.strip_tags(summary, 600),
        "source_id": src["id"],
        "source_name": src["name"],
        "publisher": src["publisher"],
        "category": src["category"],
        "trust": src["trust"],
        "extra": extra or {},
    }


# ---------------- collectors ----------------

def collect_rss(src: dict) -> list[dict]:
    r = net.get(src["url"], retries=1)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"not a feed: {feed.bozo_exception}")
    out = []
    for e in feed.entries:
        link = e.get("link")
        if not link:
            continue
        pub = parse_date(e.get("published_parsed") or e.get("published") or e.get("updated_parsed"))
        upd = parse_date(e.get("updated_parsed") or e.get("updated"))
        summary = e.get("summary") or (e.get("content") or [{}])[0].get("value", "")
        out.append(_item(src, e.get("title", ""), link, pub, upd, summary))
    return out


def collect_html_links(src: dict, known: set[str]) -> list[dict]:
    r = net.get(src["url"], check_robots=True)
    r.raise_for_status()
    page = htmlmeta.parse(r.text, src["url"])
    pattern = re.compile(src["link_pattern"])
    links: list[str] = []
    for link in page["links"]:
        link = link.split("#")[0].rstrip("/")
        if pattern.match(link) and link not in links and link.rstrip("/") != src["url"].rstrip("/"):
            links.append(link)
    out = []
    for link in links[: int(src.get("max_links", 5))]:
        if net.normalize_url(link) in known:
            continue
        try:
            art = net.get(link, check_robots=True)
            if art.status_code >= 400:
                continue
        except Exception:  # robots disallow or network error on one article must not stop the source
            continue
        meta = htmlmeta.parse(art.text, link)
        out.append(_item(src, meta["title"], link, parse_date(meta["published"]), parse_date(meta["modified"]),
                         meta["description"] or ""))
        time.sleep(1.0)  # be gentle with sites that have no feed
    return out


def collect_hn(src: dict, since: dt.datetime) -> list[dict]:
    params = {"tags": "story", "numericFilters": f"points>={int(src.get('min_points', 100))},created_at_i>{int(since.timestamp())}",
              "hitsPerPage": 100}
    r = net.get(src["url"], params=params)
    r.raise_for_status()
    out = []
    for h in r.json().get("hits", []):
        url = h.get("url")
        if not url:
            continue
        out.append(_item(src, h.get("title", ""), url, parse_date(h.get("created_at")),
                         extra={"hn_points": h.get("points"), "hn_comments": h.get("num_comments"),
                                "discussion": f"https://news.ycombinator.com/item?id={h.get('objectID')}"}))
    return out


def collect_hf_papers(src: dict) -> list[dict]:
    r = net.get(src["url"])
    r.raise_for_status()
    out = []
    for p in r.json():
        paper = p.get("paper", {})
        upvotes = paper.get("upvotes", 0)
        if upvotes < int(src.get("min_upvotes", 0)) or not paper.get("id"):
            continue
        out.append(_item(src, paper.get("title") or p.get("title", ""), f"https://huggingface.co/papers/{paper['id']}",
                         parse_date(p.get("publishedAt") or paper.get("publishedAt")), None, paper.get("summary", ""),
                         extra={"upvotes": upvotes, "arxiv": f"https://arxiv.org/abs/{paper['id']}"}))
    return out


# ---------------- selection ----------------

def relevance(item: dict, interests: list[dict]) -> tuple[int, list[str]]:
    text = f"{item['title']} {item['summary']}"
    score, hits = 0, []
    for it in interests:
        if _keyword_hit(text, it.get("keywords", [])):
            score += max(1, 7 - int(it.get("priority", 6))) * 4
            hits.append(it["id"])
    return score, hits


def candidate_id(url: str) -> str:
    return "c_" + hashlib.sha1(url.encode()).hexdigest()[:10]


def history_urls() -> set[str]:
    hist = read_json(DATA_DIR / "history.json", default=[])
    return {net.normalize_url(h["url"]) for h in hist if h.get("url")}


def select(items: list[dict], cfg: dict, interests: list[dict], known: set[str], t_now: dt.datetime) -> list[dict]:
    window = dt.timedelta(hours=int(cfg.get("window_hours", 48)))
    backfill = dt.timedelta(days=int(cfg.get("backfill_days", 7)))
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    fresh, older = [], []
    for it in items:
        pub = it["published"]
        if pub is None or pub > t_now + dt.timedelta(hours=1) or pub < t_now - backfill:
            continue  # no verifiable date, from the future, or too old
        key = net.normalize_url(it["url"])
        title_key = re.sub(r"\W+", "", it["title"].lower())
        if key in known or key in seen_urls or (title_key and title_key in seen_titles):
            continue
        seen_urls.add(key)
        seen_titles.add(title_key)
        rel, hits = relevance(it, interests)
        age_h = (t_now - pub).total_seconds() / 3600
        it = {**it, "id": candidate_id(key), "url": it["url"], "interests": hits,
              "prescore": TRUST_WEIGHT.get(it["trust"], 5) + rel + max(0, 10 - int(age_h / 12)),
              "is_backfill": pub < t_now - window}
        (older if it["is_backfill"] else fresh).append(it)
    fresh.sort(key=lambda x: -x["prescore"])
    older.sort(key=lambda x: -x["prescore"])
    picked = fresh
    if len(fresh) < int(cfg.get("min_fresh_candidates", 8)):
        picked = fresh + older[: int(cfg.get("min_fresh_candidates", 8)) * 2]
    return picked[: int(cfg.get("max_candidates", 60))]


def run(t_now: dt.datetime) -> dict:
    cfg = settings().get("collect", {})
    sources = [s for s in load_yaml("sources.yaml").get("sources", []) if s.get("enabled", True)]
    interests = load_yaml("topics.yaml").get("interests", [])
    known = history_urls()
    since = t_now - dt.timedelta(days=int(cfg.get("backfill_days", 7)))
    items, report = [], []
    for src in sources:
        t0 = time.time()
        try:
            kind = src["type"]
            if kind == "rss":
                got = collect_rss(src)
            elif kind == "html_links":
                got = collect_html_links(src, known)
            elif kind == "hn_algolia":
                got = collect_hn(src, since)
            elif kind == "hf_daily_papers":
                got = collect_hf_papers(src)
            else:
                raise ValueError(f"unknown type {kind}")
            kws = src.get("keywords")
            if kws:
                got = [g for g in got if _keyword_hit(f"{g['title']} {g['summary']}", kws)]
            got.sort(key=lambda g: g["published"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
            got = got[: int(src.get("per_source_limit", cfg.get("per_source_limit", 10)))]
            items.extend(got)
            report.append({"source": src["id"], "ok": True, "items": len(got), "sec": round(time.time() - t0, 1)})
        except Exception as e:  # a broken source is reported, never fatal
            report.append({"source": src["id"], "ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"})
    picked = select(items, cfg, interests, known, t_now)
    for c in picked:
        c["published"] = c["published"].isoformat()
        c["updated"] = c["updated"].isoformat() if c["updated"] else None
    return {"collected_at": t_now.isoformat(), "date": t_now.date().isoformat(),
            "window_hours": cfg.get("window_hours", 48), "candidates": picked, "sources": report}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(WORK_DIR / "candidates.json"))
    args = ap.parse_args(argv)
    result = run(now())
    write_json(Path(args.out), result)
    ok = sum(1 for s in result["sources"] if s["ok"])
    fresh = sum(1 for c in result["candidates"] if not c["is_backfill"])
    print(f"sources ok {ok}/{len(result['sources'])}; candidates {len(result['candidates'])} (fresh {fresh})")
    for s in result["sources"]:
        if not s["ok"]:
            print(f"  ! {s['source']}: {s['error']}")
    if not result["candidates"]:
        raise RadioError("no candidates collected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
