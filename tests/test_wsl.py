"""Opt-in real WSL process checks: CORESPACE_TEST_WSL=1 python -m unittest tests.test_wsl -v."""
import os
import json
import sys
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_backend import BackendCase, wait_finished


@unittest.skipUnless(os.name == "nt" and os.environ.get("CORESPACE_TEST_WSL") == "1", "set CORESPACE_TEST_WSL=1 to launch Ubuntu test processes")
class WslTests(BackendCase):
    def setUp(self):
        super().setUp()
        (self.root / "zero.bin").touch()
        self.captured_job = None
        original = self.manager._read_pid
        def capture(process, pid_file, job):
            original(process, pid_file, job)
            self.captured_job = job
        self.manager._read_pid = capture

    def configure(self, mode):
        script = Path(__file__).with_name("wsl_mock.py").resolve()
        mapped_script = self.manager._wsl_path(str(script))
        wrapper = self.root / ("mock-" + mode)
        wrapper.write_text('#!/bin/sh\nexec /usr/bin/python3 "' + mapped_script + '" --mode ' + mode + ' "$@"\n', encoding="utf-8", newline="\n")
        mapped_wrapper = self.manager._wsl_path(str(wrapper))
        subprocess.run(["wsl", "-d", "Ubuntu", "--exec", "chmod", "+x", mapped_wrapper], check=True, timeout=10)
        self.manager.scanner_wsl_path = mapped_wrapper

    def wait_root(self, scan_id):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self.store.get_folder(scan_id, ""):
                return
            status = self.manager.get_status(scan_id)
            if status["state"] in {"failed", "partial"}:
                self.fail(str(status))
            time.sleep(0.05)
        self.fail("root never appeared")

    def test_wsl_demo_bridge_real_windows_allocation(self):
        self.configure("demo")
        fixture = Path(__file__).resolve().parents[1] / "fixtures/generated/demo"
        self.assertTrue(fixture.is_dir(), "create fixture with tools/prepare_demo_fixture.ps1")
        scan_id = self.manager.start_scan({"path":str(fixture)})["id"]
        status = wait_finished(self.manager, scan_id, 20)
        self.assertEqual((status["state"], status["fileCount"], status["directoryCount"]), ("completed", 64, 13))
        self.assertFalse(status["isSample"])
        self.assertEqual(len(self.manager.get_children(scan_id, "many", 50, 50)["items"]), 10)
        self.assertIs(self.manager._linux_alive(self.captured_job["pid"]), False)

    def test_wsl_cancel_slow_silent_and_ignore_term(self):
        for mode in ("slow", "silent", "ignore-term"):
            with self.subTest(mode=mode):
                self.configure(mode)
                scan_id = self.manager.start_scan({"path":str(self.root)})["id"]
                self.wait_root(scan_id)
                job = self.captured_job
                started = time.monotonic()
                self.assertEqual(self.manager.cancel_scan(scan_id)[0], 202)
                status = wait_finished(self.manager, scan_id, 16)
                self.assertEqual(status["state"], "cancelled")
                self.assertLess(time.monotonic() - started, 15)
                self.assertIs(self.manager._linux_alive(job["pid"]), False)
        # A following real process can still start after cancellation.
        self.configure("crash")
        restarted = self.manager.start_scan({"path":str(self.root)})["id"]
        status = wait_finished(self.manager, restarted, 20)
        self.assertEqual(status["state"], "partial")
        codes = {i["code"] for i in self.manager.get_issues(restarted, 0, 50)["items"]}
        self.assertTrue({"MISSING_DONE", "SCANNER_EXIT"} <= codes)

    def test_wsl_stop_on_python_failure(self):
        self.configure("ignore-term")
        with patch.object(self.manager, "_consume_stream", side_effect=RuntimeError("test receiver failure")):
            scan_id = self.manager.start_scan({"path":str(self.root)})["id"]
            status = wait_finished(self.manager, scan_id, 20)
        self.assertEqual(status["state"], "failed")
        self.assertIs(self.manager._linux_alive(self.captured_job["pid"]), False)

    def test_benchmark_tool_with_labelled_mock(self):
        self.configure("demo")
        project = Path(__file__).resolve().parents[1]
        output = self.root / "benchmark-mock.json"
        result = subprocess.run(
            [sys.executable, str(project / "tools/benchmark_backend.py"),
             "--path", str(project / "fixtures/generated/demo"),
             "--scanner", self.manager.scanner_wsl_path, "--runs", "3", "--test-only", "--output", str(output)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(report["testOnly"])
        self.assertEqual(len(report["runs"]), 6)
        self.assertTrue(report["comparableFileCounts"])
        for run in report["runs"]:
            self.assertGreater(run["pythonPeakWorkingSetBytes"], 0)
            if run["engine"] == "new":
                self.assertGreater(run["cPeakRssBytes"], 0)
                self.assertEqual(run["state"], "completed")


if __name__ == "__main__": unittest.main()
