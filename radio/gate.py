"""Step 0: decide whether this (hourly) run should make today's show.

The workflow wakes every hour; the broadcast time lives in config/settings.yaml, so changing the
time needs no workflow edit. A day that already has its episode is never made twice unless forced.
Writes run/date/model/max_turns/timeout to $GITHUB_OUTPUT.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys

from .config import EPISODES_DIR, now, settings


def decide(t_now: dt.datetime, cfg: dict, exists: bool, event: str, force: bool) -> tuple[bool, str]:
    if exists and not force:
        return False, "today's episode already exists"
    if event != "schedule":
        return True, f"manual run ({event})"
    hh, mm = (int(x) for x in str(cfg.get("schedule", {}).get("time", "07:00")).split(":"))
    start = t_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    end = start + dt.timedelta(hours=int(cfg.get("schedule", {}).get("retry_hours", 3)))
    if start <= t_now < end:
        return True, f"in the broadcast window {start:%H:%M}-{end:%H:%M}"
    return False, f"outside the broadcast window ({start:%H:%M}-{end:%H:%M})"


def released(date: str) -> bool:
    """Today counts as done only when its episode file AND its GitHub Release exist (a half-finished
    run must be retried). Without gh/GH_TOKEN (local use) the episode file alone decides."""
    if not os.environ.get("GH_TOKEN") or not shutil.which("gh"):
        return True
    return subprocess.run(["gh", "release", "view", f"ep-{date}"], capture_output=True).returncode == 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch"))
    ap.add_argument("--force", default="false")
    args = ap.parse_args(argv)
    cfg = settings()
    t = now()
    date = t.date().isoformat()
    done = (EPISODES_DIR / f"{date}-ja.json").exists() and released(date)
    run, why = decide(t, cfg, done, args.event, args.force.lower() == "true")
    if run and os.environ.get("SECRETS_READY") == "false":
        run, why = False, "secrets CLAUDE_CODE_OAUTH_TOKEN / AZURE_SPEECH_KEY / AZURE_SPEECH_REGION are not all set"
    c = cfg.get("claude", {})
    out = {"run": str(run).lower(), "date": date, "model": c.get("model", ""), "max_turns": c.get("max_turns", 80),
           "timeout": c.get("timeout_minutes", 30), "fix_attempts": c.get("fix_attempts", 1)}
    print(f"{date} {t:%H:%M}: run={run} ({why})")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.writelines(f"{k}={v}\n" for k, v in out.items())
    return 0


if __name__ == "__main__":
    sys.exit(main())
