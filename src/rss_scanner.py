import argparse
import calendar
import fcntl
import json
import logging
import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TextIO, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

import feedparser
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from src.govinfo_harvester import GovinfoHarvester
from src.scan_tracker import tracker
from src.seen_ids_store import SeenIdStore

# Load environment configuration, preferring .env.local when present.
for env_name in (".env.local", ".env"):
    env_path = ROOT / "config" / env_name
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=False)

RUN_ID: Optional[str] = None
_LOGGING_CONFIGURED = False


class RunContextFilter(logging.Filter):
    """Inject the active run identifier into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = RUN_ID or "-"
        # Add a human-readable PT timestamp parsed from RUN_ID
        run_at = "-"
        try:
            base_run = (RUN_ID or "").split("-")[0]
            if base_run and len(base_run) == 16 and base_run.endswith("Z"):
                dt = datetime.strptime(base_run, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                dt_pt = dt.astimezone(ZoneInfo("America/Los_Angeles"))
                run_at = dt_pt.strftime("%Y-%m-%d %I:%M:%S %p PT")
        except Exception:
            run_at = RUN_ID or "-"
        record.run_at = run_at
        return True


class ColorFormatter(logging.Formatter):
    """ANSI colour wrapper for human-friendly terminal output."""

    COLORS = {
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[31m",
    }
    RESET = "\033[0m"

    def __init__(self, fmt: str, datefmt: Optional[str] = None, use_color: bool = False) -> None:
        super().__init__(fmt, datefmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if self.use_color and record.levelno in self.COLORS:
            return f"{self.COLORS[record.levelno]}{message}{self.RESET}"
        return message


def configure_logging() -> None:
    """Ensure the root logger prints timestamps and run identifiers."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.addFilter(RunContextFilter())
        _LOGGING_CONFIGURED = True
        return

    handler = logging.StreamHandler()
    use_color = getattr(handler.stream, "isatty", lambda: False)()
    formatter = ColorFormatter(
        "%(levelname)-8s %(message)s",
        "%Y-%m-%d %H:%M:%S",
        use_color=use_color,
    )
    handler.setFormatter(formatter)
    handler.addFilter(RunContextFilter())

    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    _LOGGING_CONFIGURED = True


configure_logging()
logger = logging.getLogger(__name__)

HOST = os.getenv("TYPESENSE_HOST", "http://localhost:8108")
ADMIN = os.getenv("TYPESENSE_ADMIN_KEY") or os.getenv("TS_ADMIN_KEY")
COLL = os.getenv("COLLECTION", "rss_entries")

USCOURTS_FEEDS = ROOT / "config" / "uscourts-filtered-feed.json"
GOVINFO_FEEDS = ROOT / "config" / "govinfo-filtered-feed.json"
SEEN_IDS_PATH = ROOT / "data" / "seen_ids.txt"
SEEN_IDS_DB_PATH = ROOT / "data" / "seen_ids.sqlite3"
SCAN_LOCK_DIR = ROOT / "data"
SEEN_IDS_MAX = int(os.getenv("SEEN_IDS_MAX", "999999999"))
SEEN_IDS_PENDING_TTL = int(os.getenv("SEEN_IDS_PENDING_TTL", "3600"))
IMPORT_ENDPOINT = f"{HOST}/collections/{COLL}/documents/import"
BATCH_SIZE = int(os.getenv("BATCH_BUFFER_SIZE", "512"))
TS_BATCH_SIZE = int(os.getenv("TS_IMPORT_BATCH_SIZE", "512"))
PROXY_ENDPOINT = os.getenv("PROXY_ENDPOINT", "https://nfq7btef6.j0mpz7gur2.workers.dev")
PROXY_MODE = (os.getenv("PROXY_MODE", "proxy-first").strip().lower())  # proxy-first | proxy-only | direct-only

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CaserBot/1.0; +https://example)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Configure retry logic and connection pooling
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

retries = Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=[429, 500, 502, 503, 504]
)
adapter = HTTPAdapter(
    max_retries=retries,
    pool_connections=20,
    pool_maxsize=50
)
SESSION.mount('http://', adapter)
SESSION.mount('https://', adapter)


def lock_path_for_shard(shard_index: int) -> Path:
    return SCAN_LOCK_DIR / f"scanner-shard-{shard_index}.lock"


