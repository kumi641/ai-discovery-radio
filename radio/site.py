"""Step 10-11: check the published show really opens, and write the GitHub Release notes.

  verify          wait until GitHub Pages serves today's episode (made_at matches), audio and guide
  release-notes   print the Markdown body of the release (the e-mail you receive)
"""
from __future__ import annotations

import argparse
import sys
import time

import requests

from .config import EPISODES_DIR, RadioError, read_json, settings, station
from .guide import CORNER_NAMES


def site_url() -> str:
    url = station().get("url") or ""
    if not url.startswith("https://"):
        raise RadioError("station.json url is not set to the GitHub Pages address")
    return url if url.endswith("/") else url + "/"


def verify(date: str) -> None:
    base = site_url()
    ep = read_json(EPISODES_DIR / f"{date}-ja.json")
    deadline = time.time() + int(settings().get("publish", {}).get("verify_timeout_sec", 600))
    checks = {f"{base}episodes/{date}-ja.json": "json", f"{base}audio/{date}-ja.mp3": "audio",
              f"{base}guides/{date}.html": "html", base: "html"}
    pending = dict(checks)
    while pending and time.time() < deadline:
        for url, kind in list(pending.items()):
            try:
                r = requests.get(url, timeout=30, headers={"Cache-Control": "no-cache"}, params={"t": int(time.time())})
            except requests.RequestException:
                continue
            if r.status_code != 200:
                continue
            if kind == "json" and r.json().get("made_at") != ep.get("made_at"):
                continue  # Pages still serves the previous build
            if kind == "audio" and len(r.content) < 10_000:
                continue
            pending.pop(url)
        if pending:
            time.sleep(20)
    if pending:
        raise RadioError("not served by GitHub Pages in time: " + ", ".join(pending))
    print(f"verified {len(checks)} URLs on {base}")


def release_notes(date: str) -> str:
    base = site_url()
    ep = read_json(EPISODES_DIR / f"{date}-ja.json")
    lines = [f"## ▶ [放送を聴く]({base}#{date}/ja)　｜　📘 [実践ガイド]({base}guides/{date}.html)", "",
             f"**{ep['title']}**（約{round(ep['seconds'] / 60)}分）", ""]
    for n in ep["news"]:
        if n.get("corner") == "experiment":
            lines.append(f"- 🧪 **今日の実験**：{n.get('name') or n['points'][0]} →[手順]({base}{n['guide']})")
        else:
            lines.append(f"- {CORNER_NAMES.get(n.get('corner'), '')}：[{n['label']}]({n['url']})")
    lines += ["", "このメールは GitHub Releases の通知です。"]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("step", choices=["verify", "release-notes", "title"])
    ap.add_argument("date")
    args = ap.parse_args(argv)
    if args.step == "verify":
        verify(args.date)
    elif args.step == "title":
        print(read_json(EPISODES_DIR / f"{args.date}-ja.json")["title"])
    else:
        print(release_notes(args.date))
    return 0


if __name__ == "__main__":
    sys.exit(main())
