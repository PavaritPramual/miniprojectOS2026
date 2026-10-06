"""Actual localhost HTTP checks, with Explorer mocked to avoid opening windows."""
import http.client
import http.server
import json
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

import main
from tests.test_backend import BackendCase, wait_finished
from tools.generate_examples import entry


class ApiTests(BackendCase):
    def setUp(self):
        super().setUp()
        self.previous = main.SCAN_MANAGER
        main.SCAN_MANAGER = self.manager
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), main.CoreSpaceRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)
        main.SCAN_MANAGER = self.previous
        super().tearDown()

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, None if body is None else json.dumps(body), {"Content-Type":"application/json"})
            response = connection.getresponse()
            payload = response.read()
            return response.status, json.loads(payload) if payload and path != "/" else payload
        finally: connection.close()

    def test_api_sample_pages_issues_errors(self):
        self.assertEqual(self.request("GET", "/")[0], 200)
        code, start = self.request("POST", "/api/scans", {"source":"sample","path":str(self.root)})
        self.assertEqual(code, 202)
        scan_id = start["id"]; wait_finished(self.manager, scan_id)
        self.assertEqual(self.request("GET", f"/api/scans/{scan_id}")[1]["fileCount"], 64)
        page1 = self.request("GET", f"/api/scans/{scan_id}/children?parent=many&offset=0&limit=50")[1]
        page2 = self.request("GET", f"/api/scans/{scan_id}/children?parent=many&offset=50&limit=50")[1]
        self.assertEqual((len(page1["items"]), len(page2["items"])), (50, 10))
        self.assertIn("folder", page1)
        self.assertEqual(self.request("GET", f"/api/scans/{scan_id}/issues")[0], 200)
        self.assertEqual(self.request("GET", f"/api/scans/{scan_id}/children?limit=51")[0], 400)
        self.assertEqual(self.request("GET", "/api/scans/absent")[0], 404)
        self.assertEqual(self.request("POST", f"/api/scans/{scan_id}/cancel", {})[0], 409)

    def test_latest_real_and_reveal(self):
        self.store.create_scan("real", str(self.root), "wsl", False)
        self.store.add_records("real", [entry("", "directory"), entry("zero", "file", 0)])
        self.store.finish_scan("real", "completed")
        path = "/api/scans/latest?" + urlencode({"path":str(self.root)})
        code, latest = self.request("GET", path)
        self.assertEqual((code, latest["id"], latest["isSample"]), (200, "real", False))
        self.assertEqual(self.request("GET", "/api/scans/latest?path=D%3A%5Cmissing")[0], 404)
        self.assertEqual(self.request("GET", "/api/scans/latest?path=relative")[0], 400)
        file = self.root / "zero"; file.touch()
        payload = {"scanId":"real","relativePath":"zero"}
        with patch.object(main.subprocess, "Popen") as explorer:
            self.assertEqual(self.request("POST", "/api/reveal", payload)[0], 200)
            explorer.assert_called_once()
        file.unlink()
        self.assertEqual(self.request("POST", "/api/reveal", payload)[0], 404)
        self.assertEqual(self.request("POST", "/api/reveal", {"scanId":"real","relativePath":"../outside"})[0], 404)
        with patch.object(main, "get_system_drives", return_value=[]):
            self.assertEqual(self.request("GET", "/api/drives")[0], 500)

    def test_concurrent_initialization_creates_one_manager(self):
        main.SCAN_MANAGER = None
        calls = []
        def create():
            calls.append(1); time.sleep(0.02); return self.manager
        with patch.object(main, "ScanManager", side_effect=create):
            threads = [threading.Thread(target=main.get_scan_manager) for _ in range(8)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(2)
        self.assertEqual(len(calls), 1)

    def test_root_is_available_while_waiting_for_scanner(self):
        self.store.create_scan("waiting", str(self.root), "wsl", False)
        code, page = self.request("GET", "/api/scans/waiting/children?parent=&limit=50")
        self.assertEqual(code, 200)
        self.assertEqual(page["items"], [])
        self.assertIsNone(page["folder"]["logicalBytes"])
        self.assertIsNone(page["folder"]["allocatedBytes"])
        self.assertEqual(self.request("GET", "/api/scans/waiting/children?parent=absent")[0], 404)
        self.store.finish_scan("waiting", "failed", "scanner did not send root")
        self.assertEqual(self.request("GET", "/api/scans/waiting/children?parent=")[0], 404)

    def test_status_and_cancel_respond_while_producer_is_silent(self):
        release = threading.Event()
        original = self.manager._consume_stream
        def slow(scan_id, root, stream, source, job, flush, buffered):
            def records():
                yield json.dumps(entry("", "directory"))
                yield json.dumps(entry("zero", "file", 0))
                release.wait(5)
            return original(scan_id, root, records(), source, job, flush, buffered)
        try:
            with patch.object(self.manager, "_consume_stream", side_effect=slow):
                code, start = self.request("POST", "/api/scans", {"source":"sample"})
                self.assertEqual(code, 202)
                scan_id = start["id"]
                deadline = time.monotonic()+3
                while not self.store.get_folder(scan_id, "") and time.monotonic()<deadline: time.sleep(0.02)
                started = time.monotonic()
                code, status = self.request("GET", f"/api/scans/{scan_id}")
                self.assertEqual((code, status["state"]), (200, "running"))
                self.assertLess(time.monotonic()-started, 2)
                self.assertEqual(self.request("POST", f"/api/scans/{scan_id}/cancel", {})[0], 202)
                self.assertEqual(wait_finished(self.manager, scan_id)["state"], "cancelled")
        finally: release.set()


if __name__ == "__main__": unittest.main()