def resolve_shard_config(
    shard_index: Optional[int],
    shard_count: Optional[int],
) -> Tuple[int, int]:
    env_index = int(os.getenv("SCAN_SHARD_INDEX", "0"))
    env_count = int(os.getenv("SCAN_SHARD_TOTAL", "1"))
    idx = env_index if shard_index is None else shard_index
    total = env_count if shard_count is None else shard_count
    if total <= 0:
        raise ValueError("SCAN_SHARD_TOTAL must be >= 1")
    if idx < 0 or idx >= total:
        raise ValueError(f"Shard index {idx} must be within [0, {total})")
    return idx, total


def slice_feeds_for_shard(feeds: List[Dict[str, str]], shard_index: int, shard_count: int) -> List[Dict[str, str]]:
    if shard_count <= 1:
        return feeds
    return feeds[shard_index::shard_count]


GOVINFO_HARVESTER = GovinfoHarvester(session=SESSION)

# Tracking params to strip for URL canonicalisation
STRIP_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "ref",
    "source",
    "t",
    "timestamp",
    "_ga",
    "mc_cid",
    "mc_eid",
}

ALLOWED_FEED_DOMAINS = {"uscourts.gov", "govinfo.gov"}

if not ADMIN:
    logger.warning("TYPESENSE_ADMIN_KEY is not set. Document upserts will fail until credentials are provided.")


def get_typesense_doc_count() -> Optional[int]:
    try:
        headers = {"X-TYPESENSE-API-KEY": ADMIN} if ADMIN else {}
        resp = SESSION.get(f"{HOST}/collections/{COLL}", headers=headers, timeout=5)
        if resp.ok:
            data = resp.json()
            return int(data.get("num_documents", 0))
    except Exception:
        return None
    return None


def canonicalize_url(url: str) -> str:
    """Canonicalise URL to create stable IDs."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        if scheme == "http" and netloc.endswith(":80"):
            netloc = netloc[:-3]
        if scheme == "https" and netloc.endswith(":443"):
            netloc = netloc[:-4]
        params = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in params.items() if k not in STRIP_PARAMS}
        query = urlencode(sorted(filtered.items()), doseq=True)
        path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path
        return urlunparse((scheme, netloc, path, parsed.params, query, ""))
    except Exception:
        return url.strip()


def is_allowed_feed_url(url: str) -> bool:
    """Validate that the feed uses HTTPS and belongs to an allow-listed domain."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return False
        netloc = parsed.netloc.lower()
        return any(netloc.endswith(domain) for domain in ALLOWED_FEED_DOMAINS)
    except Exception:
        return False


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def extract_parties(entry: feedparser.FeedParserDict) -> List[str]:
    parties = entry.get("caser_parties") or entry.get("parties")
    if isinstance(parties, list):
        return [str(item).strip() for item in parties if item and str(item).strip()]
    if isinstance(parties, str):
        return [part.strip() for part in parties.split(";") if part.strip()]
    return []


def extract_categories(entry: feedparser.FeedParserDict) -> List[str]:
    categories: List[str] = []
    tags = entry.get("tags") or []
    for tag in tags:
        term = None
        if isinstance(tag, dict):
            term = tag.get("term") or tag.get("label")
        else:
            term = getattr(tag, "term", None) or getattr(tag, "label", None)
        if term:
            categories.append(str(term).strip())
    return categories


def extract_document_link(entry: feedparser.FeedParserDict) -> str:
    direct = entry.get("caser_document_link") or entry.get("documentLink")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    for link_info in entry.get("links") or []:
        href = link_info.get("href") if isinstance(link_info, dict) else getattr(link_info, "href", None)
        if href:
            return str(href).strip()

    summary_html = entry.get("summary") or entry.get("description") or ""
    if summary_html:
        text = unescape(summary_html)
        match = re.search(r'href=["\']([^"\']+)["\']', text)
        if match:
            return match.group(1).strip()
    return ""


