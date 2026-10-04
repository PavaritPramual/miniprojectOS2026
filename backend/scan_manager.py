"""Runs explicit sample or WSL scans and stores their results in SQLite."""

import json
import ntpath
import queue
import os
import subprocess
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

from backend.allocated_size import get_allocated_file_size
from backend.scan_store import ScanStore


class ScanError(Exception):
    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


class ScanManager:
    def __init__(self, store: Optional[ScanStore] = None):
        self.store = store or ScanStore()
        self.wsl_executable = os.environ.get("CORESPACE_WSL", "wsl.exe")
        self.wsl_distro = os.environ.get("CORESPACE_WSL_DISTRO", "Ubuntu")
        self.scanner_wsl_path = os.environ.get("CORESPACE_SCANNER_WSL_PATH", "").strip()
        self.sample_path = os.path.abspath(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "examples", "scan.ndjson")
        )
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="corespace-scan")
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _is_full_drive(path: str) -> bool:
        drive, tail = ntpath.splitdrive(path)
        return bool(drive and tail in ("\\", "/"))

    def start_scan(self, payload: Dict[str, Any]) -> Dict[str, str]:
        if not isinstance(payload, dict):
            raise ScanError(400, "INVALID_BODY", "คำขอไม่ถูกต้อง")
        source = payload.get("source", "wsl")
        if not isinstance(source, str) or source not in {"wsl", "sample"}:
            raise ScanError(400, "INVALID_SOURCE", "เลือกแหล่งอ่านข้อมูลไม่ถูกต้อง")

        raw_path = payload.get("path")
        if source == "sample":
            root_path = str(raw_path or "ตัวอย่างข้อมูล")
            full_drive = False
        else:
            root_path = self._validate_windows_folder(raw_path)
            if not self.scanner_wsl_path:
                raise ScanError(
                    503,
                    "SCANNER_NOT_CONFIGURED",
                    "ยังไม่ได้ตั้งตำแหน่งโปรแกรม C ใน WSL",
                )
            if os.name != "nt":
                raise ScanError(503, "WINDOWS_REQUIRED", "การสแกนไฟล์ Windows ต้องเปิดเซิร์ฟเวอร์บน Windows")
            full_drive = self._is_full_drive(root_path)

        with self._lock:
            if full_drive and self._has_active_full_drive():
                raise ScanError(409, "FULL_DRIVE_SCAN_ACTIVE", "กำลังสแกนทั้งไดรฟ์อยู่อีกงานหนึ่ง")

            scan_id = uuid.uuid4().hex
            cancel_event = threading.Event()
            job = {
                "cancel": cancel_event,
                "process": None,
                "pid": None,
                "pid_file": None,
                "stop_requested": False,
                "cancel_at": None,
                "source": source,
            }
            self.store.create_scan(scan_id, root_path, source, full_drive)
            self._jobs[scan_id] = job
            try:
                self._executor.submit(self._run_scan, scan_id, root_path, source, job)
            except Exception:
                self._jobs.pop(scan_id, None)
                self.store.finish_scan(scan_id, "failed", "เริ่มงานสแกนไม่สำเร็จ")
                raise
        return {"id": scan_id, "state": "queued", "source": source}

    @staticmethod
    def _validate_windows_folder(raw_path: Any) -> str:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ScanError(400, "PATH_REQUIRED", "กรุณาเลือกโฟลเดอร์")
        path = ntpath.abspath(raw_path.strip())
        drive, _ = ntpath.splitdrive(path)
        if not drive or path.startswith("\\\\"):
            raise ScanError(400, "LOCAL_PATH_REQUIRED", "รองรับเฉพาะโฟลเดอร์ในไดรฟ์เครื่องนี้")
        if not os.path.isdir(path):
            raise ScanError(400, "FOLDER_NOT_FOUND", "ไม่พบโฟลเดอร์ที่เลือก")
        if os.path.islink(path):
            raise ScanError(400, "LINKED_ROOT_NOT_SUPPORTED", "เลือกโฟลเดอร์จริง ไม่ใช่ลิงก์")
        return path

    def _has_active_full_drive(self) -> bool:
        with self.store._connect() as db:
            row = db.execute(
                "SELECT 1 FROM scans WHERE full_drive=1 "
                "AND state IN ('queued','running','cancelling') LIMIT 1"
            ).fetchone()
        return row is not None

    def get_status(self, scan_id: str) -> Optional[Dict[str, Any]]:
        scan = self.store.get_scan(scan_id)
        if scan is None:
            return None
        elapsed = scan["elapsed_seconds"]
        if scan["state"] in {"running", "cancelling"} and scan["started_at"] is not None:
            elapsed = max(0, time.time() - scan["started_at"])
        return {
            "id": scan["id"],
            "rootPath": scan["root_path"],
            "source": scan["source"],
            "isSample": scan["source"] == "sample",
            "state": scan["state"],
            "fileCount": scan["file_count"],
            "directoryCount": scan["directory_count"],
            "errorCount": scan["error_count"],
            "skippedCount": scan["skipped_count"],
            "elapsedSeconds": round(elapsed, 2),
            "partial": bool(scan["partial"]),
            "error": scan["error"],
        }

    def get_children(self, scan_id: str, parent: str, offset: int, limit: int) -> Optional[Dict[str, Any]]:
        return self.store.list_children(scan_id, parent, offset, limit)

    def get_issues(self, scan_id: str, offset: int, limit: int) -> Optional[Dict[str, Any]]:
        return self.store.list_issues(scan_id, offset, limit)

    def cancel_scan(self, scan_id: str) -> Tuple[int, Dict[str, str]]:
        with self._lock:
            scan = self.store.get_scan(scan_id)
            if scan is None:
                return 404, {"code": "SCAN_NOT_FOUND", "detail": "ไม่พบงานสแกน"}
            if scan["state"] not in {"queued", "running", "cancelling"}:
                return 409, {"code": "SCAN_ALREADY_FINISHED", "detail": "งานสแกนจบแล้ว"}
            job = self._jobs.get(scan_id)
            if job:
                if not self.store.request_cancel(scan_id):
                    return 409, {"code": "SCAN_ALREADY_FINISHED", "detail": "งานสแกนจบแล้ว"}
                job["cancel"].set()
                if job.get("cancel_at") is None:
                    job["cancel_at"] = time.monotonic()
            return 202, {"id": scan_id, "state": "cancelling"}

    def shutdown(self) -> None:
        """Cancel active scans before the local server closes."""
        with self._lock:
            scan_ids = list(self._jobs)
        for scan_id in scan_ids:
            self.cancel_scan(scan_id)
        self._executor.shutdown(wait=True)

    def _linux_alive(self, pid: int, timeout: float = 2) -> Optional[bool]:
        try:
            result = subprocess.run(
                [self.wsl_executable, "-d", self.wsl_distro, "--exec", "sh", "-c",
                 'if [ ! -d /proc/"$1" ]; then exit 10; fi; '
                 'state=$(sed -n "s/^State:[[:space:]]*\\([A-Z]\\).*/\\1/p" /proc/"$1"/status); '
                 '[ "$state" = Z ] && exit 10; [ -n "$state" ] || exit 11; exit 0',
                 "corespace-check", str(pid)],
                capture_output=True, timeout=max(0.1, timeout), check=False,
            )
            if result.returncode == 0:
                return True
            if result.returncode == 10:
                return False
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None

    def _stop_process(self, job: Dict[str, Any]) -> bool:
        """Stop the Linux PID, then confirm it; ending wsl.exe alone is insufficient."""
        process = job.get("process")
        if process is None:
            return True
        deadline = (job.get("cancel_at") or time.monotonic()) + 15
        pid = job.get("pid")
        confirmed = False
        if pid:
            if process.poll() is not None:
                confirmed = self._linux_alive(pid, min(2, max(0.1, deadline-time.monotonic()))) is False
            for signal_name, grace in (("TERM", 3), ("KILL", 2)):
                if confirmed or time.monotonic() >= deadline:
                    break
                try:
                    subprocess.run(
                        [self.wsl_executable, "-d", self.wsl_distro, "--exec", "kill", f"-{signal_name}", str(pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=max(0.1, min(2, deadline-time.monotonic())), check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass
                try:
                    process.wait(timeout=max(0.1, min(grace, deadline-time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
                if time.monotonic() < deadline:
                    confirmed = self._linux_alive(pid, min(2, deadline-time.monotonic())) is False
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.5)
            except OSError:
                confirmed = False
        job["stop_confirmed"] = confirmed
        return confirmed

    def _run_scan(self, scan_id: str, root_path: str, source: str, job: Dict[str, Any]) -> None:
        buffered = []
        saw_done = None
        process = None
        pid_file = None
        stderr_chunks = []

        def flush():
            if buffered:
                self.store.add_records(scan_id, buffered)
                buffered.clear()

        try:
            if job["cancel"].is_set():
                self.store.finish_scan(scan_id, "cancelled")
                return
            self.store.set_state(scan_id, "running")
            if job["cancel"].is_set():
                self.store.finish_scan(scan_id, "cancelled")
                return

            if source == "sample":
                with open(self.sample_path, "r", encoding="utf-8") as stream:
                    exit_code, saw_done, actual_files, actual_directories, actual_errors, actual_skips = self._consume_stream(
                        scan_id, root_path, stream, source, job, flush, buffered
                    )
            else:
                process, pid_file = self._start_wsl_process(root_path, job)
                job["process"] = process
                job["pid_file"] = pid_file
                self._read_pid(process, pid_file, job)
                stderr_thread = threading.Thread(
                    target=self._drain_stderr,
                    args=(process.stderr, stderr_chunks),
                    name="corespace-stderr",
                    daemon=True,
                )
                stderr_thread.start()
                exit_code, saw_done, actual_files, actual_directories, actual_errors, actual_skips = self._consume_stream(
                    scan_id, root_path, process.stdout, source, job, flush, buffered
                )
                if job["cancel"].is_set():
                    self._stop_process(job)
                else:
                    process.wait(timeout=5)
                exit_code = process.returncode if process.returncode is not None else exit_code
                stderr_thread.join(timeout=1)

            # Re-read counts because they are updated in the database batch.
            flush()
            scan = self.store.get_scan(scan_id)
            if job["cancel"].is_set():
                if process is None or job.get("stop_confirmed"):
                    self.store.finish_scan(scan_id, "cancelled")
                else:
                    self.store.add_issue(scan_id, "", "CANCEL_NOT_CONFIRMED", "ยืนยันไม่ได้ว่าโปรแกรมใน Ubuntu หยุดแล้ว", "error")
                    self.store.finish_scan(scan_id, "failed", "ยืนยันการหยุดโปรแกรมไม่ได้")
                return
            if source == "wsl" and exit_code not in (0, 1):
                detail = "โปรแกรม C จบก่อนอ่านโฟลเดอร์เสร็จ"
                if stderr_chunks:
                    detail += ": " + "".join(stderr_chunks)[-500:]
                self.store.add_issue(scan_id, "", "SCANNER_EXIT", detail, "error")
            if not saw_done:
                self.store.add_issue(scan_id, "", "MISSING_DONE", "ข้อมูลไม่ได้แจ้งว่าการอ่านจบแล้ว", "error")
            elif saw_done is not None:
                if saw_done["fileCount"] != actual_files or saw_done["directoryCount"] != actual_directories:
                    self.store.add_issue(
                        scan_id, "", "COUNT_MISMATCH",
                        "จำนวนไฟล์หรือโฟลเดอร์ที่โปรแกรม C รายงานไม่ตรงกับรายการที่รับได้", "error",
                    )
                if saw_done["errorCount"] != actual_errors or saw_done["skippedCount"] != actual_skips:
                    self.store.add_issue(
                        scan_id, "", "ISSUE_COUNT_MISMATCH",
                        "จำนวนรายการที่อ่านไม่ได้หรือข้ามไม่ตรงกับที่โปรแกรม C รายงาน", "error",
                    )
                if not saw_done["complete"] and scan["error_count"] == 0 and scan["skipped_count"] == 0:
                    self.store.add_issue(scan_id, "", "INCOMPLETE_SCAN", "โปรแกรมรายงานว่าอ่านได้ไม่ครบ", "error")

            scan = self.store.get_scan(scan_id)
            if source == "wsl" and exit_code not in (0, 1):
                final_state = "failed" if scan["file_count"] == 0 and scan["directory_count"] == 0 else "partial"
            elif source == "wsl" and exit_code == 1:
                final_state = "partial"
            elif scan["error_count"] or scan["skipped_count"] or scan["partial"]:
                final_state = "partial"
            else:
                final_state = "completed"
            self.store.finish_scan(scan_id, final_state)
        except FileNotFoundError as exc:
            if process is not None:
                self._stop_process(job)
            self.store.add_issue(scan_id, "", "SOURCE_NOT_FOUND", str(exc), "error")
            self.store.finish_scan(scan_id, "failed", str(exc))
        except Exception as exc:
            try:
                confirmed = self._stop_process(job)
                flush()
                if job["cancel"].is_set() and confirmed:
                    self.store.finish_scan(scan_id, "cancelled")
                    return
                if not confirmed:
                    self.store.add_issue(scan_id, "", "CANCEL_NOT_CONFIRMED", "ยืนยันการหยุดโปรแกรมไม่ได้", "error")
                self.store.add_issue(scan_id, "", "SCAN_FAILED", str(exc), "error")
                self.store.finish_scan(scan_id, "failed", str(exc))
            except Exception:
                pass
        finally:
            if process is not None:
                try:
                    if process.poll() is None:
                        self._stop_process(job)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
            if pid_file:
                try:
                    os.unlink(pid_file)
                except OSError:
                    pass
            reader = job.get("reader")
            if reader:
                reader.join(timeout=1)
            if process is not None and process.poll() is not None:
                for pipe in (process.stdout, process.stderr):
                    if pipe:
                        pipe.close()
            with self._lock:
                self._jobs.pop(scan_id, None)

    @staticmethod
    def _stream_lines(stream, job, on_idle):
        """Bounded reader lets the consumer flush/cancel even if stdout goes quiet."""
        lines = queue.Queue(maxsize=128)
        stopped = threading.Event()

        def put(value):
            while not stopped.is_set():
                try:
                    lines.put(value, timeout=0.1)
                    return
                except queue.Full:
                    pass

        def read():
            try:
                for line in stream:
                    if stopped.is_set():
                        break
                    put(("line", line))
            except Exception as exc:
                put(("error", exc))
            finally:
                put(("end", None))

        reader = threading.Thread(target=read, name="corespace-stdout", daemon=True)
        job["reader"] = reader
        reader.start()
        try:
            while not job["cancel"].is_set():
                on_idle()
                try:
                    kind, value = lines.get(timeout=0.1)
                except queue.Empty:
                    continue
                if kind == "end":
                    return
                if kind == "error":
                    raise value
                yield value
        finally:
            stopped.set()

    def _consume_stream(
        self,
        scan_id: str,
        root_path: str,
        stream,
        source: str,
        job: Dict[str, Any],
        flush,
        buffered,
    ) -> Tuple[int, Optional[Dict[str, Any]], int, int, int, int]:
        root_seen = False
        saw_done = None
        exit_code = 0
        actual_files = 0
        actual_dirs = 0
        actual_errors = 0
        actual_skips = 0
        pending_paths = {}
        directory_cache = OrderedDict()
        last_flush = time.monotonic()

        def flush_batch():
            nonlocal last_flush
            flush()
            pending_paths.clear()
            last_flush = time.monotonic()

        def flush_due():
            if buffered and time.monotonic() - last_flush >= 1:
                flush_batch()

        def remember_directory(path: str) -> None:
            directory_cache[path] = True
            directory_cache.move_to_end(path)
            while len(directory_cache) > 1024:
                directory_cache.popitem(last=False)

        for line_number, raw_line in enumerate(self._stream_lines(stream, job, flush_due), 1):
            if job["cancel"].is_set():
                break
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except (json.JSONDecodeError, TypeError):
                buffered.append(self._issue_record("", "INVALID_JSON", f"ข้อมูลบรรทัด {line_number} ไม่ใช่ JSON", "error"))
                if len(buffered) >= 128:
                    flush_batch()
                continue
            if not isinstance(record, dict):
                buffered.append(self._issue_record("", "INVALID_RECORD", f"ข้อมูลบรรทัด {line_number} ไม่ใช่ object", "error"))
                if len(buffered) >= 128:
                    flush_batch()
                continue

            record_type = record.get("type")
            if saw_done is not None:
                buffered.append(self._issue_record("", "DATA_AFTER_DONE", "มีข้อมูลต่อจาก record done", "error"))
                if len(buffered) >= 128:
                    flush_batch()
                continue
            if record_type == "entry":
                try:
                    entry = self._validate_entry(record, source)
                    rel = entry["relativePath"]
                    if rel in pending_paths:
                        raise ValueError("พบ relativePath ซ้ำ")
                    parent = entry["parentRelativePath"]
                    if parent is not None:
                        parent_kind = pending_paths.get(parent)
                        if parent_kind is None and parent in directory_cache:
                            parent_kind = "directory"
                        if parent_kind is None and parent not in directory_cache:
                            parent_entry = self.store.get_entry(scan_id, parent)
                            parent_kind = parent_entry["kind"] if parent_entry else None
                            if parent_kind == "directory":
                                remember_directory(parent)
                        if parent_kind != "directory":
                            raise ValueError("ต้องส่งรายการโฟลเดอร์แม่ก่อนรายการข้างใน")
                    if source == "wsl" and entry["kind"] == "file":
                        absolute = self._windows_path_for_entry(root_path, rel)
                        allocated = get_allocated_file_size(absolute)
                        entry["allocatedBytes"] = allocated
                        if allocated is None:
                            entry["partial"] = True
                            buffered.append(self._issue_record(rel, "ALLOCATED_SIZE_UNKNOWN", "Windows อ่านพื้นที่ที่ไฟล์ใช้บนดิสก์ไม่ได้", "error"))
                    elif source == "sample" and entry["kind"] == "file":
                        entry["allocatedBytes"] = record.get("allocatedBytes")
                    buffered.append(dict(entry, type="entry"))
                    pending_paths[rel] = entry["kind"]
                    if entry["kind"] == "directory":
                        remember_directory(rel)
                    if rel == "":
                        root_seen = True
                        flush_batch()
                    if entry["kind"] == "file":
                        actual_files += 1
                    elif entry["kind"] == "directory":
                        actual_dirs += 1
                except ValueError as exc:
                    buffered.append(self._issue_record("", "INVALID_ENTRY", str(exc), "error"))
            elif record_type == "error":
                actual_errors += 1
                rel = self._safe_issue_path(record.get("relativePath"))
                buffered.append(self._issue_record(rel, str(record.get("code") or "READ_ERROR"), str(record.get("message") or "อ่านรายการนี้ไม่ได้"), "error"))
            elif record_type == "skipped":
                actual_skips += 1
                rel = self._safe_issue_path(record.get("relativePath"))
                buffered.append(self._issue_record(rel, str(record.get("reason") or "SKIPPED"), "ข้ามรายการนี้", "skipped"))
            elif record_type == "done":
                try:
                    saw_done = self._validate_done(record)
                except ValueError as exc:
                    buffered.append(self._issue_record("", "INVALID_DONE", str(exc), "error"))
            else:
                buffered.append(self._issue_record("", "UNKNOWN_RECORD", "พบข้อมูลชนิดที่ไม่รู้จัก", "error"))

            if len(buffered) >= 128:
                flush_batch()

        if not root_seen:
            buffered.append(self._issue_record("", "ROOT_MISSING", "ข้อมูลไม่มีรายการโฟลเดอร์เริ่มต้น", "error"))
        flush_batch()
        return exit_code, saw_done, actual_files, actual_dirs, actual_errors, actual_skips

    @staticmethod
    def _issue_record(path: str, code: str, message: str, issue_type: str) -> Dict[str, Any]:
        return {
            "type": "issue",
            "relativePath": path,
            "code": code[:100],
            "message": message[:1000],
            "issueType": issue_type,
        }

    @staticmethod
    def _safe_issue_path(value: Any) -> str:
        if isinstance(value, str) and "\x00" not in value and not value.startswith("/") and ".." not in value.split("/"):
            return value.replace("\\", "/")
        return ""

    @classmethod
    def _validate_entry(
        cls,
        record: Dict[str, Any],
        source: str,
    ) -> Dict[str, Any]:
        rel = record.get("relativePath")
        parent = record.get("parentRelativePath")
        name = record.get("name")
        kind = record.get("kind")
        logical = record.get("logicalBytes")
        if not isinstance(rel, str) or "\x00" in rel or "\\" in rel:
            raise ValueError("relativePath ต้องเป็นข้อความที่ใช้ / คั่น")
        if rel.startswith("/") or any(part in {".", ".."} for part in rel.split("/") if part):
            raise ValueError("relativePath ต้องไม่ออกนอกโฟลเดอร์ที่เลือก")
        if not isinstance(name, str) or not name or "\x00" in name or "/" in name or "\\" in name:
            raise ValueError("name ต้องเป็นชื่อไฟล์หรือโฟลเดอร์หนึ่งรายการ")
        if kind not in {"file", "directory", "link"}:
            raise ValueError("kind ต้องเป็น file, directory หรือ link")
        if isinstance(logical, bool) or not isinstance(logical, int) or logical < 0 or logical > 0x7FFFFFFFFFFFFFFF:
            raise ValueError("logicalBytes ต้องเป็นจำนวนเต็มตั้งแต่ศูนย์")
        if kind != "file" and logical != 0:
            raise ValueError("logicalBytes ของ directory และ link ต้องเป็นศูนย์")
        if rel == "":
            if parent is not None or kind != "directory":
                raise ValueError("รายการเริ่มต้นต้องเป็น directory")
        else:
            expected_parent = rel.rpartition("/")[0]
            if parent != expected_parent:
                raise ValueError("parentRelativePath ไม่ตรงกับ relativePath")
            if "//" in rel or rel.startswith("./"):
                raise ValueError("relativePath มีส่วนว่างหรือจุดที่ไม่จำเป็น")
            if name != rel.rsplit("/", 1)[-1]:
                raise ValueError("name ไม่ตรงกับ relativePath")
            if not expected_parent and parent != "":
                raise ValueError("รายการใน root ต้องมี parentRelativePath เป็นข้อความว่าง")
        entry = {
            "relativePath": rel,
            "parentRelativePath": parent,
            "name": name,
            "kind": kind,
            "logicalBytes": 0 if kind != "file" else logical,
        }
        if source == "sample" and kind == "file":
            allocated = record.get("allocatedBytes")
            if allocated is not None and (
                isinstance(allocated, bool)
                or not isinstance(allocated, int)
                or allocated < 0
                or allocated > 0x7FFFFFFFFFFFFFFF
            ):
                raise ValueError("allocatedBytes ของตัวอย่างต้องเป็นจำนวนเต็มหรือ null")
            entry["allocatedBytes"] = allocated
        if source == "sample" and kind == "directory":
            entry["allocatedBytes"] = 0
        if source == "sample" and kind == "link":
            entry["allocatedBytes"] = None
        return entry

    @staticmethod
    def _validate_done(record: Dict[str, Any]) -> Dict[str, Any]:
        counts = {}
        for key in ("fileCount", "directoryCount", "errorCount", "skippedCount"):
            value = record.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{key} ต้องเป็นจำนวนเต็มตั้งแต่ศูนย์")
            counts[key] = value
        complete = record.get("complete")
        if not isinstance(complete, bool):
            raise ValueError("complete ต้องเป็น true หรือ false")
        counts["complete"] = complete
        return counts

    @staticmethod
    def _windows_path_for_entry(root_path: str, relative_path: str) -> str:
        if any(":" in part for part in relative_path.split("/")):
            raise ValueError("relativePath มีอักขระไดรฟ์ที่ไม่อนุญาต")
        path = os.path.abspath(os.path.join(root_path, *relative_path.split("/")))
        try:
            if ntpath.commonpath([ntpath.normcase(root_path), ntpath.normcase(path)]) != ntpath.normcase(root_path):
                raise ValueError("รายการที่ C ส่งมาอยู่นอกโฟลเดอร์ที่เลือก")
        except ValueError:
            raise ValueError("รายการที่ C ส่งมาอยู่นอกโฟลเดอร์ที่เลือก")
        return path

    def _wsl_path(self, windows_path: str, job=None) -> str:
        process = subprocess.Popen(
            [self.wsl_executable, "-d", self.wsl_distro, "--exec", "wslpath", "-a", windows_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        deadline = time.monotonic() + 15
        try:
            while True:
                if job and job["cancel"].is_set():
                    raise ScanError(503, "START_CANCELLED", "ยกเลิกระหว่างเตรียม WSL")
                if time.monotonic() >= deadline:
                    raise ScanError(503, "WSL_PATH_TIMEOUT", "WSL ไม่ตอบกลับภายในเวลาที่กำหนด")
                try:
                    stdout, stderr = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=2)
        if process.returncode != 0:
            raise ScanError(503, "WSL_PATH_FAILED", (stderr or "แปลงตำแหน่งโฟลเดอร์ไม่สำเร็จ").strip()[:500])
        mapped = stdout.strip()
        if not mapped.startswith("/mnt/"):
            raise ScanError(400, "WINDOWS_DRIVE_NOT_MOUNTED", "WSL เข้าถึงไดรฟ์ Windows นี้ไม่ได้")
        return mapped

    def _start_wsl_process(self, root_path: str, job: Dict[str, Any]):
        scanner = self.scanner_wsl_path
        if not scanner.startswith("/") or "\n" in scanner or "\r" in scanner:
            raise ScanError(503, "SCANNER_PATH_INVALID", "ตำแหน่งโปรแกรม C ใน WSL ต้องเป็น path เต็ม")
        wsl_root = self._wsl_path(root_path, job)
        fd, pid_file = tempfile.mkstemp(prefix="corespace-", suffix=".pid")
        os.close(fd)
        try:
            wsl_pid_file = self._wsl_path(pid_file, job)
        except Exception:
            try:
                os.unlink(pid_file)
            except OSError:
                pass
            raise
        shell_script = 'printf "%s" "$$" > "$1"; shift; exec "$@"'
        command = [
            self.wsl_executable, "-d", self.wsl_distro, "--exec", "sh", "-c", shell_script,
            "corespace-launcher", wsl_pid_file, scanner,
            "--root", wsl_root, "--ndjson",
        ]
        try:
            if job["cancel"].is_set():
                raise ScanError(503, "START_CANCELLED", "ยกเลิกก่อนเรียกโปรแกรม")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception:
            try:
                os.unlink(pid_file)
            except OSError:
                pass
            raise
        return process, pid_file

    def _read_pid(self, process, pid_file: str, job: Dict[str, Any]) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with open(pid_file, "r", encoding="ascii") as handle:
                    value = handle.read().strip()
                if value.isdigit() and int(value) > 1:
                    job["pid"] = int(value)
                    return
            except OSError:
                pass
            if process.poll() is not None:
                break
            time.sleep(0.05)
        raise ScanError(503, "SCANNER_PID_MISSING", "อ่านรหัสโปรแกรมใน Ubuntu ไม่ได้ จึงยืนยันการหยุดไม่ได้")

    @staticmethod
    def _drain_stderr(stream, chunks) -> None:
        if stream is None:
            return
        try:
            for line in stream:
                chunks.append(line[:1000])
                while sum(map(len, chunks)) > 8000:
                    chunks.pop(0)
        except Exception:
            pass
