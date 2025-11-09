#!/usr/bin/env python3
"""CASER Mission Control (detailed view)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(env_path, override=False)

HOST = os.getenv("TYPESENSE_HOST", "http://localhost:8108")
ADMIN = os.getenv("TYPESENSE_ADMIN_KEY") or os.getenv("TS_ADMIN_KEY")

SCAN_STATE_PATH = ROOT / "logs" / "scan_state.json"
SCAN_HISTORY_PATH = ROOT / "logs" / "scan-history.ndjson"
USCOURTS_FEEDS = ROOT / "config" / "uscourts-filtered-feed.json"
GOVINFO_FEEDS = ROOT / "config" / "govinfo-filtered-feed.json"

BOLD = "\033[1m"
RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
PACIFIC = ZoneInfo("America/Los_Angeles")


def colour(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return {}


def count_feeds(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return sum(1 for feed in data if (feed.get("url") or "").strip())
    except Exception:
        return 0


def typesense_info() -> Dict[str, Any]:
    info = {"ok": False, "docs": None, "message": "unavailable"}
    try:
        health = requests.get(f"{HOST}/health", timeout=5)
        if not health.ok or not health.json().get("ok"):
            info["message"] = f"HTTP {health.status_code}"
            return info
        headers = {"X-TYPESENSE-API-KEY": ADMIN} if ADMIN else {}
        resp = requests.get(f"{HOST}/collections/rss_entries", headers=headers, timeout=5)
        if resp.ok:
            info["docs"] = resp.json().get("num_documents")
            info["ok"] = True
            info["message"] = "online"
        else:
            info["message"] = f"HTTP {resp.status_code}"
    except Exception as exc:
        info["message"] = str(exc)
    return info


def docker_ok() -> bool:
    try:
        return subprocess.run(["docker", "ps"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def data_size_bytes() -> int:
    data_root = ROOT / "data"
    if not data_root.exists():
        return 0
    total = 0
    for item in data_root.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def human_size(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def human_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {sec}s"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def load_recent_history(limit: int = 5) -> List[Dict[str, Any]]:
    if not SCAN_HISTORY_PATH.exists():
        return []
    try:
        with open(SCAN_HISTORY_PATH, "r", encoding="utf-8") as fp:
            lines = deque(fp, maxlen=limit)
        # Newest first
        return [json.loads(line) for line in reversed(lines) if line.strip()]
    except Exception:
        return []


def parse_iso_to_pacific(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(PACIFIC)


def format_pacific(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    return dt.strftime("%Y-%m-%d %I:%M %p PT")


def format_run_id(run_id: Optional[str]) -> Optional[str]:
    if not run_id or run_id in {"", "n/a"}:
        return None
    try:
        dt = datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.astimezone(PACIFIC).strftime("%Y-%m-%d %I:%M %p PT")


def docs_added_today_total() -> Optional[int]:
    if not SCAN_HISTORY_PATH.exists():
        return None
    try:
        today_start = datetime.now(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0)
        total = 0
        with open(SCAN_HISTORY_PATH, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                docs_new = record.get("docsNew")
                ended = record.get("endedAt")
                if docs_new is None or not ended:
                    continue
                try:
                    ended_dt = datetime.fromisoformat(ended.replace("Z", "+00:00")).astimezone(PACIFIC)
                except ValueError:
                    continue
                if ended_dt >= today_start:
                    total += docs_new
        return total
    except Exception:
        return None


def render(snapshot: Dict[str, Any], history: List[Dict[str, Any]]) -> None:
    now = snapshot["now"]
    typesense = snapshot["typesense"]
    status_state = snapshot["state"]
    recent_runs = history
    # Show the truly latest run (newest line in history)
    last_run = recent_runs[0] if recent_runs else {}

    feeds = snapshot["feeds"]
    docs_today = snapshot["docs_today"]
    data_size = snapshot["data_size"]

    ts_status = colour("OK", GREEN) if typesense["ok"] else colour("DOWN", RED)
    ts_docs = f"{typesense['docs']:,}" if isinstance(typesense.get("docs"), int) else "—"
    ts_message = typesense.get("message", "")

    docker_status = colour("OK", GREEN) if snapshot["docker_ok"] else colour("DOWN", RED)

    run_label = last_run.get("run") or status_state.get("last_scan_start", "n/a")
    run_timestamp = format_run_id(run_label)

    last_status = last_run.get("status") or status_state.get("last_scan_status", "unknown")
    status_colour = GREEN if last_status == "completed" else (YELLOW if last_status == "running" else RED)
    status_label = colour(last_status.upper(), status_colour)

    started_at = last_run.get("startedAt") or status_state.get("last_scan_start")
    ended_at = last_run.get("endedAt") or status_state.get("last_scan_end")
    duration = None
    started_dt = parse_iso_to_pacific(started_at)
    ended_dt = parse_iso_to_pacific(ended_at)
    if started_at and ended_at:
        try:
            start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            duration = human_duration((end_dt - start_dt).total_seconds())
        except ValueError:
            duration = None

    feeds_total = last_run.get("feedsTotal") or status_state.get("feeds_processed", 0) + status_state.get("feeds_skipped", 0)
    feeds_processed = last_run.get("feedsProcessed") or status_state.get("feeds_processed", 0)
    feeds_skipped = last_run.get("feedsSkipped") or status_state.get("feeds_skipped", 0)

    docs_new = last_run.get("docsNew")
    duplicates = last_run.get("duplicatesSkipped")

    docs_today_display = f"{docs_today:,}" if docs_today is not None else "—"

    print("\033[2J\033[H", end="")
    print(f"{BOLD}CASER Mission Control (detailed){RESET} — {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 80)
    print(f"{BOLD}Services{RESET}")
    print(f"  Typesense   {ts_status:<8} docs: {ts_docs:<15} ({ts_message})")
    print(f"  Docker      {docker_status}")
    print()
    print(f"{BOLD}Feeds Monitored{RESET}")
    print(f"  uscourts    {feeds['uscourts']}")
    print(f"  govinfo     {feeds['govinfo']}")
    print()
    print(f"{BOLD}Latest Run{RESET}")
    if run_timestamp:
        print(f"  Run ID      {run_label} / {run_timestamp}")
    else:
        print(f"  Run ID      {run_label}")
    print(f"  Status      {status_label}", end="")
    if duration:
        print(f"  duration: {duration}")
    else:
        print()
    print(f"  Feeds       {feeds_processed} processed / {feeds_skipped} skipped / total {feeds_total}")
    if docs_new is not None:
        dup_display = duplicates if duplicates is not None else 0
        print(f"  Docs        {docs_new:,} new / {dup_display:,} duplicates skipped")
    if started_at:
        print(f"  Started     {format_pacific(started_dt)}")
    if ended_at:
        print(f"  Ended       {format_pacific(ended_dt)}")
    print()
    print(f"{BOLD}Index Overview{RESET}")
    print(f"  Documents   {ts_docs}")
    print(f"  Added Today {docs_today_display}")
    print(f"  Data Size   {human_size(data_size)}")
    print()
    if recent_runs:
        print(f"{BOLD}Recent Runs{RESET}")
        print(f"{BOLD}{'Run ID':<20} {'Status':<12} {'Docs':<12} {'Feeds':<15} {'Duration':<10} {'Ended (PT)':<25}{RESET}")
        for record in recent_runs:
            status = record.get("status", "unknown")
            colour_code = GREEN if status == "completed" else (YELLOW if status == "running" else RED)
            status_text = colour(status.upper(), colour_code)
            docs_val = record.get("docsNew")
            docs_display = f"{docs_val:,}" if docs_val is not None else "—"
            feeds_processed = record.get("feedsProcessed", "—")
            feeds_total = record.get("feedsTotal", "—")
            run_duration = "—"
            started_iso = record.get("startedAt")
            ended_iso = record.get("endedAt")
            ended_dt_row = parse_iso_to_pacific(ended_iso)
            if started_iso and ended_iso:
                try:
                    start_dt = datetime.fromisoformat(started_iso.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(ended_iso.replace("Z", "+00:00"))
                    run_duration = human_duration((end_dt - start_dt).total_seconds())
                except ValueError:
                    run_duration = "—"
            print(
                f"{record.get('run','n/a'):<20} "
                f"{status_text:<12} "
                f"{docs_display:<12} "
                f"{feeds_processed}/{feeds_total:<11} "
                f"{run_duration:<10} "
                f"{format_pacific(ended_dt_row):<25}"
            )
        print()
    print("Press Ctrl+C to exit (updates every 5 seconds)")


def collect_snapshot() -> Dict[str, Any]:
    typesense = typesense_info()
    state = read_json(SCAN_STATE_PATH)
    feeds = {
        "uscourts": count_feeds(USCOURTS_FEEDS),
        "govinfo": count_feeds(GOVINFO_FEEDS),
    }
    recent_runs = load_recent_history(10)
    docs_today = docs_added_today_total()

    return {
        "now": datetime.now().astimezone(),
        "typesense": typesense,
        "docker_ok": docker_ok(),
        "feeds": feeds,
        "state": state,
        "docs_today": docs_today,
        "data_size": data_size_bytes(),
        "history": recent_runs,
    }


def main(interval: int) -> None:
    try:
        while True:
            snapshot = collect_snapshot()
            render(snapshot, snapshot["history"])
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CASER Mission Control dashboard (detailed).")
    parser.add_argument("--interval", type=int, default=5, help="Refresh interval in seconds (default: 5)")
    args = parser.parse_args()

    if not HOST:
        print("TYPESENSE_HOST is not configured.", file=sys.stderr)
        sys.exit(1)
    main(max(1, args.interval))