def normalize(entry: feedparser.FeedParserDict, feed: Dict[str, str]) -> Dict[str, object]:
    """Normalise uscourts feed entries."""
    guid = entry.get("id") or entry.get("guid") or ""
    link = (entry.get("link") or "").strip()

    if guid and "USCOURTS-" in guid:
        id_source = guid
    elif guid:
        id_source = f"{feed.get('feedId', '')}|{guid}"
    elif link:
        canonical = canonicalize_url(link)
        id_source = f"{feed.get('feedId', '')}|{canonical}"
    else:
        title = (entry.get("title") or "").strip()
        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        pub_str = str(calendar.timegm(pub)) if pub else ""
        id_source = f"{feed.get('feedId', '')}|{title}|{pub_str}"

    doc_id = hashlib_sha1(id_source)

    pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    pub_ts = calendar.timegm(pub_struct) if pub_struct else int(time.time())

    created_struct = entry.get("created_parsed") or entry.get("updated_parsed")
    created_ts = calendar.timegm(created_struct) if created_struct else pub_ts

    description = entry.get("summary") or entry.get("description") or ""

    document_link = extract_document_link(entry)

    categories = extract_categories(entry)
    creator = (entry.get("author") or "").strip()

    return {
        "objectID": doc_id,
        "id": doc_id,
        "title": (entry.get("title") or "").strip(),
        "description": description.strip(),
        "state": feed.get("state", ""),
        "type": feed.get("type", ""),
        "timezone": feed.get("timezone", ""),
        "courtName": feed.get("name", ""),
        "courtSlug": slugify(feed.get("name", "")),
        "courtId": feed.get("courtId") or feed.get("feedId") or slugify(feed.get("name", "")),
        "feedId": feed.get("feedId") or feed.get("courtId") or slugify(feed.get("name", "")),
        "guid": guid or link,
        "link": link,
        "documentLink": document_link,
        "parties": "; ".join(extract_parties(entry)),
        "pubDate": pub_ts,
        "createdAt": created_ts,
        "indexedAt": int(time.time()),
        "source": feed.get("source", "uscourts"),
        "category": categories,
        "creator": creator,
    }


def hashlib_sha1(value: str) -> str:
    import hashlib

    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def push_batch(batch: List[Dict[str, object]]) -> int:
    """Send batch to Typesense with upsert action, return count of successfully upserted docs."""
    if not batch:
        return 0

    # Check for monitored case
    case_webhook = os.getenv("CASE_MONITOR_WEBHOOK_URL")
    monitored_case = os.getenv("MONITORED_CASE", "").lower()
    
    if case_webhook and monitored_case:
        for doc in batch:
            title = doc.get("title", "")
            if monitored_case in title.lower():
                try:
                    import requests as alert_requests
                    alert_requests.post(
                        case_webhook,
                        json={
                            "attachments": [{
                                "color": "#9C27B0",
                                "blocks": [
                                    {
                                        "type": "header",
                                        "text": {"type": "plain_text", "text": "🔔 MONITORED CASE UPDATE"}
                                    },
                                    {
                                        "type": "section",
                                        "fields": [
                                            {"type": "mrkdwn", "text": f"*Case:*\n{monitored_case.title()}"},
                                            {"type": "mrkdwn", "text": f"*Court:*\n{doc.get('court', 'Unknown')}"},
                                            {"type": "mrkdwn", "text": f"*Title:*\n{title}"},
                                            {"type": "mrkdwn", "text": f"*Date:*\n{doc.get('pubDate', 'Unknown')}"}
                                        ]
                                    },
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f"<{doc.get('link', '#')}|View Document>"
                                        }
                                    }
                                ]
                            }]
                        },
                        timeout=10
                    )
                except Exception as exc:
                    logger.warning("Failed to send case monitoring alert: %s", exc)

    ndjson = "\n".join(json.dumps(doc, ensure_ascii=False) for doc in batch)
    for attempt in range(5):
        try:
            response = SESSION.post(
                f"{IMPORT_ENDPOINT}?action=upsert&batch_size={TS_BATCH_SIZE}",
                headers={"X-TYPESENSE-API-KEY": ADMIN, "Content-Type": "text/plain"},
                data=ndjson.encode("utf-8"),
                timeout=120,
            )
            response.raise_for_status()
            upserted = 0
            failed = 0
            for line in response.text.strip().split("\n"):
                if not line:
                    continue
                try:
                    result = json.loads(line)
                    if result.get("success"):
                        upserted += 1
                    else:
                        failed += 1
                        if failed <= 3:
                            logger.error("Document failed: %s", result)
                except json.JSONDecodeError:
                    continue
            if upserted != len(batch):
                logger.warning(
                    "Typesense upsert mismatch (requested=%d, success=%d, failed=%d)",
                    len(batch),
                    upserted,
                    failed,
                )
            time.sleep(0.2)
            return upserted
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 503 and attempt < 4:
                backoff = 3 * (attempt + 1)
                logger.warning("Typesense 503 on batch (retry in %ss)", backoff)
                time.sleep(backoff)
                continue
            raise
    return 0


