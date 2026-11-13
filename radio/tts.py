"""Step 5: voice an episode with Azure AI Speech (F0) and time every line.

Each line is synthesised on its own (as the original station does), so its start and end are exact:
the WAVs are joined in Python with fixed pauses, then FFmpeg makes one loudness-normalised MP3.

Safety: a monthly character ledger (data/tts_usage.json) stops the run before the station's own
limit (settings.tts.monthly_char_limit) is crossed. Nothing here ever upgrades the Azure plan.
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import time
import wave
from pathlib import Path
from xml.sax.saxutils import escape

import requests

from .config import AUDIO_DIR, DATA_DIR, EPISODES_DIR, RadioError, now, read_json, settings, write_json

LEDGER = DATA_DIR / "tts_usage.json"
RATE = 24000


# ---------------- quota ledger ----------------

def billable_chars(text: str) -> int:
    """Counted on the safe side: a non-ASCII (Japanese) character counts as 2, as Azure may bill CJK."""
    return sum(1 if ord(ch) < 128 else 2 for ch in text)


def month_key() -> str:
    return now().strftime("%Y-%m")


def ledger_used(ledger: dict, month: str) -> int:
    return int(ledger.get(month, {}).get("chars", 0))


def check_quota(needed: int, cfg: dict, ledger: dict, month: str) -> None:
    per_ep = int(cfg.get("per_episode_char_limit", 6000))
    limit = int(cfg.get("monthly_char_limit", 300000))
    if needed > per_ep:
        raise RadioError(f"episode needs {needed} chars > per_episode_char_limit {per_ep}")
    used = ledger_used(ledger, month)
    if used + needed > limit:
        raise RadioError(f"TTS monthly limit: used {used} + {needed} > {limit} chars ({month}). Stopped before synthesis.")


def add_usage(ledger: dict, month: str, chars: int, requests_n: int = 1) -> dict:
    cur = ledger.get(month, {"chars": 0, "requests": 0})
    return {**ledger, month: {"chars": cur["chars"] + chars, "requests": cur["requests"] + requests_n}}


# ---------------- synthesis ----------------

def ssml(text: str, voice: str, rate: str) -> str:
    return (f"<speak version='1.0' xml:lang='ja-JP'><voice name='{escape(voice)}'>"
            f"<prosody rate='{escape(rate)}'>{escape(text)}</prosody></voice></speak>")


def azure_synth(text: str, voice: str, cfg: dict) -> bytes:
    key, region = os.environ.get("AZURE_SPEECH_KEY"), os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        raise RadioError("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION are not set")
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
               "X-Microsoft-OutputFormat": cfg.get("output_format", "riff-24khz-16bit-mono-pcm"),
               "User-Agent": "ai-discovery-radio"}
    body = ssml(text, voice, cfg.get("rate", "+0%")).encode("utf-8")
    for attempt in range(int(cfg.get("max_retries", 3)) + 1):
        try:
            r = requests.post(url, headers=headers, data=body, timeout=int(cfg.get("request_timeout_sec", 60)))
        except requests.RequestException as e:
            if attempt >= int(cfg.get("max_retries", 3)):
                raise RadioError(f"Azure TTS unreachable: {type(e).__name__}") from None
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 200 and r.content:
            return r.content
        if r.status_code in (401, 403):
            raise RadioError(f"Azure TTS refused the key ({r.status_code}); quota exhausted or wrong key/region")
        if r.status_code == 429 or r.status_code >= 500:
            wait = float(r.headers.get("Retry-After", 10 * (attempt + 1)))
            time.sleep(min(wait, 60))
            continue
        raise RadioError(f"Azure TTS error {r.status_code}")
    raise RadioError("Azure TTS: too many retries (rate limit)")


def fake_synth(text: str, voice: str, cfg: dict) -> bytes:
    """Silent audio sized like speech (about 7.5 chars a second). For trying the pipeline without a key."""
    return make_wav(b"\x00\x00" * int(RATE * max(0.5, len(text) / 7.5)))


def make_wav(frames: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)
    return buf.getvalue()


def read_frames(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, RATE):
            raise RadioError("unexpected audio format from TTS (need 24kHz 16-bit mono)")
        return w.readframes(w.getnframes())


# ---------------- assembly ----------------

def parts_of(ep: dict) -> list[list[dict]]:
    return [ep["opening"], *[n["lines"] for n in ep["news"]], ep["closing"]]


def assemble(parts: list[list[bytes]], parts_text: list[list[dict]], cfg: dict) -> tuple[bytes, list[dict], list[dict], float]:
    """Join the line audio with pauses; return frames, lines_timed, segments and length in seconds."""
    silence = lambda sec: b"\x00\x00" * int(RATE * sec)  # noqa: E731
    out = bytearray(silence(float(cfg.get("lead_sec", 0.6))))
    timed, segments = [], []
    n_parts = len(parts)
    for pi, (audio_lines, text_lines) in enumerate(zip(parts, parts_text)):
        if pi > 0:
            out += silence(float(cfg.get("gap_part_sec", 0.9)))
        seg_start = len(out) / 2 / RATE
        for li, (frames, ln) in enumerate(zip(audio_lines, text_lines)):
            if li > 0:
                out += silence(float(cfg.get("gap_line_sec", 0.25)))
            start = len(out) / 2 / RATE
            out += frames
            timed.append({"start": round(start, 3), "end": round(len(out) / 2 / RATE, 3), "show": ln["show"], "part": pi})
        kind = "opening" if pi == 0 else "closing" if pi == n_parts - 1 else "news"
        segments.append({"kind": kind, "index": None if kind != "news" else pi - 1, "start": round(seg_start, 3), "end": None})
    out += silence(float(cfg.get("tail_sec", 0.6)))
    total = round(len(out) / 2 / RATE, 3)
    for i, s in enumerate(segments):  # parts follow each other with no hole, as the player expects
        s["end"] = segments[i + 1]["start"] if i + 1 < len(segments) else total
    return bytes(out), timed, segments, total


def encode_mp3(wav_path: Path, mp3_path: Path, bitrate: str) -> None:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path),
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(RATE), "-ac", "1",
           "-c:a", "libmp3lame", "-b:a", bitrate, str(mp3_path)]
    subprocess.run(cmd, check=True)


def voice_episode(ep_path: Path, provider: str | None = None) -> dict:
    cfg = settings().get("tts", {})
    provider = provider or os.environ.get("TTS_PROVIDER") or cfg.get("provider", "azure")
    synth = {"azure": azure_synth, "fake": fake_synth}[provider]
    ep = read_json(ep_path)
    parts_text = parts_of(ep)
    needed = sum(billable_chars(ln["say"]) for part in parts_text for ln in part)
    month = month_key()
    ledger = read_json(LEDGER, default={})
    if provider == "azure":
        check_quota(needed, cfg, ledger, month)
    voices = cfg.get("voices", {"main": "ja-JP-NanamiNeural"})
    interval = float(cfg.get("min_interval_sec", 3.3)) if provider == "azure" else 0
    parts_audio: list[list[bytes]] = []
    last = 0.0
    for part in parts_text:
        audio_lines = []
        for ln in part:
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.monotonic()
            voice = voices.get(ln.get("speaker", "main"), voices["main"])
            audio_lines.append(read_frames(synth(ln["say"], voice, cfg)))
            if provider == "azure":  # record every request at once, so a later failure cannot hide usage
                ledger = add_usage(ledger, month, billable_chars(ln["say"]))
                write_json(LEDGER, ledger)
        parts_audio.append(audio_lines)
    frames, timed, segments, total = assemble(parts_audio, parts_text, cfg)
    name = ep_path.stem
    wav_path = AUDIO_DIR / f"{name}.wav"
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    wav_path.write_bytes(make_wav(frames))
    encode_mp3(wav_path, AUDIO_DIR / f"{name}.mp3", cfg.get("mp3_bitrate", "64k"))
    wav_path.unlink()
    ep = {**ep, "seconds": total, "lines_timed": timed, "segments": segments, "made_at": now().strftime("%Y-%m-%dT%H:%M:%S"),
          "tts": {"provider": provider, "chars": needed, "voice": voices["main"]}}
    write_json(ep_path, ep)
    return {"chars": needed, "seconds": total, "month_used": ledger_used(ledger, month)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("episode", nargs="?", help="episodes/<date>-ja.json (default: today's)")
    ap.add_argument("--provider", choices=["azure", "fake"])
    args = ap.parse_args(argv)
    from .config import today
    path = Path(args.episode) if args.episode else EPISODES_DIR / f"{today()}-ja.json"
    info = voice_episode(path, args.provider)
    print(f"voiced {path.name}: {info['chars']} chars, {info['seconds']} s; this month {info['month_used']} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
