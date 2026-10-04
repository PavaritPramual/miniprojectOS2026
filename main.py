"""
CoreSpace Main Server
OS Mini-Project: Disk Space Visualization
Group: ผู้ก้าวข้ามโชคชะตาด้วยมือของตัวเอง
Members:
1. นายศรัณย์ พาพรชัย (673380515-5)
2. นายปวริศช์ ประมวล (673380278-9)
3. นายธีรเมธ สายคำ (673380273-9)

Architecture: Zero-Dependency Lightweight Client-Server (Pure Python Standard Library)
Serves static UI and REST API for high-performance disk analysis.
"""

import http.server
import json
import os
import subprocess
import sys
import time
import webbrowser
import ntpath
import re
import threading
from urllib.parse import parse_qs, unquote, urlparse

# Ensure safe UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# Add project root to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.win32_api import get_system_drives, get_cluster_size
from backend.scanner import DirectoryScanner
from backend.aggregator import convert_to_treemap_data, convert_to_tree_view_data
from backend.scan_manager import ScanError, ScanManager

PORT = 8080
SCAN_MANAGER = None
SCAN_MANAGER_LOCK = threading.Lock()


def get_scan_manager():
    global SCAN_MANAGER
    with SCAN_MANAGER_LOCK:
        if SCAN_MANAGER is None:
            SCAN_MANAGER = ScanManager()
    return SCAN_MANAGER

class CoreSpaceRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_file(os.path.join(BASE_DIR, "static", "index.html"), "text/html")
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            file_path = os.path.join(BASE_DIR, "static", rel_path)
            content_type = self._get_content_type(file_path)
            self._serve_file(file_path, content_type)
        elif path == "/api/drives":
            self._handle_get_drives()
        elif path.startswith("/api/scans/"):
            self._handle_get_scan_api(parsed)
        else:
            self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        payload = self._read_json_body()
        if payload is None:
            return

        if path == "/api/scans":
            self._handle_start_scan(payload)
        elif path.startswith("/api/scans/") and path.endswith("/cancel"):
            self._handle_cancel_scan(path)
        elif path == "/api/scan":
            self._handle_scan(payload)
        elif path == "/api/reveal":
            self._handle_reveal(payload)
        else:
            self.send_error(404, "Endpoint not found")

    def _read_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_api_error(400, "INVALID_LENGTH", "ขนาดคำขอไม่ถูกต้อง")
            return None
        if content_length < 0 or content_length > 1_000_000:
            self._send_api_error(413, "BODY_TOO_LARGE", "ข้อมูลคำขอมีขนาดใหญ่เกินไป")
            return None
        try:
            body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_api_error(400, "INVALID_JSON", "ข้อมูลคำขอไม่ใช่ JSON ที่ถูกต้อง")
            return None
        if not isinstance(payload, dict):
            self._send_api_error(400, "INVALID_BODY", "ข้อมูลคำขอต้องเป็น object")
            return None
        return payload

    def _send_api_error(self, status: int, code: str, detail: str):
        self._send_json({"code": code, "detail": detail}, status=status)

    @staticmethod
    def _page_arguments(query, limit_default=50):
        try:
            offset = int(query.get("offset", ["0"])[0])
            limit = int(query.get("limit", [str(limit_default)])[0])
        except (TypeError, ValueError, IndexError):
            raise ValueError("offset และ limit ต้องเป็นจำนวนเต็ม")
        if offset < 0 or offset > 0x7FFFFFFFFFFFFFFF or not 1 <= limit <= 50:
            raise ValueError("offset ต้องไม่ติดลบและ limit ต้องอยู่ระหว่าง 1 ถึง 50")
        return offset, limit

    def _handle_start_scan(self, payload):
        try:
            result = get_scan_manager().start_scan(payload)
        except ScanError as exc:
            self._send_api_error(exc.status, exc.code, exc.detail)
            return
        except Exception as exc:
            self._send_api_error(500, "SCAN_START_FAILED", str(exc))
            return
        self._send_json(result, status=202)

    def _handle_get_scan_api(self, parsed):
        if parsed.path == "/api/scans/latest":
            query = parse_qs(parsed.query, keep_blank_values=True)
            root = ntpath.normpath(query.get("path", [""])[0].strip())
            drive, _ = ntpath.splitdrive(root)
            if len(drive) != 2 or drive[1] != ":" or not drive[0].isalpha() or not ntpath.isabs(root):
                self._send_api_error(400, "INVALID_PATH", "ระบุตำแหน่งโฟลเดอร์ในไดรฟ์เครื่องนี้")
                return
            try:
                manager = get_scan_manager()
                scan_id = manager.store.latest_successful_scan(root)
                status = manager.get_status(scan_id) if scan_id else None
            except Exception:
                self._send_api_error(500, "SCAN_READ_FAILED", "อ่านผลสแกนล่าสุดไม่ได้")
                return
            if status is None:
                self._send_api_error(404, "SCAN_NOT_FOUND", "ไม่มีผลสแกนจริงที่บันทึกไว้สำหรับโฟลเดอร์นี้")
            else:
                self._send_json(status)
            return
        match = re.fullmatch(r"/api/scans/([^/]+)(?:/(children|issues))?", parsed.path)
        if not match:
            self._send_api_error(404, "ENDPOINT_NOT_FOUND", "ไม่พบ endpoint นี้")
            return
        scan_id = unquote(match.group(1))
        section = match.group(2)
        try:
            manager = get_scan_manager()
        except Exception:
            self._send_api_error(500, "SCAN_STORE_FAILED", "เปิดที่เก็บผลการสแกนไม่ได้")
            return
        query = parse_qs(parsed.query, keep_blank_values=True)
        if section is None:
            try:
                status = manager.get_status(scan_id)
            except Exception:
                self._send_api_error(500, "SCAN_READ_FAILED", "อ่านสถานะงานสแกนไม่ได้")
                return
            if status is None:
                self._send_api_error(404, "SCAN_NOT_FOUND", "ไม่พบงานสแกน")
            else:
                self._send_json(status)
            return
        try:
            offset, limit = self._page_arguments(query)
        except ValueError as exc:
            self._send_api_error(400, "INVALID_PAGE", str(exc))
            return
        try:
            if section == "children":
                parent = query.get("parent", [""])[0]
                result = manager.get_children(scan_id, parent, offset, limit)
            else:
                result = manager.get_issues(scan_id, offset, limit)
        except Exception:
            self._send_api_error(500, "SCAN_READ_FAILED", "อ่านรายการจากผลสแกนไม่ได้")
            return
        if result is None:
            self._send_api_error(404, "SCAN_OR_FOLDER_NOT_FOUND", "ไม่พบงานหรือโฟลเดอร์ที่ขอ")
            return
        self._send_json(result)

    def _handle_cancel_scan(self, path):
        match = re.fullmatch(r"/api/scans/([^/]+)/cancel", path)
        if not match:
            self._send_api_error(404, "ENDPOINT_NOT_FOUND", "ไม่พบ endpoint นี้")
            return
        try:
            status, body = get_scan_manager().cancel_scan(unquote(match.group(1)))
            self._send_json(body, status=status)
        except Exception:
            self._send_api_error(500, "CANCEL_FAILED", "ส่งคำขอยกเลิกงานสแกนไม่ได้")

    def _serve_file(self, file_path: str, content_type: str):
        if not os.path.exists(file_path):
            self.send_error(404, f"File {file_path} not found")
            return

        with open(file_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _get_content_type(self, path: str) -> str:
        if path.endswith(".css"):
            return "text/css"
        elif path.endswith(".js"):
            return "application/javascript"
        elif path.endswith(".html"):
            return "text/html"
        elif path.endswith(".json"):
            return "application/json"
        elif path.endswith(".svg"):
            return "image/svg+xml"
        return "application/octet-stream"

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_get_drives(self):
        try:
            all_drives = get_system_drives()
            if not all_drives:
                raise OSError("Windows ไม่ส่งรายชื่อไดรฟ์กลับมา")
            if all(d.get("total_bytes", 0) <= 0 for d in all_drives):
                raise OSError("Windows อ่านความจุของไดรฟ์ไม่ได้")
            self._send_json(all_drives)
        except Exception as exc:
            self._send_api_error(500, "DRIVE_LIST_FAILED", str(exc))

    def _handle_scan(self, payload: dict):
        target_path = payload.get("path")
        threads = int(payload.get("threads") or os.cpu_count() or 8)

        if not target_path or not os.path.exists(target_path):
            self._send_json({"detail": f"Path not found: {target_path}"}, status=400)
            return

        scanner = DirectoryScanner(target_path, max_workers=threads)
        start_time = time.perf_counter()
        
        root_node = scanner.scan_concurrent()
        duration = time.perf_counter() - start_time
        
        speed = scanner.scanned_files / duration if duration > 0 else 0

        tree_view_data = convert_to_tree_view_data(root_node)
        cluster_sz = get_cluster_size(target_path)

        response_data = {
            "root_path": target_path,
            "cluster_size": cluster_sz,
            "scan_duration_seconds": round(duration, 3),
            "files_per_second": round(speed, 1),
            "scanned_files": scanner.scanned_files,
            "scanned_folders": scanner.scanned_folders,
            "total_logical_bytes": scanner.total_logical_bytes,
            "total_physical_bytes": scanner.total_physical_bytes,
            "total_slack_bytes": scanner.total_slack_bytes,
            "categories": scanner.categories,
            "largest_files": scanner.largest_files,
            "tree_view": tree_view_data,
        }

        self._send_json(response_data)


    def _handle_reveal(self, payload: dict):
        scan_id = payload.get("scanId")
        relative_path = payload.get("relativePath")
        if scan_id is not None or relative_path is not None:
            if not isinstance(scan_id, str) or not isinstance(relative_path, str):
                self._send_api_error(400, "INVALID_REVEAL_PATH", "ข้อมูลตำแหน่งไม่ถูกต้อง")
                return
            try:
                manager = get_scan_manager()
                scan = manager.store.get_scan(scan_id)
                entry = manager.store.get_entry(scan_id, relative_path)
            except Exception:
                self._send_api_error(500, "REVEAL_LOOKUP_FAILED", "อ่านตำแหน่งจากผลสแกนไม่ได้")
                return
            if scan is None or entry is None or entry["kind"] == "link":
                self._send_api_error(404, "SCAN_ENTRY_NOT_FOUND", "ไม่พบไฟล์นี้ในผลสแกน")
                return
            norm_path = os.path.abspath(os.path.join(scan["root_path"], *relative_path.split("/")))
            try:
                if ntpath.commonpath([ntpath.normcase(scan["root_path"]), ntpath.normcase(norm_path)]) != ntpath.normcase(scan["root_path"]):
                    self._send_api_error(400, "PATH_OUTSIDE_SCAN", "ตำแหน่งนี้อยู่นอกโฟลเดอร์ที่สแกน")
                    return
            except ValueError:
                self._send_api_error(400, "PATH_OUTSIDE_SCAN", "ตำแหน่งนี้อยู่นอกโฟลเดอร์ที่สแกน")
                return
            if not os.path.exists(norm_path):
                self._send_api_error(404, "PATH_NOT_FOUND", "รายการนี้ถูกย้ายหรือลบไปแล้ว")
                return
        else:
            # Keep path-based Reveal available to the existing prototype.
            file_path = payload.get("path")
            if not file_path or not os.path.exists(file_path):
                self._send_api_error(404, "PATH_NOT_FOUND", "ไม่พบไฟล์หรือโฟลเดอร์")
                return
            norm_path = os.path.normpath(file_path)
        try:
            if os.path.isdir(norm_path):
                subprocess.Popen(["explorer", norm_path])
            else:
                subprocess.Popen(["explorer", f"/select,{norm_path}"])
            self._send_json({"status": "revealed", "path": norm_path})
        except Exception as e:
            self._send_api_error(500, "REVEAL_FAILED", str(e))


def run_server():
    server_address = ("127.0.0.1", PORT)
    httpd = http.server.ThreadingHTTPServer(server_address, CoreSpaceRequestHandler)

    print("=" * 65)
    print("🚀  CoreSpace | OS Storage Analyzer")
    print("    กลุ่ม: ผู้ก้าวข้ามโชคชะตาด้วยมือของตัวเอง (OS Mini-Project)")
    print("    สมาชิก:")
    print("    1. นายศรัณย์ พาพรชัย (673380515-5)")
    print("    2. นายปวริศช์ ประมวล (673380278-9)")
    print("    3. นายธีรเมธ สายคำ (673380273-9)")
    print("=" * 65)
    print(f"📡  Server listening at: http://localhost:{PORT}")
    print("    Scanner source: WSL Ubuntu (explicit sample mode available through /api/scans)")
    print("=" * 65)

    # Open browser automatically
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        httpd.server_close()
        if SCAN_MANAGER is not None:
            SCAN_MANAGER.shutdown()


if __name__ == "__main__":
    run_server()