def fetch_and_parse(url: str, name: str) -> Optional[feedparser.FeedParserDict]:
    """Fetch RSS/Atom feed respecting PROXY_MODE, with relaxed content-type checks."""
    if not is_allowed_feed_url(url):
        logger.error("Feed URL not allowed (HTTPS + govinfo/uscourts domains only): %s", url)
        return None

    mode = PROXY_MODE if PROXY_MODE in {"proxy-first", "proxy-only", "direct-only"} else "proxy-first"
    if mode == "proxy-only":
        attempts: List[Tuple[str, str]] = [("proxy", f"{PROXY_ENDPOINT}/?url={url}")]
    elif mode == "direct-only":
        attempts = [("direct", url)]
    else:  # proxy-first
        attempts = [("proxy", f"{PROXY_ENDPOINT}/?url={url}"), ("direct", url)]
    last_error: Optional[str] = None
    proxy_failed = False

    for mode, target in attempts:
        try:
            response = SESSION.get(target, timeout=(5, 15), stream=True)
            response.raise_for_status()
            
            # Enforce size limit to prevent memory exhaustion
            max_size = 10 * 1024 * 1024  # 10MB
            content = b''
            for chunk in response.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > max_size:
                    raise ValueError(f"Response too large for {name} (>{max_size} bytes)")
            
            # Replace response content with size-limited version
            response._content = content
        except requests.exceptions.RequestException as exc:
            last_error = f"{mode} request error: {exc}"
            logger.warning("%s fetch failed for %s (%s): %s", mode.upper(), name, url, exc)
            if mode == "proxy":
                proxy_failed = True
                if PROXY_MODE == "proxy-only":
                    logger.error("Proxy-only mode: skipping direct for %s", name)
                    break
            continue
        except ValueError as exc:
            last_error = str(exc)
            logger.error("%s: %s", mode.upper(), exc)
            break

        content_type = (response.headers.get("content-type") or "").lower()
        body = response.content

        if "text/html" in content_type:
            lower_body = body.lower()
            if b"<rss" not in lower_body and b"<feed" not in lower_body:
                last_error = f"non-RSS payload content-type={content_type}"
                logger.debug(
                    "Non-RSS payload for %s via %s (content-type=%s)",
                    name,
                    mode,
                    content_type,
                )
                continue

        parsed = feedparser.parse(body)
        if parsed.bozo:
            last_error = f"parse error: {parsed.bozo_exception}"
            logger.debug(
                "Feedparser error for %s via %s: %s",
                name,
                mode,
                parsed.bozo_exception,
            )
            continue

        if mode == "direct" and proxy_failed:
            logger.info("Fetched %s via direct fallback", name)
        return parsed

    if last_error:
        logger.error("Failed to fetch %s (%s): %s", name, url, last_error)
    return None


def is_govinfo_feed(url: str) -> bool:
    return "govinfo.gov" in (url or "").lower()


