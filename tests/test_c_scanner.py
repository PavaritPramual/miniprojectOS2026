"""Builds scanner/diskviz-scan and checks its NDJSON against docs/CONTRACT.md.

Linux only (run inside Ubuntu/WSL); skipped on Windows or when no C compiler exists.
Every record is also passed through the real validators in backend.scan_manager.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from backend.scan_manager import ScanManager

REPO = Path(__file__).resolve().parents[1]
SCANNER_DIR = REPO / "scanner"
FIXTURE_SCRIPT = REPO / "tools" / "make_demo_fixture.sh"
SAMPLE = REPO / "docs" / "examples" / "scan.ndjson"

CAN_RUN = (sys.platform.startswith("linux") and shutil.which("make")
           and (shutil.which("cc") or shutil.which("gcc")) and shutil.which("sh"))


def run(binary, root, *extra, prefix=(), timeout=60, max_fds=None):
    """Runs the scanner; returns (exit code, list of parsed records, stdout text, stderr text)."""
    cmd = list(prefix) + [str(binary), "--root", str(root), "--ndjson", *extra]
    limit = None
    if max_fds:
        import resource  # POSIX only: importing it at the top would break `unittest discover` on Windows

        def limit():
            resource.setrlimit(resource.RLIMIT_NOFILE, (max_fds, max_fds))

    result = subprocess.run(cmd, capture_output=True, timeout=timeout, preexec_fn=limit)
    stdout = result.stdout.decode("utf-8")  # strict: the stream must be valid UTF-8
    lines = stdout.split("\n")
    assert lines[-1] == "", "stdout must end with a newline"
    records = [json.loads(line) for line in lines[:-1]]
    return result.returncode, records, stdout, result.stderr.decode("utf-8", "replace")


@unittest.skipUnless(CAN_RUN, "needs Linux with make and a C compiler (run inside Ubuntu/WSL)")
class CScannerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="corespace-c-")
        cls.base = Path(cls.temp.name)
        os.chmod(cls.base, 0o755)  # lets the "nobody" user in when the tests run as root
        cls.binary = cls.base / "diskviz-scan"
        build = subprocess.run(["make", "-C", str(SCANNER_DIR), f"TARGET={cls.binary}"],
                               capture_output=True, text=True)
        if build.returncode != 0:
            raise AssertionError("build failed:\n" + build.stdout + build.stderr)
        cls.demo = cls.base / "demo"
        subprocess.run(["sh", str(FIXTURE_SCRIPT), str(cls.demo)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        for path in cls.base.rglob("*"):  # no-access/ has mode 000
            if path.is_dir() and not path.is_symlink():
                os.chmod(path, 0o755)
        cls.temp.cleanup()

    # -- helpers --------------------------------------------------------

    def assert_contract(self, records):
        """Checks that hold for every scan: order, validators, and counts in done."""
        self.assertEqual(records[0]["type"], "entry")
        self.assertEqual(records[0]["relativePath"], "")
        self.assertIsNone(records[0]["parentRelativePath"])
        self.assertEqual(records[-1]["type"], "done")
        self.assertEqual([r for r in records[:-1] if r["type"] == "done"], [])

        seen = {}
        files = dirs = errors = skipped = 0
        for record in records[:-1]:
            kind = record["type"]
            if kind == "entry":
                entry = ScanManager._validate_entry(record, "wsl")  # raises ValueError if bad
                self.assertNotIn("allocatedBytes", record, "Python measures allocated size itself")
                parent = entry["parentRelativePath"]
                if parent is not None:
                    self.assertEqual(seen.get(parent), "directory", f"parent before child: {record}")
                self.assertNotIn(entry["relativePath"], seen, "duplicate relativePath")
                seen[entry["relativePath"]] = entry["kind"]
                files += entry["kind"] == "file"
                dirs += entry["kind"] == "directory"
            elif kind == "error":
                errors += 1
                self.assertEqual(sorted(record), ["code", "message", "relativePath", "type"])
            elif kind == "skipped":
                skipped += 1
                self.assertEqual(sorted(record), ["reason", "relativePath", "type"])
            else:
                self.fail(f"unknown record type {kind}")

        done = ScanManager._validate_done(records[-1])
        self.assertEqual((done["fileCount"], done["directoryCount"], done["errorCount"], done["skippedCount"]),
                         (files, dirs, errors, skipped))
        self.assertEqual(done["complete"], errors == 0 and skipped == 0)
        return done

    def make_tree(self, name):
        root = self.base / name
        root.mkdir()
        return root

    # -- tests ----------------------------------------------------------

    def test_demo_folder_is_complete_and_matches_shipped_sample(self):
        code, records, _, stderr = run(self.binary, self.demo)
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        done = self.assert_contract(records)
        self.assertEqual((done["fileCount"], done["directoryCount"]), (64, 13))
        self.assertTrue(done["complete"])

        def facts(recs):
            return {(r["relativePath"], r["kind"], r["logicalBytes"]) for r in recs if r["type"] == "entry"}

        sample = [json.loads(line) for line in SAMPLE.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(facts(records), facts(sample))

    def test_same_records_every_run_and_trailing_slash_is_ignored(self):
        # Names are printed in the order the filesystem returns them (not sorted), so compare as sets.
        _, _, first, _ = run(self.binary, self.demo)
        _, _, second, _ = run(self.binary, self.demo)
        _, _, slashed, _ = run(self.binary, str(self.demo) + "/")
        self.assertEqual(sorted(first.split("\n")), sorted(second.split("\n")))
        self.assertEqual(sorted(first.split("\n")), sorted(slashed.split("\n")))

    def test_empty_folder_and_zero_byte_file(self):
        root = self.make_tree("empty-root")
        code, records, _, _ = run(self.binary, root)
        self.assertEqual(code, 0)
        self.assertEqual(len(records), 2)
        self.assert_contract(records)
        (root / "zero.bin").write_bytes(b"")
        _, records, _, _ = run(self.binary, root)
        zero = [r for r in records if r.get("relativePath") == "zero.bin"][0]
        self.assertEqual(zero["logicalBytes"], 0)

    def test_special_characters_survive_json(self):
        root = self.make_tree("odd-names")
        names = ['quote"mark.txt', "tab\there.txt", "new\nline.txt", "emoji-😀.txt", "ชื่อ ไทย.txt", "sp ace.txt"]
        for name in names:
            (root / name).write_text("x")
        code, records, stdout, _ = run(self.binary, root)
        self.assertEqual(code, 0)
        self.assert_contract(records)
        self.assertEqual(len(stdout.split("\n")) - 1, len(records), "a raw newline split a record")
        self.assertEqual({r["name"] for r in records[1:-1]}, set(names))

    def test_deep_folder(self):
        root = self.make_tree("deep")
        cursor = root
        for level in range(40):
            cursor = cursor / f"d{level}"
        cursor.mkdir(parents=True)
        (cursor / "leaf.txt").write_text("deep")
        code, records, _, _ = run(self.binary, root)
        self.assertEqual(code, 0)
        done = self.assert_contract(records)
        self.assertEqual((done["fileCount"], done["directoryCount"]), (1, 41))

    def test_folders_nested_past_the_open_directory_limit(self):
        """Below 32 levels subdirectories are queued instead of entered; counts must still be exact."""
        root = self.make_tree("queued")
        cursor = root
        for level in range(36):
            cursor = cursor / f"d{level}"
        cursor.mkdir(parents=True)
        for sibling in range(5):  # several queued siblings at the deepest level
            (cursor / f"s{sibling}").mkdir()
            (cursor / f"s{sibling}" / "f.txt").write_text("ab")
        (cursor / "a.txt").write_text("abc")
        code, records, _, _ = run(self.binary, root)
        self.assertEqual(code, 0)
        done = self.assert_contract(records)
        self.assertEqual((done["fileCount"], done["directoryCount"]), (6, 1 + 36 + 5))
        self.assertEqual(sum(r["logicalBytes"] for r in records[:-1]), 3 + 5 * 2)

    def test_deep_tree_needs_only_a_few_file_descriptors(self):
        root = self.make_tree("fd-limit")
        cursor = root
        for level in range(150):
            cursor = cursor / f"d{level}"
        cursor.mkdir(parents=True)
        (cursor / "leaf.txt").write_text("x")
        code, records, _, stderr = run(self.binary, root, max_fds=40)  # stdio + 33 open dirs at most
        self.assertEqual((code, stderr), (0, ""))
        done = self.assert_contract(records)
        self.assertEqual((done["fileCount"], done["directoryCount"], done["errorCount"]), (1, 151, 0))

    def test_wide_folders(self):
        root = self.make_tree("wide")
        for number in range(3000):
            (root / f"f{number}.txt").write_text("x")
        for number in range(200):
            (root / f"sub{number}").mkdir()
            (root / f"sub{number}" / "g.txt").write_text("yy")
        code, records, _, _ = run(self.binary, root)
        self.assertEqual(code, 0)
        done = self.assert_contract(records)
        self.assertEqual((done["fileCount"], done["directoryCount"]), (3200, 201))

    def test_problem_cases_are_reported_not_hidden(self):
        root = self.base / "issues"
        subprocess.run(["sh", str(FIXTURE_SCRIPT), str(root), "--with-issues"], check=True, capture_output=True)
        prefix = ()
        is_root = os.geteuid() == 0
        if is_root and shutil.which("setpriv"):
            prefix = ("setpriv", "--reuid=65534", "--regid=65534", "--clear-groups")
            is_root = False
        code, records, _, _ = run(self.binary, root, prefix=prefix)
        self.assertEqual(code, 1)
        done = self.assert_contract(records)
        self.assertFalse(done["complete"])

        by_path = {}
        for r in records[:-1]:  # the last record is "done", which has no path
            by_path.setdefault(r["relativePath"], []).append(r)

        for link in ("back-to-root", "broken-link"):  # entry of kind link AND skipped, same path
            kinds = sorted((r["type"], r.get("kind") or r.get("reason")) for r in by_path[link])
            self.assertEqual(kinds, [("entry", "link"), ("skipped", "symlink")])
        self.assertFalse([p for p in by_path if p.startswith("back-to-root/")], "followed a loop")

        self.assertEqual([r["reason"] for r in by_path["pipe.fifo"]], ["special_file"])

        unsupported = [r for r in records if r["type"] == "error" and r["code"] == "UNSUPPORTED_NAME"]
        self.assertEqual(len(unsupported), 2)
        self.assertIn("back\\slash.txt", {r["relativePath"] for r in unsupported})
        self.assertTrue(any("\ufffd" in r["relativePath"] for r in unsupported))

        if not is_root:  # root can read mode-000 folders, so only check this for normal users
            self.assertEqual([r["code"] for r in by_path["no-access"] if r["type"] == "error"], ["EACCES"])
            self.assertFalse([p for p in by_path if p.startswith("no-access/")], "invented a size for hidden.txt")

    def test_bad_input_exits_2_with_empty_stdout(self):
        a_file = self.demo / "zero.bin"
        cases = [
            [],
            ["--root", str(self.demo)],
            ["--ndjson"],
            ["--root", "relative/path", "--ndjson"],
            ["--root", "/definitely/not/here", "--ndjson"],
            ["--root", str(a_file), "--ndjson"],
            ["--root", "/", "--ndjson"],
            ["--root", str(self.demo) + "/../demo", "--ndjson"],
            ["--root", str(self.demo), "--ndjson", "--bogus"],
            ["--root"],
        ]
        for args in cases:
            with self.subTest(args=args):
                result = subprocess.run([str(self.binary), *args], capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                self.assertTrue(result.stderr)

    def test_sigterm_stops_scanner_even_when_stdout_pipe_is_full(self):
        """Python cancels by SIGTERM and stops reading; the scanner must still exit with 130."""
        root = self.make_tree("many-files")
        for number in range(6000):  # about 660 KB of output, far more than a pipe holds
            (root / f"file-{number:05d}.txt").write_text("x")
        process = subprocess.Popen([str(self.binary), "--root", str(root), "--ndjson"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(0.5)
            self.assertIsNone(process.poll(), "scanner should be blocked on the full pipe")
            process.send_signal(signal.SIGTERM)
            self.assertEqual(process.wait(timeout=3), 130)
        finally:
            if process.poll() is None:
                process.kill()
            process.stdout.close()
            process.stderr.close()
            process.wait()


if __name__ == "__main__":
    unittest.main()
