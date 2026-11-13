"""Step 12 (optional): send the "show is ready" mail through Gmail, with a clear subject.

Runs only when GMAIL_ADDRESS and GMAIL_APP_PASSWORD are set (GitHub Secrets). The mail goes from
your own address to NOTIFY_TO (default: the same address), so it lands in your inbox, not under a filter
for GitHub notifications. The app password is read from the environment and never printed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import smtplib
import sys
from email.message import EmailMessage

from .config import EPISODES_DIR, RadioError, read_json
from .guide import CORNER_NAMES
from .site import site_url

WEEK = "月火水木金土日"


def subject(date: str, title: str) -> str:
    d = dt.date.fromisoformat(date)
    return f"【AIラジオ】{d.month}/{d.day}({WEEK[d.weekday()]}) {title}"


def body(date: str) -> str:
    base = site_url()
    ep = read_json(EPISODES_DIR / f"{date}-ja.json")
    lines = [ep["title"], f"（約{round(ep['seconds'] / 60)}分）", "", f"▶ 放送を聴く\n{base}#{date}/ja", "",
             f"📘 実践ガイド\n{base}guides/{date}.html", "", "■ 今日の内容"]
    for n in ep["news"]:
        if n.get("corner") == "experiment":
            lines.append(f"🧪 今日の実験：{n.get('name') or n['label']}\n   {base}{n['guide']}")
        else:
            idea = f"\n   💡 {n['idea']}" if n.get("idea") else ""
            lines.append(f"・{CORNER_NAMES.get(n.get('corner'), '')}｜{n['label']}{idea}\n   {n['url']}")
    return "\n".join(lines) + "\n\n— AI Discovery & Build Radio（自動送信）\n"


def send(date: str) -> None:
    sender, password = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        raise RadioError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD are not set")
    ep = read_json(EPISODES_DIR / f"{date}-ja.json")
    msg = EmailMessage()
    msg["Subject"] = subject(date, ep["title"])
    msg["From"] = f"AI Discovery & Build Radio <{sender}>"
    msg["To"] = os.environ.get("NOTIFY_TO") or sender
    msg.set_content(body(date))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(sender, password)
        s.send_message(msg)
    print(f"mail sent: {msg['Subject']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("date")
    ap.add_argument("--dry-run", action="store_true", help="print the subject and body only")
    args = ap.parse_args(argv)
    if args.dry_run:
        ep = read_json(EPISODES_DIR / f"{args.date}-ja.json")
        print(subject(args.date, ep["title"]))
        print(body(args.date))
        return 0
    try:
        send(args.date)
    except (smtplib.SMTPException, OSError) as e:
        raise RadioError(f"mail not sent: {type(e).__name__}") from None
    return 0


if __name__ == "__main__":
    sys.exit(main())
