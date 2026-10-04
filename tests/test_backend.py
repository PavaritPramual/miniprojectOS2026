"""Repeatable backend checks; databases and files are isolated in temporary folders."""
import io
import json
import os
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.scan_manager import ScanManager, ScanError
from backend.scan_store import ScanStore
from backend.allocated_size import get_allocated_file_size
from tools.generate_examples import entry, demo_records


def finish(records, errors=0, skipped=0):
    return records + [{"type": "done", "fileCount": sum(r.get("kind") == "file" for r in records),
                       "directoryCount": sum(r.get("kind") == "directory" for r in records),
                       "errorCount": errors, "skippedCount": skipped,
                       "complete": not (errors or skipped)}]


def wait_finished(manager, scan_id, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = manager.get_status(scan_id)
        if status["state"] not in {"queued", "running", "cancelling"}:
            return status
        time.sleep(0.02)
    raise AssertionError("scan did not finish")


class BackendCase(unittest.TestCase):
    def setUp(self):
        temp_base = Path(__file__).resolve().parents[1] / "fixtures" / "generated" / "test-runs"
        temp_base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_base)
        self.root = Path(self.temp.name)
        self.store = ScanStore(str(self.root / "test.sqlite3"))
        self.manager = ScanManager(self.store)

    def tearDown(self):
        self.manager.shutdown()
        self.temp.cleanup()

    def sample(self, records):
        path = self.root / "records.ndjson"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) if not isinstance(r, str) else r for r in records), encoding="utf-8")
        self.manager.sample_path = str(path)
        scan_id = self.manager.start_scan({"path": str(self.root), "source": "sample"})["id"]
        return scan_id, wait_finished(self.manager, scan_id)


