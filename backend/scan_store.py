"""Small SQLite store for scan status, entries, and read errors."""

import os
import ntpath
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Optional


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def default_database_path() -> str:
    configured = os.environ.get("CORESPACE_DB_PATH")
    if configured:
        return os.path.abspath(configured)
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "CoreSpace", "scans.sqlite3")


class ScanStore:
    def __init__(self, database_path: Optional[str] = None):
        self.database_path = os.path.abspath(database_path or default_database_path())
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS scans (
                    id TEXT PRIMARY KEY,
                    root_path TEXT NOT NULL,
                    source TEXT NOT NULL,
                    state TEXT NOT NULL,
                    full_drive INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    elapsed_seconds REAL NOT NULL DEFAULT 0,
                    file_count INTEGER NOT NULL DEFAULT 0,
                    directory_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    partial INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS entries (
                    scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                    relative_path TEXT NOT NULL,
                    parent_relative_path TEXT,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    logical_bytes INTEGER,
                    allocated_bytes INTEGER,
                    partial INTEGER NOT NULL DEFAULT 0,
                    has_children INTEGER NOT NULL DEFAULT 0,
                    pending INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (scan_id, relative_path)
                );
                CREATE INDEX IF NOT EXISTS ix_entries_children
                    ON entries(scan_id, parent_relative_path);
                CREATE TABLE IF NOT EXISTS issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                    relative_path TEXT NOT NULL,
                    code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    issue_type TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_issues_scan
                    ON issues(scan_id, id);
                """
            )
            entry_columns = {row["name"] for row in db.execute("PRAGMA table_info(entries)")}
            if "pending" not in entry_columns:
                db.execute("ALTER TABLE entries ADD COLUMN pending INTEGER NOT NULL DEFAULT 0")
            # A process cannot resume after the web server exits. Keep its
            # partial results, but make that fact clear to the next run.
            db.execute(
                "UPDATE entries SET partial=1, pending=0 WHERE kind='directory' AND pending=1 "
                "AND scan_id IN (SELECT id FROM scans WHERE state IN ('queued','running','cancelling'))"
            )
            db.execute(
                "UPDATE scans SET state='failed', partial=1, finished_at=?, "
                "error=COALESCE(error, 'เซิร์ฟเวอร์ปิดก่อนงานสแกนจบ') "
                "WHERE state IN ('queued', 'running', 'cancelling')",
                (time.time(),),
            )

    def create_scan(self, scan_id: str, root_path: str, source: str, full_drive: bool) -> None:
        now = time.time()
        with self._connect() as db:
            db.execute(
                "INSERT INTO scans(id, root_path, source, state, full_drive, created_at) "
                "VALUES (?, ?, ?, 'queued', ?, ?)",
                (scan_id, root_path, source, int(full_drive), now),
            )

    def get_scan(self, scan_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["partial"] = bool(data["partial"])
        data["full_drive"] = bool(data["full_drive"])
        return data

    def request_cancel(self, scan_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE scans SET state='cancelling' WHERE id=? "
                "AND state IN ('queued','running','cancelling')", (scan_id,))
            return cursor.rowcount == 1

    def set_state(self, scan_id: str, state: str, error: Optional[str] = None) -> None:
        now = time.time()
        with self._connect() as db:
            if state == "running":
                db.execute(
                    "UPDATE scans SET state=CASE WHEN state='cancelling' THEN state ELSE ? END, "
                    "started_at=COALESCE(started_at, ?) WHERE id=?",
                    (state, now, scan_id),
                )
            elif state in {"completed", "partial", "cancelled", "failed"}:
                db.execute(
                    "UPDATE scans SET state=?, finished_at=?, "
                    "elapsed_seconds=CASE WHEN started_at IS NULL THEN 0 ELSE ? - started_at END, "
                    "partial=CASE WHEN ? IN ('partial','cancelled','failed') THEN 1 ELSE partial END, "
                    "error=COALESCE(?, error) WHERE id=?",
                    (state, now, now, state, error, scan_id),
                )
                db.execute(
                    "UPDATE entries SET partial=CASE WHEN pending=1 AND ?!='completed' "
                    "THEN 1 ELSE partial END, pending=0 WHERE scan_id=? AND kind='directory'",
                    (state, scan_id),
                )
                if state in {"completed", "partial"}:
                    current = db.execute(
                        "SELECT root_path, source, created_at FROM scans WHERE id=?",
                        (scan_id,),
                    ).fetchone()
                    db.execute(
                        "DELETE FROM scans WHERE root_path=? COLLATE NOCASE AND source=? AND id!=? AND created_at<? "
                        "AND state IN ('completed','partial','cancelled','failed')",
                        (current["root_path"], current["source"], scan_id, current["created_at"]),
                    )
            else:
                db.execute(
                    "UPDATE scans SET state=?, error=COALESCE(?, error) WHERE id=?",
                    (state, error, scan_id),
                )

    @staticmethod
    def _ancestors(parent_path: Optional[str]) -> Iterable[str]:
        current = parent_path
        while current is not None:
            yield current
            if current == "":
                break
            current = current.rpartition("/")[0]

    def _mark_ancestors_partial(self, db: sqlite3.Connection, scan_id: str, parent_path: Optional[str]) -> None:
        for ancestor in self._ancestors(parent_path):
            db.execute(
                "UPDATE entries SET partial=1 WHERE scan_id=? AND relative_path=?",
                (scan_id, ancestor),
            )

    def _insert_issue(
        self,
        db: sqlite3.Connection,
        scan_id: str,
        relative_path: str,
        code: str,
        message: str,
        issue_type: str,
    ) -> None:
        parent = relative_path.rpartition("/")[0] if relative_path else ""
        db.execute(
            "INSERT INTO issues(scan_id, relative_path, code, message, issue_type, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (scan_id, relative_path, code, message[:1000], issue_type, time.time()),
        )
        column = "skipped_count" if issue_type == "skipped" else "error_count"
        db.execute(f"UPDATE scans SET {column}={column}+1, partial=1 WHERE id=?", (scan_id,))
        db.execute(
            "UPDATE entries SET partial=1 WHERE scan_id=? AND relative_path=? AND kind='directory'",
            (scan_id, relative_path),
        )
        self._mark_ancestors_partial(db, scan_id, parent)

    def add_issue(
        self,
        scan_id: str,
        relative_path: str,
        code: str,
        message: str,
        issue_type: str,
    ) -> None:
        with self._connect() as db:
            self._insert_issue(db, scan_id, relative_path, code, message, issue_type)

    def _insert_entry(self, db: sqlite3.Connection, scan_id: str, entry: Dict[str, Any]) -> None:
        rel = entry["relativePath"]
        parent = entry["parentRelativePath"]
        kind = entry["kind"]
        logical = 0 if kind == "directory" else entry["logicalBytes"]
        allocated = 0 if kind == "directory" else entry.get("allocatedBytes")
        partial = bool(entry.get("partial", False)) or (kind == "file" and allocated is None)

        db.execute(
            "INSERT INTO entries(scan_id, relative_path, parent_relative_path, name, kind, "
            "logical_bytes, allocated_bytes, partial, has_children, pending) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (scan_id, rel, parent, entry["name"], kind, logical, allocated, int(partial), int(kind == "directory")),
        )

        if parent is not None:
            db.execute(
                "UPDATE entries SET has_children=1 WHERE scan_id=? AND relative_path=?",
                (scan_id, parent),
            )

        if kind == "directory":
            db.execute("UPDATE scans SET directory_count=directory_count+1 WHERE id=?", (scan_id,))
        elif kind == "file":
            db.execute("UPDATE scans SET file_count=file_count+1 WHERE id=?", (scan_id,))
            # Folder totals are added as files arrive, so no full tree is
            # kept in Python memory. Unknown allocation propagates upward.
            for ancestor in self._ancestors(parent):
                db.execute(
                    "UPDATE entries SET logical_bytes=COALESCE(logical_bytes,0)+?, "
                    "allocated_bytes=CASE WHEN allocated_bytes IS NULL OR ? IS NULL "
                    "THEN NULL ELSE allocated_bytes+? END, "
                    "partial=CASE WHEN ? THEN 1 ELSE partial END "
                    "WHERE scan_id=? AND relative_path=? AND kind='directory'",
                    (logical, allocated, allocated, int(partial), scan_id, ancestor),
                )

        if partial:
            self._mark_ancestors_partial(db, scan_id, parent)

    def add_records(self, scan_id: str, records: List[Dict[str, Any]]) -> None:
        """Commit a modest batch so large scans do not open a database per row."""
        with self._connect() as db:
            for record in records:
                if record["type"] == "entry":
                    try:
                        self._insert_entry(db, scan_id, record)
                    except sqlite3.IntegrityError:
                        self._insert_issue(
                            db,
                            scan_id,
                            record["relativePath"],
                            "DUPLICATE_ENTRY",
                            "พบ relativePath ซ้ำ หรือบันทึกรายการไม่ได้",
                            "error",
                        )
                else:
                    self._insert_issue(
                        db,
                        scan_id,
                        record["relativePath"],
                        record["code"],
                        record["message"],
                        record["issueType"],
                    )

    def add_entry(self, scan_id: str, entry: Dict[str, Any]) -> None:
        self.add_records(scan_id, [dict(entry, type="entry")])

    def finish_scan(self, scan_id: str, state: str, error: Optional[str] = None) -> None:
        self.set_state(scan_id, state, error)

    def get_folder(self, scan_id: str, relative_path: str) -> Optional[Dict[str, Any]]:
        with self._connect() as db:
            row = db.execute(
                "SELECT relative_path, name, kind, logical_bytes, allocated_bytes, partial, has_children, pending "
                "FROM entries WHERE scan_id=? AND relative_path=? AND kind='directory'",
                (scan_id, relative_path),
            ).fetchone()
        return self._folder_dict(row) if row else None

    def get_entry(self, scan_id: str, relative_path: str) -> Optional[Dict[str, Any]]:
        with self._connect() as db:
            row = db.execute(
                "SELECT relative_path, name, kind FROM entries WHERE scan_id=? AND relative_path=?",
                (scan_id, relative_path),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _folder_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "relativePath": row["relative_path"],
            "name": row["name"],
            "kind": row["kind"],
            "logicalBytes": None if row["pending"] else row["logical_bytes"],
            "allocatedBytes": None if row["pending"] else row["allocated_bytes"],
            "partial": bool(row["partial"]),
            "hasChildren": bool(row["has_children"]),
        }

    def list_children(self, scan_id: str, parent: str, offset: int, limit: int) -> Optional[Dict[str, Any]]:
        with self._connect() as db:
            db.execute("BEGIN")  # Counts, state and page must describe one snapshot.
            scan = db.execute("SELECT state, root_path FROM scans WHERE id=?", (scan_id,)).fetchone()
            if scan is None:
                return None
            active = scan["state"] in {"queued", "running", "cancelling"}
            order = "rowid ASC" if active else (
                "(allocated_bytes IS NULL) ASC, allocated_bytes DESC, "
                "name COLLATE NOCASE ASC, relative_path ASC"
            )
            folder_row = db.execute(
                "SELECT relative_path, name, kind, logical_bytes, allocated_bytes, partial, has_children, pending "
                "FROM entries WHERE scan_id=? AND relative_path=? AND kind='directory'",
                (scan_id, parent),
            ).fetchone()
            if folder_row is None:
                if parent == "" and active:
                    # The selected root is known before WSL starts. Its contents
                    # and totals remain unknown until the scanner sends records.
                    return {
                        "scanId": scan_id, "parent": "", "offset": offset, "limit": limit,
                        "totalChildren": 0, "hasMore": False, "partial": False,
                        "folder": {"relativePath": "", "name": ntpath.basename(scan["root_path"].rstrip("\\/")) or scan["root_path"],
                                   "kind": "directory", "logicalBytes": None, "allocatedBytes": None,
                                   "partial": False, "hasChildren": False},
                        "items": [],
                    }
                return None
            count_row = db.execute(
                "SELECT COUNT(*) AS n FROM entries WHERE scan_id=? AND parent_relative_path=?",
                (scan_id, parent),
            ).fetchone()
            rows = db.execute(
                "SELECT relative_path, name, kind, logical_bytes, allocated_bytes, partial, has_children, pending "
                "FROM entries WHERE scan_id=? AND parent_relative_path=? "
                f"ORDER BY {order} LIMIT ? OFFSET ?",
                (scan_id, parent, limit, offset),
            ).fetchall()

        total = count_row["n"]
        items = [
            {
                "relativePath": row["relative_path"],
                "name": row["name"],
                "kind": row["kind"],
                "logicalBytes": None if row["kind"] == "directory" and row["pending"] else row["logical_bytes"],
                "allocatedBytes": None if row["kind"] == "directory" and row["pending"] else row["allocated_bytes"],
                "partial": bool(row["partial"]),
                "hasChildren": bool(row["has_children"]),
            }
            for row in rows
        ]
        return {
            "scanId": scan_id,
            "parent": parent,
            "offset": offset,
            "limit": limit,
            "totalChildren": total,
            "hasMore": offset + len(items) < total,
            "partial": bool(folder_row["partial"]),
            "folder": self._folder_dict(folder_row),
            "items": items,
        }

    def list_issues(self, scan_id: str, offset: int, limit: int) -> Optional[Dict[str, Any]]:
        scan = self.get_scan(scan_id)
        if scan is None:
            return None
        with self._connect() as db:
            total = db.execute("SELECT COUNT(*) AS n FROM issues WHERE scan_id=?", (scan_id,)).fetchone()["n"]
            rows = db.execute(
                "SELECT relative_path, code, message, issue_type FROM issues "
                "WHERE scan_id=? ORDER BY id LIMIT ? OFFSET ?",
                (scan_id, limit, offset),
            ).fetchall()
        items = [
            {
                "relativePath": row["relative_path"],
                "code": row["code"],
                "message": row["message"],
                "issueType": row["issue_type"],
            }
            for row in rows
        ]
        return {
            "scanId": scan_id,
            "offset": offset,
            "limit": limit,
            "totalIssues": total,
            "hasMore": offset + len(items) < total,
            "items": items,
        }

    def add_record_issue(self, scan_id: str, relative_path: str, code: str, message: str) -> None:
        self.add_issue(scan_id, relative_path, code, message, "error")

    def latest_successful_scan(self, root_path: str) -> Optional[str]:
        root_path = ntpath.normpath(root_path)
        with self._connect() as db:
            row = db.execute(
                "SELECT id FROM scans WHERE root_path=? COLLATE NOCASE AND source='wsl' "
                "AND state IN ('completed','partial') "
                "ORDER BY created_at DESC LIMIT 1",
                (root_path,),
            ).fetchone()
        return row["id"] if row else None

    def iter_entries(self, scan_id: str) -> List[Dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT relative_path, parent_relative_path, name, kind, logical_bytes, allocated_bytes "
                "FROM entries WHERE scan_id=?",
                (scan_id,),
            ).fetchall()
        return [dict(row) for row in rows]
