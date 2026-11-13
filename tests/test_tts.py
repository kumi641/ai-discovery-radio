import shutil

import pytest

from radio import tts
from radio.config import RadioError, read_json, write_json

CFG = {"lead_sec": 0.5, "gap_line_sec": 0.25, "gap_part_sec": 1.0, "tail_sec": 0.5}


def frames(sec):
    return b"\x00\x00" * int(tts.RATE * sec)


def test_assemble_times_lines_and_contiguous_segments():
    parts = [[frames(1.0)], [frames(2.0), frames(1.0)], [frames(1.0)]]
    text = [[{"show": "o"}], [{"show": "n1"}, {"show": "n2"}], [{"show": "c"}]]
    _, timed, segs, total = tts.assemble(parts, text, CFG)
    assert [(t["start"], t["end"], t["part"]) for t in timed] == [
        (0.5, 1.5, 0), (2.5, 4.5, 1), (4.75, 5.75, 1), (6.75, 7.75, 2)]
    assert [s["kind"] for s in segs] == ["opening", "news", "closing"] and segs[1]["index"] == 0
    assert segs[0]["end"] == segs[1]["start"] and segs[-1]["end"] == total == 8.25


def test_quota_blocks_before_crossing_limit():
    cfg = {"monthly_char_limit": 1000, "per_episode_char_limit": 500}
    tts.check_quota(400, cfg, {"2026-11": {"chars": 500, "requests": 3}}, "2026-11")
    with pytest.raises(RadioError):
        tts.check_quota(400, cfg, {"2026-11": {"chars": 700, "requests": 3}}, "2026-11")
    with pytest.raises(RadioError):
        tts.check_quota(600, cfg, {}, "2026-11")


def test_add_usage_is_per_month_and_does_not_mutate():
    ledger = {"2026-10": {"chars": 5, "requests": 1}}
    new = tts.add_usage(ledger, "2026-11", 10)
    assert new["2026-11"] == {"chars": 10, "requests": 1} and "2026-11" not in ledger


def test_billable_chars_counts_japanese_double():
    assert tts.billable_chars("AIです") == 2 + 2 * 2


def test_ssml_escapes_text():
    s = tts.ssml("A & B <tag>", "ja-JP-NanamiNeural", "+0%")
    assert "A &amp; B &lt;tag&gt;" in s and "ja-JP-NanamiNeural" in s


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_fake_voice_episode_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(tts, "LEDGER", tmp_path / "usage.json")
    ep_path = tmp_path / "2026-11-10-ja.json"
    line = {"say": "テストです。", "show": "テストです。"}
    write_json(ep_path, {"opening": [line], "news": [{"lines": [line, line]}], "closing": [line]})
    info = tts.voice_episode(ep_path, "fake")
    ep = read_json(ep_path)
    assert (tmp_path / "audio" / "2026-11-10-ja.mp3").stat().st_size > 1000
    assert len(ep["lines_timed"]) == 4 and ep["seconds"] == info["seconds"] > 3
    assert not (tmp_path / "usage.json").exists()  # the fake voice never touches the Azure ledger