class BackendTests(BackendCase):
    def test_130_and_10000_files_cross_batches(self):
        for count in (130, 10000):
            with self.subTest(count=count):
                records = finish([entry("", "directory")] + [entry(f"f{i:05d}", "file", 1) for i in range(count)])
                scan_id, status = self.sample(records)
                self.assertEqual((status["state"], status["fileCount"], status["errorCount"]), ("completed", count, 0))
                paths = []
                for offset in range(0, count, 50):
                    paths.extend(i["relativePath"] for i in self.manager.get_children(scan_id, "", offset, 50)["items"])
                self.assertEqual(len(set(paths)), count)
                self.assertEqual(len(paths), count)

    def test_evicted_parent_found_in_database(self):
        records = [entry("", "directory")]
        records += [entry(f"dir{i:04d}", "directory") for i in range(1100)]
        records += [entry("dir0000/late.txt", "file", 7)]
        scan_id, status = self.sample(finish(records))
        self.assertEqual((status["state"], status["directoryCount"], status["fileCount"]), ("completed", 1101, 1))
        self.assertEqual(self.store.get_folder(scan_id, "dir0000")["logicalBytes"], 7)

    def test_demo_pages_names_depth_empty_and_sizes(self):
        scan_id, status = self.sample(demo_records())
        self.assertEqual((status["fileCount"], status["directoryCount"]), (64, 13))
        first = self.manager.get_children(scan_id, "many", 0, 50)
        second = self.manager.get_children(scan_id, "many", 50, 50)
        self.assertEqual((len(first["items"]), len(second["items"])), (50, 10))
        self.assertEqual(len({i["relativePath"] for i in first["items"] + second["items"]}), 60)
        self.assertEqual(self.manager.get_children(scan_id, "empty", 0, 50)["folder"]["allocatedBytes"], 0)
        self.assertIsNotNone(self.store.get_entry(scan_id, "ชื่อ ไทย/รายงาน 1.txt"))
        deep = "depth/" + "/".join(f"level-{i:02d}" for i in range(1, 9)) + "/leaf.txt"
        self.assertIsNotNone(self.store.get_entry(scan_id, deep))
        root = self.manager.get_children(scan_id, "", 0, 50)
        self.assertEqual(root["items"][0]["relativePath"], "large.bin")
        self.assertEqual(root["folder"]["logicalBytes"], 1048645)

    def test_invalid_duplicate_missing_done_and_bad_counts(self):
        cases = [([entry("", "directory"), "not json"], "INVALID_JSON"),
                 ([entry("", "directory")], "MISSING_DONE"),
                 (finish([entry("", "directory"), entry("a", "file", 1)] + [entry(f"b{i}", "file", 1) for i in range(127)] + [entry("a", "file", 1)]), "DUPLICATE_ENTRY"),
                 ([entry("", "directory"), {"type":"done","fileCount":9,"directoryCount":1,"errorCount":0,"skippedCount":0,"complete":True}], "COUNT_MISMATCH")]
        for records, code in cases:
            with self.subTest(code=code):
                scan_id, status = self.sample(records)
                self.assertEqual(status["state"], "partial")
                codes = {i["code"] for i in self.manager.get_issues(scan_id, 0, 50)["items"]}
                self.assertIn(code, codes)

    def test_unknown_allocation_and_issues_propagate(self):
        unknown = dict(entry("a", "file", 5), allocatedBytes=None)
        records = [entry("", "directory"), unknown, entry("link", "link"),
                   {"type":"skipped","relativePath":"link","reason":"symbolic_link"},
                   {"type":"error","relativePath":"blocked","code":"ACCESS_DENIED","message":"denied"}]
        scan_id, status = self.sample(finish(records, errors=1, skipped=1))
        self.assertTrue(status["partial"])
        result = self.manager.get_children(scan_id, "", 0, 50)
        self.assertIsNone(result["folder"]["allocatedBytes"])
        self.assertTrue(result["folder"]["partial"])
        self.assertIsNone(next(i for i in result["items"] if i["name"] == "a")["allocatedBytes"])
        self.assertEqual(self.manager.get_issues(scan_id, 0, 50)["totalIssues"], 2)

    def test_flush_when_producer_is_silent_and_active_order(self):
        self.store.create_scan("slow", str(self.root), "sample", False)
        self.store.set_state("slow", "running")
        sent = threading.Event()
        release = threading.Event()
        def stream():
            for r in [entry("", "directory"), entry("z", "file", 1), entry("a", "file", 5000)]:
                yield json.dumps(r)
            sent.set()
            release.wait(5)
        job = {"cancel":threading.Event()}
        buffer = []
        def flush(): self.store.add_records("slow", buffer); buffer.clear()
        thread = threading.Thread(target=self.manager._consume_stream, args=("slow", str(self.root), stream(), "sample", job, flush, buffer))
        thread.start()
        try:
            self.assertTrue(sent.wait(2))
            deadline = time.monotonic()+2
            while self.store.get_scan("slow")["file_count"] != 2 and time.monotonic()<deadline: time.sleep(0.02)
            self.assertIsNotNone(self.store.get_folder("slow", ""))
            page = self.manager.get_children("slow", "", 0, 50)
            self.assertEqual([i["name"] for i in page["items"]], ["z", "a"])
            self.assertIsNone(page["folder"]["logicalBytes"])
        finally:
            job["cancel"].set(); release.set(); thread.join(3)
        self.store.finish_scan("slow", "completed")
        self.assertEqual([i["name"] for i in self.manager.get_children("slow", "", 0, 50)["items"]], ["a", "z"])

    def test_latest_real_retention_restart_and_recovery(self):
        for scan_id, source in (("real", "wsl"), ("mock", "sample")):
            self.store.create_scan(scan_id, r"D:\demo", source, False)
            self.store.add_entry(scan_id, entry("", "directory"))
            self.store.finish_scan(scan_id, "completed")
        self.assertEqual(self.store.latest_successful_scan("d:\\DEMO\\"), "real")
        self.assertIsNotNone(self.store.get_scan("real"))
        self.store.create_scan("abandoned", r"D:\other", "wsl", False)
        self.store.add_entry("abandoned", entry("", "directory"))
        restarted = ScanStore(self.store.database_path)
        self.assertEqual(restarted.latest_successful_scan(r"D:\demo"), "real")
        self.assertEqual(restarted.get_scan("abandoned")["state"], "failed")
        self.assertTrue(restarted.get_folder("abandoned", "")["partial"])

    def test_whole_drive_guard_and_no_automatic_sample(self):
        self.store.create_scan("whole", "D:\\", "wsl", True)
        self.manager.scanner_wsl_path = "/scanner"
        with patch.object(self.manager, "_validate_windows_folder", return_value="D:\\"):
            with self.assertRaises(ScanError) as caught: self.manager.start_scan({"path":"D:\\"})
        self.assertEqual(caught.exception.status, 409)
        self.manager.scanner_wsl_path = ""
        with self.assertRaises(ScanError) as caught: self.manager.start_scan({"path":str(self.root)})
        self.assertEqual(caught.exception.code, "SCANNER_NOT_CONFIGURED")

    @unittest.skipUnless(os.name == "nt", "Windows measurement")
    def test_windows_measurement_unknown_and_zero(self):
        self.assertIsNone(get_allocated_file_size(str(self.root / "missing")))
        file = self.root / "zero"; file.touch()
        self.assertEqual(get_allocated_file_size(str(file)), 0)

    def test_unconfirmed_stop_is_failed(self):
        records = io.StringIO(json.dumps(entry("", "directory")) + "\n")
        process = unittest.mock.Mock()
        process.stdout = records; process.stderr = io.StringIO(""); process.returncode = 1
        process.poll.return_value = 1
        job = {"cancel":threading.Event(), "cancel_at":None, "process":None, "pid":None}
        self.store.create_scan("unconfirmed", str(self.root), "wsl", False)
        def read_pid(*args): job["cancel"].set()
        with patch.object(self.manager, "_start_wsl_process", return_value=(process, None)), patch.object(self.manager, "_read_pid", side_effect=read_pid), patch.object(self.manager, "_stop_process", return_value=False):
            self.manager._run_scan("unconfirmed", str(self.root), "wsl", job)
        self.assertEqual(self.manager.get_status("unconfirmed")["state"], "failed")

    def test_cancel_queued_job_then_restart(self):
        release = threading.Event()
        blockers = [self.manager._executor.submit(release.wait, 5) for _ in range(4)]
        try:
            scan_id = self.manager.start_scan({"source":"sample"})["id"]
            self.assertEqual(self.manager.get_status(scan_id)["state"], "queued")
            self.assertEqual(self.manager.cancel_scan(scan_id)[0], 202)
        finally:
            release.set()
        self.assertEqual(wait_finished(self.manager, scan_id)["state"], "cancelled")
        restarted = self.manager.start_scan({"source":"sample"})["id"]
        self.assertEqual(wait_finished(self.manager, restarted)["state"], "completed")

    def test_committed_examples_match_the_receiver(self):
        base = Path(__file__).resolve().parents[1] / "docs/examples"
        records = [json.loads(line) for line in (base / "scan.ndjson").read_text(encoding="utf-8").splitlines()]
        examples = json.loads((base / "api.json").read_text(encoding="utf-8"))
        scan_id, status = self.sample(records)
        self.assertEqual(status["fileCount"], examples["completedStatus"]["fileCount"])
        for offset, key in ((0, "childrenPage1"), (50, "childrenPage2")):
            actual = self.manager.get_children(scan_id, "many", offset, 50)
            actual["scanId"] = examples[key]["scanId"]
            self.assertEqual(actual, examples[key])

    def test_cancel_cannot_overwrite_finished_state(self):
        self.store.create_scan("finished", str(self.root), "sample", False)
        self.store.finish_scan("finished", "completed")
        self.assertFalse(self.store.request_cancel("finished"))
        self.assertEqual(self.store.get_scan("finished")["state"], "completed")


if __name__ == "__main__": unittest.main()