def process_govinfo_entry(entry: feedparser.FeedParserDict, feed: Dict[str, str]) -> Dict[str, object]:
    try:
        rss_entry = {
            "guid": entry.get("id") or entry.get("guid", ""),
            "title": entry.get("title", ""),
            "description": entry.get("summary", ""),
            "link": entry.get("link", ""),
            "pubDate": calendar.timegm(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            if (entry.get("published_parsed") or entry.get("updated_parsed"))
            else int(time.time()),
            "category": [tag.term if hasattr(tag, "term") else str(tag) for tag in entry.get("tags", [])],
            "creator": entry.get("author", ""),
            "source": "govinfo",
        }

        feed_metadata = {
            "name": feed.get("name", ""),
            "state": feed.get("state", ""),
            "type": feed.get("type", ""),
            "timezone": feed.get("timezone", ""),
            "courtId": feed.get("courtId") or feed.get("feedId") or slugify(feed.get("name", "")),
            "feedId": feed.get("feedId") or feed.get("courtId") or slugify(feed.get("name", "")),
        }

        doc = GOVINFO_HARVESTER.process_entry(rss_entry, feed_metadata)
        doc["createdAt"] = rss_entry["pubDate"]
        doc["indexedAt"] = int(time.time())
        return doc
    except Exception as exc:
        logger.error("Failed to process govinfo entry: %s", exc)
        return normalize(entry, feed)


def append_history(record: Dict[str, object]) -> None:
    history_path = ROOT / "logs" / "scan-history.ndjson"
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(history_path, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to append scan history: %s", exc)


def acquire_scan_lock(lock_file: Path) -> Optional[TextIO]:
    """Prevent concurrent scans by locking a well-known file."""

    try:
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = open(lock_file, "w", encoding="utf-8")
    except Exception as exc:
        logger.error("Unable to open scan lock file: %s", exc)
        return None

    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_handle.write(str(os.getpid()))
        lock_handle.flush()
        return lock_handle
    except BlockingIOError:
        logger.warning("Another rss_scanner instance is already running.")
    except Exception as exc:
        logger.error("Failed to acquire scan lock: %s", exc)

    lock_handle.close()
    return None


def release_scan_lock(handle: TextIO, lock_file: Path) -> None:
    try:
        fcntl.flock(handle, fcntl.LOCK_UN)
    except Exception:
        pass
    finally:
        try:
            handle.close()
        finally:
            try:
                lock_file.unlink(missing_ok=True)
            except Exception:
                pass


def load_feeds() -> List[Dict[str, str]]:
    feeds: List[Dict[str, str]] = []

    def load(path: Path, source: str) -> int:
        if not path.exists():
            logger.warning("Feed list not found: %s", path)
            return 0
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        count = 0
        for feed in data:
            url = (feed.get("url") or "").strip()
            if not url:
                continue
            feed_copy = feed.copy()
            feed_copy["feedId"] = feed_copy.get("feedId") or slugify(feed_copy.get("name", ""))
            feed_copy["source"] = source
            feeds.append(feed_copy)
            count += 1
        return count

    uscourts_count = load(USCOURTS_FEEDS, "uscourts")
    govinfo_count = load(GOVINFO_FEEDS, "govinfo")

    logger.info("Loaded %d uscourts feeds and %d govinfo feeds", uscourts_count, govinfo_count)
    return feeds


def run_once(
    limit: Optional[int] = None,
    shard_index: Optional[int] = None,
    shard_count: Optional[int] = None,
) -> None:
    shard_idx, shard_total = resolve_shard_config(shard_index, shard_count)
    lock_file = lock_path_for_shard(shard_idx)
    lock_handle = acquire_scan_lock(lock_file)
    if not lock_handle:
        return

    seen_store = SeenIdStore(SEEN_IDS_DB_PATH, SEEN_IDS_PATH, SEEN_IDS_PENDING_TTL)
    cleanup_count = seen_store.cleanup_stale_pending()
    seen_store.trim_committed(SEEN_IDS_MAX)
    committed_count, pending_count = seen_store.stats()

    try:
        global RUN_ID
        timestamp_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        RUN_ID = f"{timestamp_id}-s{shard_idx}"

        start_time = datetime.now(timezone.utc)
        tracker.start_scan(shard_index=shard_idx, shard_count=shard_total)
        
        # Send start alert
        alert_webhook = os.getenv("ALERT_WEBHOOK_URL")
        if alert_webhook:
            try:
                import requests as alert_requests
                alert_requests.post(
                    alert_webhook,
                    json={
                        "attachments": [{
                            "color": "#36a64f",
                            "blocks": [
                                {
                                    "type": "header",
                                    "text": {"type": "plain_text", "text": "🚀 SCAN INITIATED"}
                                },
                                {
                                    "type": "section",
                                    "fields": [
                                        {"type": "mrkdwn", "text": f"*Run ID:*\n`{RUN_ID}`"},
                                        {"type": "mrkdwn", "text": f"*Shard:*\n{shard_idx + 1}/{shard_total}"},
                                        {"type": "mrkdwn", "text": f"*Started:*\n{start_time.strftime('%H:%M:%S UTC')}"},
                                        {"type": "mrkdwn", "text": f"*Status:*\nProcessing feeds..."}
                                    ]
                                }
                            ]
                        }]
                    },
                    timeout=10
                )
            except Exception:
                pass

        feeds = load_feeds()
        if limit:
            feeds = feeds[:limit]
        feeds = slice_feeds_for_shard(feeds, shard_idx, shard_total)
        total_feeds = len(feeds)
        logger.info(
            "Shard %d/%d handling %d feeds (limit=%s)",
            shard_idx + 1,
            shard_total,
            total_feeds,
            limit or "all",
        )
        logger.info(
            "Seen-id store ready (committed=%d, pending=%d, cleaned=%d)",
            committed_count,
            pending_count,
            cleanup_count,
        )

        ok_feeds = 0
        skipped_feeds = 0
        docs_created = 0
        duplicates_total = 0
        error: Optional[str] = None
        last_milestone = 0

        pending_ids: List[str] = []

        try:
            for index, feed in enumerate(feeds, start=1):
                url = (feed.get("url") or "").strip()
                name = feed.get("name", "")
                logger.info("[%d/%d] %s", index, total_feeds, name)

                if not url:
                    skipped_feeds += 1
                    logger.warning("Skipping feed without URL: %s", name)
                    continue

                parsed = fetch_and_parse(url, name)
                if not parsed:
                    skipped_feeds += 1
                    continue

                ok_feeds += 1
                entries = parsed.entries or []
                new_docs_in_feed = 0
                duplicates_in_feed = 0

                buffer: List[Dict[str, object]] = []
                pending_ids = []

                def flush_buffer() -> None:
                    nonlocal docs_created, pending_ids
                    if not buffer:
                        return
                    try:
                        created = push_batch(buffer)
                    except Exception as exc:
                        seen_store.release(pending_ids, RUN_ID)
                        logger.error("Batch push failed for %s: %s", name, exc)
                        raise
                    else:
                        seen_store.commit(pending_ids, RUN_ID)
                        docs_created += created
                        if created != len(buffer):
                            logger.debug(
                                "Batch upsert mismatch for %s (requested=%d, success=%d)",
                                name,
                                len(buffer),
                                created,
                            )
                    finally:
                        buffer.clear()
                        pending_ids = []

                for entry in entries:
                    quick_id = None
                    if is_govinfo_feed(url):
                        guid = entry.get("id") or entry.get("guid", "")
                        quick_id = hashlib_sha1(guid) if guid else None
                        if quick_id and not seen_store.reserve(quick_id, RUN_ID):
                            duplicates_in_feed += 1
                            continue

                    try:
                        doc = process_govinfo_entry(entry, feed) if is_govinfo_feed(url) else normalize(entry, feed)
                    except Exception:
                        if quick_id:
                            seen_store.release([quick_id], RUN_ID)
                        raise
                    doc_id = doc["objectID"]

                    if quick_id:
                        promoted = seen_store.promote(quick_id, doc_id, RUN_ID)
                        if not promoted:
                            duplicates_in_feed += 1
                            continue
                    else:
                        if not seen_store.reserve(doc_id, RUN_ID):
                            duplicates_in_feed += 1
                            continue

                    buffer.append(doc)
                    pending_ids.append(doc_id)
                    new_docs_in_feed += 1

                    if len(buffer) >= BATCH_SIZE:
                        flush_buffer()

                flush_buffer()

                duplicates_total += duplicates_in_feed
                logger.info(
                    "✅ +%d new | %d dup | 📊 %d total",
                    new_docs_in_feed,
                    duplicates_in_feed,
                    docs_created,
                )
                
                # Send milestone alert every 100K docs
                if docs_created // 100000 > last_milestone:
                    last_milestone = docs_created // 100000
                    if alert_webhook:
                        try:
                            alert_requests.post(
                                alert_webhook,
                                json={
                                    "attachments": [{
                                        "color": "#2196F3",
                                        "blocks": [
                                            {
                                                "type": "section",
                                                "text": {
                                                    "type": "mrkdwn",
                                                    "text": f"📊 *MILESTONE REACHED*\n`{last_milestone * 100}K` documents indexed"
                                                }
                                            },
                                            {
                                                "type": "context",
                                                "elements": [
                                                    {"type": "mrkdwn", "text": f"Run: `{RUN_ID}` • Feed: {index}/{total_feeds}"}
                                                ]
                                            }
                                        ]
                                    }]
                                },
                                timeout=10
                            )
                        except Exception:
                            pass

                time.sleep(0.5)

        except Exception as exc:
            error = str(exc)
            logger.exception("Scan failed: %s", exc)
        finally:
            seen_store.release(pending_ids, RUN_ID)
            tracker.end_scan(
                ok_feeds,
                skipped_feeds,
                docs_created,
                error,
                shard_idx,
                shard_total,
            )

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            status = "error" if error else "completed"

            append_history(
                {
                    "run": RUN_ID,
                    "status": status,
                    "shardIndex": shard_idx,
                    "shardCount": shard_total,
                    "startedAt": start_time.isoformat(),
                    "endedAt": end_time.isoformat(),
                    "feedsTotal": total_feeds,
                    "feedsProcessed": ok_feeds,
                    "feedsSkipped": skipped_feeds,
                    "docsNew": docs_created,
                    "duplicatesSkipped": duplicates_total,
                    "error": error,
                }
            )

            logger.info(
                "Summary status=%s feeds_ok=%d feeds_skipped=%d docs_new=%d duplicates=%d duration=%.2fs",
                status,
                ok_feeds,
                skipped_feeds,
                docs_created,
                duplicates_total,
                duration,
            )
            
            # Send completion alert
            if alert_webhook:
                try:
                    color = "#36a64f" if status == "completed" else "#ff0000"
                    emoji = "✅" if status == "completed" else "❌"
                    alert_requests.post(
                        alert_webhook,
                        json={
                            "attachments": [{
                                "color": color,
                                "blocks": [
                                    {
                                        "type": "header",
                                        "text": {"type": "plain_text", "text": f"{emoji} SCAN {status.upper()}"}
                                    },
                                    {
                                        "type": "section",
                                        "fields": [
                                            {"type": "mrkdwn", "text": f"*Run ID:*\n`{RUN_ID}`"},
                                            {"type": "mrkdwn", "text": f"*Duration:*\n{int(duration//60)}m {int(duration%60)}s"},
                                            {"type": "mrkdwn", "text": f"*Feeds Processed:*\n{ok_feeds}/{total_feeds}"},
                                            {"type": "mrkdwn", "text": f"*Feeds Failed:*\n{skipped_feeds}"},
                                            {"type": "mrkdwn", "text": f"*New Documents:*\n{docs_created:,}"},
                                            {"type": "mrkdwn", "text": f"*Duplicates Skipped:*\n{duplicates_total:,}"}
                                        ]
                                    },
                                    {
                                        "type": "context",
                                        "elements": [
                                            {"type": "mrkdwn", "text": f"Completed at {end_time.strftime('%H:%M:%S UTC')}"}
                                        ]
                                    }
                                ]
                            }]
                        },
                        timeout=10
                    )
                except Exception:
                    pass
            
            # Alert if high feed failure rate
            if total_feeds > 0:
                failure_rate = skipped_feeds / total_feeds
                if failure_rate > 0.10:  # Alert if >10% of feeds fail
                    alert_webhook = os.getenv("ALERT_WEBHOOK_URL")
                    if alert_webhook:
                        try:
                            import requests as alert_requests
                            alert_requests.post(
                                alert_webhook,
                                json={
                                    "attachments": [{
                                        "color": "#ff9800",
                                        "blocks": [
                                            {
                                                "type": "header",
                                                "text": {"type": "plain_text", "text": "⚠️ HIGH FAILURE RATE DETECTED"}
                                            },
                                            {
                                                "type": "section",
                                                "fields": [
                                                    {"type": "mrkdwn", "text": f"*Failure Rate:*\n{failure_rate*100:.1f}%"},
                                                    {"type": "mrkdwn", "text": f"*Failed Feeds:*\n{skipped_feeds}/{total_feeds}"},
                                                    {"type": "mrkdwn", "text": f"*Run ID:*\n`{RUN_ID}`"},
                                                    {"type": "mrkdwn", "text": f"*Action Required:*\nInvestigate feed sources"}
                                                ]
                                            }
                                        ]
                                    }]
                                },
                                timeout=10
                            )
                        except Exception as exc:
                            logger.warning("Failed to send alert webhook: %s", exc)

            RUN_ID = None
    finally:
        try:
            seen_store.write_mirror_file()
        except Exception as exc:
            logger.warning("Failed to mirror seen-id file: %s", exc)
        finally:
            seen_store.close()
        release_scan_lock(lock_handle, lock_file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CASER RSS scanner")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional number of feeds to scan (after sharding).",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=None,
        help="Shard index (overrides SCAN_SHARD_INDEX).",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=None,
        help="Total shard count (overrides SCAN_SHARD_TOTAL).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = parse_args()
    run_once(
        limit=cli_args.limit,
        shard_index=cli_args.shard_index,
        shard_count=cli_args.shard_count,
    )
