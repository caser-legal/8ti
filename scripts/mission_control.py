#!/usr/bin/env python3
"""CASER Mission Control dashboard."""

import json
import os
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(env_path, override=False)

HOST = os.getenv("TYPESENSE_HOST", "http://localhost:8108")
ADMIN = os.getenv("TYPESENSE_ADMIN_KEY") or os.getenv("TS_ADMIN_KEY")

SCAN_STATE_PATH = ROOT / "logs" / "scan_state.json"
SCAN_HISTORY_PATH = ROOT / "logs" / "scan-history.ndjson"
LOG_FILE_PATH = ROOT / "logs" / "feed-scan.log"
USCOURTS_FEEDS = ROOT / "config" / "uscourts-filtered-feed.json"
GOVINFO_FEEDS = ROOT / "config" / "govinfo-filtered-feed.json"

BOLD = "\033[1m"
RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
PACIFIC = ZoneInfo("America/Los_Angeles")
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


def read_last_history() -> Optional[Dict[str, Any]]:
    if not SCAN_HISTORY_PATH.exists():
        return None
    try:
        with open(SCAN_HISTORY_PATH, "r", encoding="utf-8") as fp:
            last_line = deque(fp, maxlen=1)
        if not last_line:
            return None
        return json.loads(last_line[0])
    except Exception:
        return None


def load_recent_history(limit: int = 20) -> List[Dict[str, Any]]:
    if not SCAN_HISTORY_PATH.exists():
        return []
    try:
        with open(SCAN_HISTORY_PATH, "r", encoding="utf-8") as fp:
            lines = deque(fp, maxlen=limit)
        # newest first
        return [json.loads(line) for line in reversed(lines) if line.strip()]
    except Exception:
        return []


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


def tail_lines(path: Path, n: int = 5):
    if not path.exists():
        return []
    try:
        from collections import deque as _deque
        with open(path, "r", encoding="utf-8", errors="replace") as fp:
            return list(_deque(fp, maxlen=n))
    except Exception:
        return []


def fetch_typesense_info() -> Dict[str, Any]:
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


def docker_running() -> bool:
    try:
        return subprocess.run(["docker", "ps"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def data_directory_size() -> int:
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


def docs_added_today_total() -> Optional[int]:
    if not SCAN_HISTORY_PATH.exists():
        return None
    total = 0
    today_start = datetime.now(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
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


def collect_snapshot() -> Dict[str, Any]:
    typesense = fetch_typesense_info()
    state = read_json(SCAN_STATE_PATH)
    recent_runs = load_recent_history()
    # Always show the truly latest run (last line in history)
    primary = recent_runs[0] if recent_runs else {}
    feeds_uscourts = count_feeds(USCOURTS_FEEDS)
    feeds_govinfo = count_feeds(GOVINFO_FEEDS)
    data_size = data_directory_size()
    docs_today = docs_added_today_total()

    return {
        "now": datetime.now().astimezone(),
        "typesense": typesense,
        "docker_ok": docker_running(),
        "feeds": {"uscourts": feeds_uscourts, "govinfo": feeds_govinfo},
        "scan_state": state,
        "history": primary,
        "data_size": data_size,
        "docs_today": docs_today,
    }


def render(snapshot: Dict[str, Any]) -> None:
    now = snapshot["now"].strftime("%Y-%m-%d %H:%M:%S %Z")
    typesense = snapshot["typesense"]
    history = snapshot["history"]
    state = snapshot["scan_state"]

    ts_status = colour("OK", GREEN) if typesense["ok"] else colour("DOWN", RED)
    ts_docs = f"{typesense['docs']:,}" if isinstance(typesense.get("docs"), int) else "—"
    ts_message = typesense.get("message", "")

    docker_status = colour("OK", GREEN) if snapshot["docker_ok"] else colour("DOWN", RED)

    last_run_id = history.get("run") or state.get("last_scan_start", "") or "n/a"
    last_status = history.get("status") or state.get("last_scan_status", "unknown")
    last_status_colour = GREEN if last_status == "completed" else (YELLOW if last_status == "running" else RED)
    status_label = colour(last_status.upper(), last_status_colour)
    run_human = format_run_id(last_run_id)

    # Intentionally hide feeds/docs summary lines per user request

    started_at = history.get("startedAt") or state.get("last_scan_start")
    ended_at = history.get("endedAt") or state.get("last_scan_end")
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

    docs_today = snapshot["docs_today"]
    docs_today_label = f"{docs_today:,}" if isinstance(docs_today, int) else "—"

    data_size = human_size(snapshot["data_size"])

    feeds = snapshot["feeds"]

    print("\033[2J\033[H", end="")  # Clear screen
    print(f"{BOLD}CASER Mission Control{RESET} — {now}")
    print("=" * 60)
    print(f"{BOLD}Services{RESET}")
    print(f"  Typesense   {ts_status:<8} docs: {ts_docs:<15} ({ts_message})")
    print(f"  Docker      {docker_status}")
    print()
    print(f"{BOLD}Feeds Monitored{RESET}")
    print(f"  uscourts    {feeds['uscourts']}")
    print(f"  govinfo     {feeds['govinfo']}")
    print()
    run_label = f"{last_run_id}"
    if run_human:
        run_label = f"{last_run_id} / {run_human}"
    print(f"{BOLD}Latest Run{RESET} ({run_label})")
    print(f"  Status      {status_label}", end="")
    if duration:
        print(f"  duration: {duration}")
    else:
        print()
    # Feeds and Docs lines removed
    if started_at:
        print(f"  Started     {format_pacific(started_dt)}")
    if ended_at:
        print(f"  Ended       {format_pacific(ended_dt)}")
    print(f"{BOLD}Index Overview{RESET}")
    print(f"  Documents   {ts_docs}")
    print(f"  Data Size   {data_size}")

    # Recent scan log tail (always show last 5 lines)
    print()
    print(f"{BOLD}Log Tail{RESET} (last 5 lines)")
    log_tail = tail_lines(LOG_FILE_PATH, 5)
    if log_tail:
        for line in log_tail:
            # already contains newline
            print(line.rstrip())
    else:
        print("  (no log yet)")


def main() -> None:
    try:
        while True:
            snapshot = collect_snapshot()
            render(snapshot)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == "__main__":
    if not HOST:
        print("TYPESENSE_HOST is not configured.", file=sys.stderr)
        sys.exit(1)
    main()
