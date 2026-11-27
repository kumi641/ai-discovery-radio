from radio import notify


def test_subject_has_date_weekday_and_title():
    assert notify.subject("2026-11-10", "テスト放送") == "【AIラジオ】11/10(火) テスト放送"


def test_body_lists_links_and_experiment(monkeypatch):
    ep = {"title": "T (beta)", "seconds": 453, "news": [
        {"corner": "news", "label": "見出し", "url": "https://example.com/a"},
        {"corner": "experiment", "label": "今日の実験", "name": "小さな実験", "guide": "guides/2026-11-10.html#experiment"}]}
    monkeypatch.setattr(notify, "read_json", lambda path: ep)
    monkeypatch.setattr(notify, "site_url", lambda: "https://example.github.io/radio/")
    text = notify.body("2026-11-10")
    assert "T (beta)" in text and "https://example.github.io/radio/#2026-11-10/ja" in text
    assert "https://example.com/a" in text and "🧪 今日の実験：小さな実験" in text
