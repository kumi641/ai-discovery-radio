from radio import validate


def errors(draft, candidates, cfg, topics):
    return validate.check_schema(draft, candidates, cfg, topics).errors


def test_valid_draft_passes(draft, candidates, cfg, topics):
    assert errors(draft, candidates, cfg, topics) == []


def test_news_url_must_be_the_candidates_own_url(draft, candidates, cfg, topics):
    draft["news"][0]["url"] = "https://made-up.example.org/story"
    assert any("candidate's own URL" in e for e in errors(draft, candidates, cfg, topics))


def test_unknown_candidate_is_rejected(draft, candidates, cfg, topics):
    draft["news"][0]["candidate_id"] = "c_doesnotexist"
    assert any("collected candidates" in e for e in errors(draft, candidates, cfg, topics))


def test_command_without_documentation_is_rejected(draft, candidates, cfg, topics):
    draft["experiment"]["snippet"].pop("source_url")
    assert any("source_url" in e for e in errors(draft, candidates, cfg, topics))


def test_experiment_needs_snippet_and_valid_news_index(draft, candidates, cfg, topics):
    draft["experiment"].pop("snippet")
    draft["experiment"]["news_index"] = 9
    errs = errors(draft, candidates, cfg, topics)
    assert any("experiment.snippet" in e for e in errs) and any("news_index" in e for e in errs)


def test_corner_order_and_score_range(draft, candidates, cfg, topics):
    draft["news"][0]["corner"], draft["news"][2]["corner"] = "creative", "news"
    draft["news"][1]["scores"]["practice"] = 99
    errs = errors(draft, candidates, cfg, topics)
    assert any("ordered by corner" in e for e in errs) and any("scores.practice" in e for e in errs)


def test_url_in_spoken_text_and_too_long_episode(draft, candidates, cfg, topics):
    draft["opening"][0]["say"] = "詳しくは https://example.com で"
    cfg["program"]["say_chars_max"] = 20
    errs = errors(draft, candidates, cfg, topics)
    assert any("must not contain a URL" in e for e in errs) and any("spoken text" in e for e in errs)


def test_missing_top_level_keys(candidates, cfg, topics):
    assert errors({"date": "2026-11-10"}, candidates, cfg, topics)


def test_links_dead_news_url_is_fatal_dead_ref_is_removed(draft, candidates, monkeypatch):
    status = {"https://example.com/news/1": 404, "https://example.com/docs/skills": 404}
    monkeypatch.setattr(validate.net, "check_url", lambda u: status.get(u, 200))
    p = validate.Problems()
    validate.check_links(draft, candidates, p)
    assert any("news[1].url does not open" in e for e in p.errors)
    # the experiment's only ref was dead too: removed, and that is fatal
    assert draft["experiment"]["refs"] == [] and any("experiment has no reference" in e for e in p.errors)


def test_links_bot_blocked_news_url_is_a_warning(draft, candidates, monkeypatch):
    monkeypatch.setattr(validate.net, "check_url", lambda u: 403 if u.endswith("/news/0") else 200)
    p = validate.Problems()
    validate.check_links(draft, candidates, p)
    assert p.errors == [] and any("403" in w for w in p.warnings)


def test_command_with_dead_doc_link_is_hidden(draft, candidates, monkeypatch):
    draft["news"][0]["quick_try"]["snippet"] = {"type": "command", "text": "rm -rf /", "source_url": "https://dead.example/x"}
    monkeypatch.setattr(validate.net, "check_url", lambda u: 0 if "dead" in u else 200)
    p = validate.Problems()
    validate.check_links(draft, candidates, p)
    snip = draft["news"][0]["quick_try"]["snippet"]
    assert snip["type"] == "removed" and snip["text"] == ""


def test_dates_outside_range_are_fatal(draft, candidates, monkeypatch):
    monkeypatch.setattr(validate, "settings", lambda: {"collect": {"backfill_days": 7}})
    candidates["candidates"][0]["published"] = "2026-10-01T00:00:00+00:00"
    p = validate.Problems()
    validate.check_dates(draft, candidates, p)
    assert any("outside the allowed range" in e for e in p.errors)
    assert draft["news"][1]["publisher"] == "Anthropic"


def test_use_idea_is_optional_but_not_empty(draft, candidates, cfg, topics):
    draft["news"][0]["use_idea"] = None          # news a listener cannot try: no idea is fine
    draft["news"][1].pop("use_idea")
    assert errors(draft, candidates, cfg, topics) == []
    draft["news"][2]["use_idea"] = "  "           # but an idea that is there must say something
    assert any("use_idea" in e for e in errors(draft, candidates, cfg, topics))
