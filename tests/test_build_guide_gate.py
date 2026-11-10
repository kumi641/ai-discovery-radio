import datetime as dt

from radio import build, gate, guide

JST = dt.timezone(dt.timedelta(hours=9))


def test_episode_has_player_fields_and_experiment_last(draft):
    cards = {n["url"]: {"url": n["url"], "title": "t", "site": "s", "description": None, "image": None, "icon": None}
             for n in draft["news"]}
    cards["https://example.com/docs/skills"] = {"url": "https://example.com/docs/skills", "title": "doc"}
    ep = build.to_episode(draft, cards)
    assert ep["format"] == "monoradio/news-1" and ep["guide"] == "guides/2026-11-10.html"
    assert len(ep["news"]) == 4 and ep["news"][-1]["corner"] == "experiment" and ep["highlight"] == 3
    assert ep["news"][0]["guide"].endswith("#news-1")
    for n in ep["news"]:
        assert len(n["points"]) == len(n["details"]) and n["lines"] and n["link"]["url"]


def test_guide_escapes_untrusted_text_and_unsafe_links(draft):
    draft["news"][0]["summary"] = "<script>alert(1)</script>"
    draft["news"][0]["whats_new"] = "<img src=x onerror=alert(1)>"
    draft["experiment"]["refs"] = ["javascript:alert(1)"]
    page = guide.html_page(draft, {"seconds": 540})
    assert "<img src=x" not in page and 'href="javascript:' not in page
    assert 'id="experiment"' in page and 'href="../#2026-11-10/ja"' in page


def test_guide_markdown_has_sections(draft):
    md = guide.markdown(draft)
    for heading in ("## 今日の実験", "### 重要ポイント", "### 技術解説", "### 実践アイデア", "### 利用条件・料金", "```bash"):
        assert heading in md


def test_gate_runs_once_inside_window():
    cfg = {"schedule": {"time": "07:00", "retry_hours": 3}}
    at = lambda h, m=5: dt.datetime(2026, 11, 10, h, m, tzinfo=JST)  # noqa: E731
    assert gate.decide(at(6), cfg, False, "schedule", False)[0] is False
    assert gate.decide(at(7), cfg, False, "schedule", False)[0] is True
    assert gate.decide(at(9), cfg, False, "schedule", False)[0] is True
    assert gate.decide(at(10), cfg, False, "schedule", False)[0] is False
    assert gate.decide(at(7), cfg, True, "schedule", False)[0] is False   # already published
    assert gate.decide(at(15), cfg, False, "workflow_dispatch", False)[0] is True
    assert gate.decide(at(15), cfg, True, "workflow_dispatch", True)[0] is True
