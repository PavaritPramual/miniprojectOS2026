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
from urllib.parse import urlparse

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

PORT = 8080

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
        else:
            self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/scan":
            self._handle_scan(payload)
        elif path == "/api/reveal":
            self._handle_reveal(payload)
        else:
            self.send_error(404, "Endpoint not found")

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
        drives = get_system_drives()
        self._send_json(drives)

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

        file_path = payload.get("path")
        if not file_path or not os.path.exists(file_path):
            self._send_json({"detail": "File not found"}, status=404)
            return

        # Windows Explorer reveal command
        norm_path = os.path.normpath(file_path)
        try:
            subprocess.Popen(["explorer", f"/select,{norm_path}"])
            self._send_json({"status": "revealed", "path": norm_path})
        except Exception as e:
            self._send_json({"detail": str(e)}, status=500)


def run_server():
    server_address = ("", PORT)
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
        httpd.server_close()


if __name__ == "__main__":
    run_server()
