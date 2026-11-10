"""Step 4 and 7: turn the validated draft into the player's episode and the practice guide.

  build     work/validated.json -> episodes/<date>-ja.json (no timings yet) + link cards (OGP)
  finalize  after TTS: guides/<date>.md/.html, guides/index.html, episodes.json, data/history.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

from . import guide, htmlmeta, net
from .config import DATA_DIR, EPISODES_DIR, GUIDES_DIR, ROOT, WORK_DIR, RadioError, read_json, write_json

LANG = "ja"


def link_card(url: str, fallback_title: str) -> dict:
    """The site's own share image (OGP) by URL. Nothing is downloaded into the repository."""
    card = {"url": url, "title": fallback_title, "site": urlsplit(url).netloc, "description": None, "image": None, "icon": None}
    try:
        r = net.get(url, check_robots=True)
    except Exception:
        return card
    if r.status_code >= 400:
        return {**card, "status": r.status_code}
    meta = htmlmeta.parse(r.text, url)
    return {**card, "title": meta["title"] or fallback_title, "site": meta["site"] or card["site"],
            "description": meta["description"], "image": meta["image"], "icon": meta["icon"]}


def to_episode(d: dict, cards: dict[str, dict]) -> dict:
    news = []
    for i, n in enumerate(d["news"]):
        news.append({"label": n["label"], "points": n["points"], "details": n["details"], "url": n["url"],
                     "lines": n["lines"], "link": cards.get(n["url"]) or link_card(n["url"], n["headline"]),
                     "corner": n["corner"], "guide": f"guides/{d['date']}.html#news-{i + 1}"})
    ex = d["experiment"]
    ref = ex["refs"][0]
    news.append({"label": "今日の実験", "points": ex["points"], "details": [None] * len(ex["points"]), "url": ref,
                 "lines": ex["lines"], "link": cards.get(ref) or link_card(ref, ex["name"]),
                 "corner": "experiment", "name": ex["name"], "guide":f"guides/{d['date']}.html#experiment"})
    return {"format": "monoradio/news-1", "lang": LANG, "date": d["date"], "title": d["title"],
            "opening": d["opening"], "news": news, "closing": d["closing"],
            "highlight": len(news) - 1, "guide": f"guides/{d['date']}.html"}


def build(validated: Path) -> Path:
    d = read_json(validated)
    cards = {}
    for n in d["news"]:
        cards[n["url"]] = link_card(n["url"], n["headline"])
    ep = to_episode(d, cards)
    path = EPISODES_DIR / f"{d['date']}-{LANG}.json"
    write_json(path, ep)
    return path


def update_episodes_index(ep: dict) -> list:
    path = ROOT / "episodes.json"
    eps = [e for e in read_json(path, default=[]) if e.get("date") != ep["date"]]
    eps.append({"date": ep["date"], LANG: {"title": ep["title"], "seconds": ep["seconds"]}})
    eps.sort(key=lambda e: e["date"], reverse=True)
    write_json(path, eps, compact=True)
    return eps


def update_history(d: dict) -> None:
    path = DATA_DIR / "history.json"
    hist = [h for h in read_json(path, default=[]) if h.get("date") != d["date"]]
    for i, n in enumerate(d["news"]):
        hist.append({"date": d["date"], "url": n["url"], "title": n["headline"], "publisher": n.get("publisher"),
                     "corner": n["corner"], "experiment": d["experiment"]["name"] if d["experiment"]["news_index"] == i else None})
    write_json(path, hist)


def finalize(validated: Path) -> None:
    d = read_json(validated)
    ep_path = EPISODES_DIR / f"{d['date']}-{LANG}.json"
    ep = read_json(ep_path)
    if not ep.get("lines_timed") or not ep.get("seconds"):
        raise RadioError("episode has no timings: run TTS first")
    eps = update_episodes_index(ep)
    GUIDES_DIR.mkdir(parents=True, exist_ok=True)
    (GUIDES_DIR / f"{d['date']}.md").write_text(guide.markdown(d), encoding="utf-8")
    (GUIDES_DIR / f"{d['date']}.html").write_text(guide.html_page(d, ep), encoding="utf-8")
    (GUIDES_DIR / "index.html").write_text(guide.index_page(eps), encoding="utf-8")
    update_history(d)
    cands = read_json(WORK_DIR / "candidates.json", default={})
    write_json(DATA_DIR / "runs" / f"{d['date']}.json", {
        "date": d["date"], "made_at": ep.get("made_at"), "seconds": ep["seconds"], "tts": ep.get("tts"),
        "candidates": len(cands.get("candidates", [])), "sources": cands.get("sources", []),
        "evaluated": d.get("evaluated", []), "warnings": d.get("validation", {}).get("warnings", []),
    })


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("step", choices=["build", "finalize"])
    ap.add_argument("--validated", default=str(WORK_DIR / "validated.json"))
    args = ap.parse_args(argv)
    if args.step == "build":
        print(f"built {build(Path(args.validated))}")
    else:
        finalize(Path(args.validated))
        print("finalized guide, episodes.json, history")
    return 0


if __name__ == "__main__":
    sys.exit(main())
