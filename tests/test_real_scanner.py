"""Opt-in Windows HTTP integration with the group's compiled C scanner, not a mock."""
import http.client
import http.server
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import unittest
from urllib.parse import urlencode

import main
from backend.scan_manager import ScanManager
from backend.scan_store import ScanStore
from tests.test_backend import BackendCase, wait_finished


def standard_file_allocation(path):
    """Independent Windows FILE_STANDARD_INFO reference for ordinary fixture files."""
    class StandardInfo(ctypes.Structure):
        _fields_ = [("allocation", ctypes.c_longlong), ("size", ctypes.c_longlong),
                    ("links", wintypes.DWORD), ("deleted", ctypes.c_ubyte), ("directory", ctypes.c_ubyte)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80, 7, None, 3, 0, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = StandardInfo()
        if not kernel.GetFileInformationByHandleEx(handle, 1, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return info.allocation
    finally:
        kernel.CloseHandle(handle)


@unittest.skipUnless(os.name == "nt" and os.environ.get("CORESPACE_TEST_REAL_C") == "1",
                     "set CORESPACE_TEST_REAL_C=1 and configure the compiled C scanner")
class RealScannerTests(BackendCase):
    def setUp(self):
        super().setUp()
        self.assertTrue(self.manager.scanner_wsl_path, "set CORESPACE_SCANNER_WSL_PATH")
        self.fixture = self.root / "demo"
        script = Path(__file__).resolve().parents[1] / "tools/prepare_demo_fixture.ps1"
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(script), "-Target", str(self.fixture)], check=True, capture_output=True)
        self.previous = main.SCAN_MANAGER
        main.SCAN_MANAGER = self.manager
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), main.CoreSpaceRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(2)
            main.SCAN_MANAGER = self.previous
        super().tearDown()

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, None if body is None else json.dumps(body),
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def scan(self):
        code, start = self.request("POST", "/api/scans", {"path": str(self.fixture)})
        self.assertEqual(code, 202)
        return start["id"], wait_finished(self.manager, start["id"], 30)

    def test_real_files_pages_totals_and_persistence(self):
        scan_id, status = self.scan()
        self.assertEqual((status["state"], status["fileCount"], status["directoryCount"]),
                         ("completed", 64, 13), status)
        self.assertFalse(status["isSample"])
        pages = [self.request("GET", f"/api/scans/{scan_id}/children?parent=many&offset={offset}&limit=50")[1]
                 for offset in (0, 50)]
        self.assertEqual([len(p["items"]) for p in pages], [50, 10])
        self.assertEqual(len({i["relativePath"] for p in pages for i in p["items"]}), 60)
        folder = self.request("GET", f"/api/scans/{scan_id}/children?parent=&limit=50")[1]["folder"]
        self.assertEqual(folder["logicalBytes"], sum(p.stat().st_size for p in self.fixture.rglob("*") if p.is_file()))
        self.assertFalse(folder["partial"])
        self.assertIsNotNone(folder["allocatedBytes"])
        for relative in ("empty", "depth/level-01/level-02/level-03/level-04/level-05/level-06/level-07/level-08", "ชื่อ ไทย"):
            code, page = self.request("GET", f"/api/scans/{scan_id}/children?" + urlencode({"parent": relative}))
            self.assertEqual(code, 200)
            self.assertIsNotNone(page["folder"]["logicalBytes"])
        root_items = self.manager.get_children(scan_id, "", 0, 50)["items"]
        zero = next(i for i in root_items if i["name"] == "zero.bin")
        self.assertEqual((zero["logicalBytes"], zero["allocatedBytes"]), (0, 0))
        for name in ("zero.bin", "large.bin"):
            item = next(i for i in root_items if i["name"] == name)
            self.assertEqual(item["allocatedBytes"], standard_file_allocation(self.fixture / name))
        self.assertEqual(self.request("GET", f"/api/scans/{scan_id}/issues")[1]["items"], [])
        self.manager.shutdown()
        self.manager = ScanManager(ScanStore(str(self.root / "test.sqlite3")))
        main.SCAN_MANAGER = self.manager
        code, latest = self.request("GET", "/api/scans/latest?" + urlencode({"path": str(self.fixture)}))
        self.assertEqual((code, latest["id"], latest["state"]), (200, scan_id, "completed"))

    def test_real_junction_does_not_loop(self):
        junction = self.fixture / "back-to-root"
        command = 'New-Item -ItemType Junction -Path $args[0] -Target $args[1] | Out-Null'
        # Arguments are passed through a script file, never interpolated into shell code.
        script = self.root / "junction.ps1"
        script.write_text(command, encoding="utf-8")
        subprocess.run(["powershell.exe", "-NoProfile", "-File", str(script), str(junction), str(self.fixture)],
                       check=True, capture_output=True)
        try:
            scan_id, status = self.scan()
            self.assertEqual(status["state"], "partial", status)
            self.assertEqual(status["fileCount"], 64)
            self.assertGreater(status["skippedCount"] + status["errorCount"], 0)
            self.assertTrue(self.manager.get_children(scan_id, "", 0, 50)["folder"]["partial"])
            issues = self.request("GET", f"/api/scans/{scan_id}/issues")[1]["items"]
            self.assertTrue(any(i["relativePath"] == "back-to-root" for i in issues), issues)
        finally:
            os.rmdir(junction)  # Remove only the junction, never its target.

    @unittest.skipUnless(os.environ.get("CORESPACE_TEST_DRIVE"), "set CORESPACE_TEST_DRIVE to opt into a real drive scan")
    def test_real_drive_cancel_and_restart(self):
        drive = os.environ["CORESPACE_TEST_DRIVE"]
        code, start = self.request("POST", "/api/scans", {"path": drive})
        self.assertEqual(code, 202)
        scan_id = start["id"]
        try:
            self.assertEqual(self.request("POST", "/api/scans", {"path": drive})[0], 409)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                job = self.manager._jobs.get(scan_id)
                if job and job.get("pid") and self.manager.store.get_folder(scan_id, ""):
                    break
                time.sleep(0.05)
            self.assertTrue(job and job.get("pid"), "C process did not start")
            pid = job["pid"]
            self.assertEqual(self.request("GET", f"/api/scans/{scan_id}/children?parent=&limit=50")[0], 200)
            started = time.monotonic()
            self.assertEqual(self.request("POST", f"/api/scans/{scan_id}/cancel", {})[0], 202)
            self.assertEqual(wait_finished(self.manager, scan_id, 16)["state"], "cancelled")
            self.assertLess(time.monotonic() - started, 15)
            self.assertIs(self.manager._linux_alive(pid), False)
        finally:
            self.manager.cancel_scan(scan_id)
            wait_finished(self.manager, scan_id, 20)
        self.assertEqual(self.scan()[1]["state"], "completed")


if __name__ == "__main__":
    unittest.main()
