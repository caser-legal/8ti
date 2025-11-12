from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Sequence


class SeenIdStore:
    """Concurrent-safe seen-id registry backed by SQLite."""

    def __init__(
        self,
        db_path: Path,
        mirror_path: Path,
        pending_ttl_seconds: int = 3600,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.mirror_path = Path(mirror_path)
        self.pending_ttl_seconds = pending_ttl_seconds

        self._conn = sqlite3.connect(
            str(self.db_path),
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA busy_timeout=5000;")
        try:
            self._conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.OperationalError:
            pass
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA temp_store=MEMORY;")

        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_ids (
                id TEXT PRIMARY KEY,
                status INTEGER NOT NULL, -- 0=pending, 1=committed
                owner TEXT,
                updated_at INTEGER NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_seen_pending
            ON seen_ids(status, updated_at)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_seen_owner
            ON seen_ids(owner, status)
            """
        )
        if self._is_empty() and self.mirror_path.exists():
            self._bootstrap_from_mirror()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def cleanup_stale_pending(self) -> int:
        cutoff = int(time.time()) - self.pending_ttl_seconds
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM seen_ids WHERE status = 0 AND updated_at < ?",
                (cutoff,),
            )
            return cursor.rowcount or 0

    def reserve(self, doc_id: str, run_id: str) -> bool:
        now = int(time.time())
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO seen_ids (id, status, owner, updated_at)
                    VALUES (?, 0, ?, ?)
                    """,
                    (doc_id, run_id, now),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def promote(self, placeholder_id: str, final_id: str, run_id: str) -> bool:
        if placeholder_id == final_id:
            return True

        now = int(time.time())
        try:
            with self._conn:
                cursor = self._conn.execute(
                    """
                    UPDATE seen_ids
                       SET id = ?, updated_at = ?
                     WHERE id = ?
                       AND owner = ?
                       AND status = 0
                    """,
                    (final_id, now, placeholder_id, run_id),
                )
                if cursor.rowcount:
                    return True
        except sqlite3.IntegrityError:
            # final id already exists; fall through to cleanup
            pass

        self.release([placeholder_id], run_id)
        return False

    def commit(self, doc_ids: Sequence[str], run_id: str) -> None:
        if not doc_ids:
            return
        now = int(time.time())
        params = [(now, doc_id, run_id) for doc_id in doc_ids]
        with self._conn:
            self._conn.executemany(
                """
                UPDATE seen_ids
                   SET status = 1,
                       owner = NULL,
                       updated_at = ?
                 WHERE id = ?
                   AND owner = ?
                   AND status = 0
                """,
                params,
            )

    def release(self, doc_ids: Sequence[str], run_id: str) -> None:
        if not doc_ids:
            return
        params = [(doc_id, run_id) for doc_id in doc_ids]
        with self._conn:
            self._conn.executemany(
                """
                DELETE FROM seen_ids
                 WHERE id = ?
                   AND owner = ?
                   AND status = 0
                """,
                params,
            )

    def stats(self) -> tuple[int, int]:
        committed = self._conn.execute(
            "SELECT COUNT(*) FROM seen_ids WHERE status = 1"
        ).fetchone()[0]
        pending = self._conn.execute(
            "SELECT COUNT(*) FROM seen_ids WHERE status = 0"
        ).fetchone()[0]
        return committed, pending

    def write_mirror_file(self) -> None:
        committed_ids = self._conn.execute(
            "SELECT id FROM seen_ids WHERE status = 1 ORDER BY updated_at ASC"
        ).fetchall()
        lines = [row[0] for row in committed_ids]
        self._atomic_write(lines)

    def trim_committed(self, max_size: int) -> None:
        if max_size <= 0:
            return
        row = self._conn.execute(
            "SELECT COUNT(*) FROM seen_ids WHERE status = 1"
        ).fetchone()
        total = row[0]
        if total <= max_size:
            return
        to_delete = total - max_size
        with self._conn:
            self._conn.execute(
                """
                DELETE FROM seen_ids
                 WHERE id IN (
                       SELECT id
                         FROM seen_ids
                        WHERE status = 1
                        ORDER BY updated_at ASC
                        LIMIT ?
                 )
                """,
                (to_delete,),
            )

    def replace_with(self, doc_ids: Iterable[str]) -> None:
        now = int(time.time())
        with self._conn:
            self._conn.execute("DELETE FROM seen_ids")
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO seen_ids (id, status, owner, updated_at)
                VALUES (?, 1, NULL, ?)
                """,
                ((doc_id, now) for doc_id in doc_ids),
            )

    def _atomic_write(self, lines: Sequence[str]) -> None:
        self.mirror_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.mirror_path.with_suffix(f".tmp.{os.getpid()}")
        try:
            with open(tmp_path, "w", encoding="utf-8") as fp:
                fp.write("\n".join(lines))
                if lines:
                    fp.write("\n")
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp_path, self.mirror_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _is_empty(self) -> bool:
        row = self._conn.execute("SELECT COUNT(*) FROM seen_ids").fetchone()
        return row[0] == 0

    def _bootstrap_from_mirror(self) -> None:
        try:
            with open(self.mirror_path, "r", encoding="utf-8") as fp:
                ids = [line.strip() for line in fp if line.strip()]
        except FileNotFoundError:
            return
        if not ids:
            return
        now = int(time.time())
        with self._conn:
            self._conn.executemany(
                """
                INSERT OR IGNORE INTO seen_ids (id, status, owner, updated_at)
                VALUES (?, 1, NULL, ?)
                """,
                ((doc_id, now) for doc_id in ids),
            )
