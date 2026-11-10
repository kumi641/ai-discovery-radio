"""Shared test data. Everything here is fictional sample data for tests, not real news."""
import copy

import pytest

DATE = "2026-11-10"
COLLECTED = "2026-11-10T07:00:00+09:00"


def _line(text: str) -> dict:
    return {"say": text, "show": text}


def _task(n_steps: int = 3, snippet: dict | None = None) -> dict:
    t = {"name": "小さなスキルを作る", "goal": "繰り返す作業を再利用できる形にする", "tools": ["Claude Code"],
         "prep": ["Claude Code をインストール済み"], "minutes": 15,
         "steps": [f"手順{i}" for i in range(1, n_steps + 1)],
         "deliverable": "動くスキルファイル", "success_check": "呼び出すと期待どおりに動く", "cost": "無料枠で可能",
         "refs": ["https://example.com/docs/skills"]}
    if snippet:
        t["snippet"] = snippet
    return t


def _news(i: int, cid: str, url: str, corner: str) -> dict:
    return {
        "candidate_id": cid, "corner": corner, "label": f"見出し{i}", "headline": f"ガイド見出し{i}", "url": url,
        "scores": {"practice": 30, "novelty": 15, "reliability": 22, "relevance": 18},
        "points": ["要点A", "要点B"], "details": ["説明A", None], "summary": "要約。", "whats_new": "新しい点。",
        "why_important": "重要な理由。", "difference": "従来との違い。", "technical_points": ["仕組み"],
        "terms": "無料（公式ページで確認）", "feasibility": "高：すぐ試せる", "reliability": "公式ブログで確認",
        "applications": ["個人開発への応用"], "quick_try": _task(),
        "build_idea": {"title": "発展", "description": "説明", "time": "2時間", "steps": ["a", "b", "c"]},
        "lines": [_line(f"ニュース{i}の一文目です。"), _line(f"ニュース{i}の二文目です。")],
    }


@pytest.fixture
def candidates() -> dict:
    cands = []
    for i, (pub, cat) in enumerate([("OpenAI", "official"), ("Anthropic", "agent-dev"), ("Blender", "creative")]):
        cands.append({"id": f"c_{i:010d}", "title": f"Item {i}", "url": f"https://example.com/news/{i}",
                      "published": "2026-11-09T12:00:00+00:00", "updated": None, "summary": "", "source_id": f"s{i}",
                      "source_name": pub, "publisher": pub, "category": cat, "trust": "primary", "extra": {},
                      "interests": [], "prescore": 40, "is_backfill": False})
    return {"collected_at": COLLECTED, "date": DATE, "window_hours": 48, "candidates": cands, "sources": []}


@pytest.fixture
def draft(candidates) -> dict:
    c = candidates["candidates"]
    exp = _task(4, {"type": "command", "text": "echo hello", "source_url": "https://example.com/docs/cli"})
    exp.update({"news_index": 1, "points": ["作るもの", "始め方"], "lines": [_line("今日の実験です。")]})
    return copy.deepcopy({
        "date": DATE, "title": "テスト放送", "overview": "今日の動き。",
        "evaluated": [{"candidate_id": x["id"], "fetched": True, "selected": True, "reason": "r",
                       "scores": {"practice": 30, "novelty": 15, "reliability": 22, "relevance": 18}} for x in c],
        "opening": [_line("おはようございます。")],
        "news": [_news(1, c[0]["id"], c[0]["url"], "news"), _news(2, c[1]["id"], c[1]["url"], "practice"),
                 _news(3, c[2]["id"], c[2]["url"], "creative")],
        "experiment": exp,
        "closing": [_line("また明日。")],
    })


@pytest.fixture
def cfg() -> dict:
    return {"program": {"min_news": 3, "max_news": 6, "max_per_publisher": 2, "say_chars_min": 10, "say_chars_max": 4200},
            "collect": {"window_hours": 48, "backfill_days": 7, "min_fresh_candidates": 2, "max_candidates": 60}}


@pytest.fixture
def topics() -> dict:
    return {"scoring": {"practice": {"max": 35}, "novelty": {"max": 20}, "reliability": {"max": 25}, "relevance": {"max": 20}},
            "interests": [{"id": "agent-dev", "priority": 1, "keywords": ["agent", "mcp"]},
                          {"id": "music", "priority": 3, "keywords": ["music"]}]}
