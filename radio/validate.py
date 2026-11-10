"""Step 3: check Claude's draft (work/draft.json) before anything is voiced or published.

--schema-only : structure and rules only (no network). Used inside the Claude job to ask for a fix.
default       : also checks that every URL opens, then writes work/validated.json.

Fatal problems raise RadioError (exit 1) so an incomplete show is never published.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

from . import net
from .config import WORK_DIR, RadioError, load_yaml, read_json, settings, write_json

LINE_KEYS = ("say", "show")
TASK_KEYS = ("name", "goal", "tools", "prep", "minutes", "steps", "deliverable", "success_check", "cost", "refs")
NEWS_KEYS = ("candidate_id", "corner", "label", "headline", "url", "points", "details", "summary", "whats_new",
             "why_important", "difference", "technical_points", "terms", "feasibility", "reliability",
             "applications", "quick_try", "build_idea", "lines", "scores")
CORNERS = ("news", "practice", "creative")
BAD_STATUS = {0, 404, 410}
URL_RE = re.compile(r"^https?://[^\s<>\"]+$")


class Problems:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _text(p: Problems, where: str, v, max_len: int = 2000) -> None:
    if not isinstance(v, str) or not v.strip():
        p.err(f"{where}: empty or not a string")
    elif len(v) > max_len:
        p.err(f"{where}: too long ({len(v)} > {max_len})")


def _lines(p: Problems, where: str, lines) -> None:
    if not isinstance(lines, list) or not lines:
        p.err(f"{where}: must be a non-empty list of {{say, show}}")
        return
    for i, ln in enumerate(lines):
        if not isinstance(ln, dict):
            p.err(f"{where}[{i}]: not an object")
            continue
        for k in LINE_KEYS:
            _text(p, f"{where}[{i}].{k}", ln.get(k), 300)
        if ln.get("speaker") not in (None, "main", "sub"):
            p.err(f"{where}[{i}].speaker must be main or sub")
        if isinstance(ln.get("say"), str) and re.search(r"https?://", ln["say"]):
            p.err(f"{where}[{i}].say must not contain a URL")


def _str_list(p: Problems, where: str, v, min_n: int = 1, max_n: int = 12) -> None:
    if not isinstance(v, list) or not (min_n <= len(v) <= max_n) or not all(isinstance(x, str) and x.strip() for x in v):
        p.err(f"{where}: needs {min_n}-{max_n} non-empty strings")


def _task(p: Problems, where: str, t, *, deep: bool = False) -> None:
    if not isinstance(t, dict):
        p.err(f"{where}: missing")
        return
    for k in TASK_KEYS:
        if k not in t:
            p.err(f"{where}.{k}: missing")
    for k in ("name", "goal", "deliverable", "success_check", "cost"):
        if k in t:
            _text(p, f"{where}.{k}", t[k], 600)
    _str_list(p, f"{where}.tools", t.get("tools"), 1, 8)
    _str_list(p, f"{where}.prep", t.get("prep"), 0 if not deep else 1, 8)
    _str_list(p, f"{where}.steps", t.get("steps"), 3, 7 if deep else 5)
    _str_list(p, f"{where}.refs", t.get("refs"), 1, 6)
    if not isinstance(t.get("minutes"), (int, float)) or not 1 <= t["minutes"] <= 600:
        p.err(f"{where}.minutes: must be a number of minutes")
    snip = t.get("snippet")
    if snip is not None:
        if not isinstance(snip, dict) or snip.get("type") not in ("prompt", "command", "code", "config"):
            p.err(f"{where}.snippet: needs type prompt|command|code|config and text")
        else:
            _text(p, f"{where}.snippet.text", snip.get("text"), 4000)
            # commands must come from documentation we can point at; never invented
            if snip["type"] in ("command", "code", "config") and not snip.get("source_url"):
                p.err(f"{where}.snippet.source_url: required for {snip['type']} (where the command is documented)")
    elif deep:
        p.err(f"{where}.snippet: the experiment needs a copy-paste prompt or command")
    if "cost" in t and isinstance(t["cost"], str) and ("課金" in t["cost"] or "有料" in t["cost"]) and not t.get("free_alternative"):
        p.warn(f"{where}: paid task without free_alternative")


def check_schema(draft: dict, candidates: dict, cfg: dict, topics: dict) -> Problems:
    p = Problems()
    prog = cfg.get("program", {})
    by_id = {c["id"]: c for c in candidates.get("candidates", [])}
    for k in ("date", "title", "overview", "opening", "news", "experiment", "closing", "evaluated"):
        if k not in draft:
            p.err(f"{k}: missing")
    if p.errors:
        return p
    if not isinstance(draft["date"], str) or not re.fullmatch(r"\d{4}-\d\d-\d\d", draft["date"]):
        p.err("date must be YYYY-MM-DD")
    elif draft["date"] != candidates.get("date"):
        p.err(f"date {draft['date']} does not match candidates date {candidates.get('date')}")
    _text(p, "title", draft["title"], 60)
    _text(p, "overview", draft["overview"], 400)
    _lines(p, "opening", draft["opening"])
    _lines(p, "closing", draft["closing"])

    # scoring of everything considered
    maxes = {k: v["max"] for k, v in topics.get("scoring", {}).items()}
    if not isinstance(draft["evaluated"], list) or not draft["evaluated"]:
        p.err("evaluated: list every candidate you scored")
    else:
        for i, ev in enumerate(draft["evaluated"]):
            if ev.get("candidate_id") not in by_id:
                p.err(f"evaluated[{i}].candidate_id unknown: {ev.get('candidate_id')}")

    news = draft["news"]
    if not isinstance(news, list):
        p.err("news: must be a list")
        return p
    if not 1 <= len(news) <= int(prog.get("max_news", 6)):
        p.err(f"news: {len(news)} items (allowed 1-{prog.get('max_news', 6)})")
    if len(news) < int(prog.get("min_news", 3)):
        p.warn(f"news: only {len(news)} items (short episode)")
    publishers: dict[str, int] = {}
    order = []
    for i, n in enumerate(news):
        w = f"news[{i}]"
        if not isinstance(n, dict):
            p.err(f"{w}: not an object")
            continue
        for k in NEWS_KEYS:
            if k not in n:
                p.err(f"{w}.{k}: missing")
        cand = by_id.get(n.get("candidate_id"))
        if cand is None:
            p.err(f"{w}.candidate_id must be one of the collected candidates")
        elif net.normalize_url(n.get("url", "")) != net.normalize_url(cand["url"]):
            p.err(f"{w}.url must be the candidate's own URL ({cand['url']})")
        else:
            publishers[cand["publisher"]] = publishers.get(cand["publisher"], 0) + 1
        if n.get("corner") not in CORNERS:
            p.err(f"{w}.corner must be one of {CORNERS}")
        else:
            order.append(CORNERS.index(n["corner"]))
        _text(p, f"{w}.label", n.get("label"), 24)
        _text(p, f"{w}.headline", n.get("headline"), 120)
        for k in ("summary", "whats_new", "why_important", "difference", "terms", "feasibility", "reliability"):
            _text(p, f"{w}.{k}", n.get(k), 1200)
        _str_list(p, f"{w}.points", n.get("points"), 2, 4)
        if isinstance(n.get("points"), list) and isinstance(n.get("details"), list) and len(n["points"]) != len(n["details"]):
            p.err(f"{w}.details must have the same length as points")
        _str_list(p, f"{w}.technical_points", n.get("technical_points"), 1, 6)
        _str_list(p, f"{w}.applications", n.get("applications"), 1, 6)
        _lines(p, f"{w}.lines", n.get("lines"))
        _task(p, f"{w}.quick_try", n.get("quick_try"))
        bi = n.get("build_idea")
        if not isinstance(bi, dict) or not all(k in bi for k in ("title", "description", "time", "steps")):
            p.err(f"{w}.build_idea needs title, description, time, steps")
        sc = n.get("scores")
        if not isinstance(sc, dict):
            p.err(f"{w}.scores missing")
        else:
            for k, mx in maxes.items():
                v = sc.get(k)
                if not isinstance(v, (int, float)) or not 0 <= v <= mx:
                    p.err(f"{w}.scores.{k} must be 0-{mx}")
    if order != sorted(order):
        p.err("news must be ordered by corner: news, practice, creative")
    cap = int(prog.get("max_per_publisher", 2))
    for pub, cnt in publishers.items():
        if cnt > cap:
            p.warn(f"{cnt} items from {pub} (max_per_publisher {cap})")

    ex = draft["experiment"]
    _task(p, "experiment", ex, deep=True)
    if isinstance(ex, dict):
        if not isinstance(ex.get("news_index"), int) or not 0 <= ex["news_index"] < len(news):
            p.err("experiment.news_index must point at a news item")
        _lines(p, "experiment.lines", ex.get("lines"))
        _str_list(p, "experiment.points", ex.get("points"), 2, 4)

    say = "".join(ln.get("say", "") for ln in all_lines(draft) if isinstance(ln, dict))
    lo, hi = int(prog.get("say_chars_min", 1200)), int(prog.get("say_chars_max", 4200))
    if len(say) > hi:
        p.err(f"spoken text is {len(say)} chars (max {hi})")
    elif len(say) < lo and len(news) >= int(prog.get("min_news", 3)):
        p.warn(f"spoken text is short: {len(say)} chars")
    return p


def all_lines(draft: dict) -> list[dict]:
    out = list(draft.get("opening") or [])
    for n in draft.get("news") or []:
        if isinstance(n, dict):
            out += n.get("lines") or []
    ex = draft.get("experiment")
    if isinstance(ex, dict):
        out += ex.get("lines") or []
    return out + list(draft.get("closing") or [])


def _refs_of(draft: dict):
    """Every (where, url) the listener may open, apart from the news sources."""
    for i, n in enumerate(draft["news"]):
        for key in ("quick_try",):
            t = n.get(key) or {}
            for j, u in enumerate(t.get("refs") or []):
                yield f"news[{i}].{key}.refs[{j}]", t, "refs", u
            if (t.get("snippet") or {}).get("source_url"):
                yield f"news[{i}].{key}.snippet.source_url", t["snippet"], "source_url", t["snippet"]["source_url"]
        for j, u in enumerate((n.get("build_idea") or {}).get("refs") or []):
            yield f"news[{i}].build_idea.refs[{j}]", n["build_idea"], "refs", u
    ex = draft["experiment"]
    for j, u in enumerate(ex.get("refs") or []):
        yield f"experiment.refs[{j}]", ex, "refs", u
    if (ex.get("snippet") or {}).get("source_url"):
        yield "experiment.snippet.source_url", ex["snippet"], "source_url", ex["snippet"]["source_url"]


def check_links(draft: dict, candidates: dict, p: Problems) -> dict:
    """Open every URL. News sources that are gone stop the run; dead references are removed."""
    statuses: dict[str, int] = {}

    def status(url: str) -> int:
        if url not in statuses:
            statuses[url] = net.check_url(url) if URL_RE.match(url or "") else 0
        return statuses[url]

    for i, n in enumerate(draft["news"]):
        s = status(n["url"])
        n["url_status"] = s
        if s in BAD_STATUS or s >= 500:
            p.err(f"news[{i}].url does not open ({s}): {n['url']}")
        elif s >= 400:
            # feeds gave us this URL, but the site refuses bots (403/401/429): keep it, say so
            p.warn(f"news[{i}].url answered {s} to the bot: {n['url']}")
    for where, holder, key, url in list(_refs_of(draft)):
        s = status(url)
        if s in BAD_STATUS or s >= 500:
            p.warn(f"{where} removed: does not open ({s}) {url}")
            if key == "refs":
                holder["refs"] = [u for u in holder["refs"] if u != url]
            else:
                holder.pop("source_url", None)
                if holder.get("type") in ("command", "code", "config"):
                    # a command we cannot point at the documentation for is not shown
                    holder["type"], holder["text"] = "removed", ""
    if not draft["experiment"].get("refs"):
        p.err("experiment has no reference that opens: it cannot be published as a verified how-to")
    snip = draft["experiment"].get("snippet") or {}
    if snip.get("type") == "removed":
        p.err("experiment command lost its documentation link")
    return statuses


def check_dates(draft: dict, candidates: dict, p: Problems) -> None:
    by_id = {c["id"]: c for c in candidates["candidates"]}
    collected = dt.datetime.fromisoformat(candidates["collected_at"])
    backfill = dt.timedelta(days=int(settings().get("collect", {}).get("backfill_days", 7)))
    for i, n in enumerate(draft["news"]):
        c = by_id[n["candidate_id"]]
        pub = dt.datetime.fromisoformat(c["published"])
        if pub > collected + dt.timedelta(hours=1) or pub < collected - backfill:
            p.err(f"news[{i}] publish date {c['published']} is outside the allowed range")
        n["published"], n["updated"], n["is_backfill"] = c["published"], c.get("updated"), c["is_backfill"]
        n["publisher"], n["source_name"], n["category"] = c["publisher"], c["source_name"], c["category"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--draft", default=str(WORK_DIR / "draft.json"))
    ap.add_argument("--candidates", default=str(WORK_DIR / "candidates.json"))
    ap.add_argument("--out", default=str(WORK_DIR / "validated.json"))
    ap.add_argument("--report", default=str(WORK_DIR / "validation.txt"))
    ap.add_argument("--schema-only", action="store_true")
    ap.add_argument("--expect-date", help="the date the workflow is making (both files must agree with it)")
    args = ap.parse_args(argv)
    candidates = read_json(Path(args.candidates))
    if args.expect_date and candidates.get("date") != args.expect_date:
        print(f"candidates are for {candidates.get('date')}, expected {args.expect_date}")
        return 1
    try:
        draft = read_json(Path(args.draft))
    except (ValueError, RadioError) as e:
        Path(args.report).write_text(f"ERROR draft.json is not valid JSON: {e}\n", encoding="utf-8")
        print(f"draft.json unreadable: {e}")
        return 1
    p = check_schema(draft, candidates, settings(), load_yaml("topics.yaml"))
    if not p.errors and not args.schema_only:
        check_dates(draft, candidates, p)
        check_links(draft, candidates, p)
    report = "\n".join([f"ERROR {e}" for e in p.errors] + [f"WARN  {w}" for w in p.warnings])
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(report + "\n", encoding="utf-8")
    print(report or "draft OK")
    if p.errors:
        return 1
    if not args.schema_only:
        draft["validation"] = {"warnings": p.warnings}
        write_json(Path(args.out), draft)
    return 0


if __name__ == "__main__":
    sys.exit(main())
