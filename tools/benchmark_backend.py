"""Compare actual old/new scans in fresh Python processes; never substitute sample data."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.scanner import DirectoryScanner
from backend.scan_manager import ScanManager
from backend.scan_store import ScanStore


def python_peak_bytes():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("peak", "working", "quotaPeakPaged", "quotaPaged",
                                                "quotaPeakNonPaged", "quotaNonPaged", "pagefile", "peakPagefile")]
    counters = Counters(); counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return None
    return counters.peak


class MeasuredManager(ScanManager):
    """GNU time wraps the launcher; the PID file still identifies the scanner itself."""
    def __init__(self, store, metrics_path):
        super().__init__(store)
        self.metrics_path = metrics_path

    def _start_wsl_process(self, root_path, job):
        root = self._wsl_path(root_path, job)
        fd, pid_file = tempfile.mkstemp(prefix="corespace-benchmark-", suffix=".pid")
        os.close(fd)
        try:
            pid_wsl = self._wsl_path(pid_file, job)
            metrics_wsl = self._wsl_path(str(self.metrics_path), job)
            command = [self.wsl_executable, "-d", self.wsl_distro, "--exec", "/usr/bin/time",
                       "-f", "%M", "-o", metrics_wsl, "sh", "-c",
                       'printf "%s" "$$" > "$1"; shift; exec "$@"', "corespace-benchmark",
                       pid_wsl, self.scanner_wsl_path, "--root", root, "--ndjson"]
            if job["cancel"].is_set():
                raise RuntimeError("benchmark cancelled before launch")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8", errors="replace", bufsize=1)
            return process, pid_file
        except Exception:
            os.unlink(pid_file)
            raise


def worker(args):
    if os.name != "nt": raise RuntimeError("Run this tool using Windows Python")
    started = time.perf_counter()
    if args.engine == "prototype":
        scanner = DirectoryScanner(args.path)
        tree = scanner.scan_concurrent()
        elapsed = time.perf_counter() - started
        result = {"engine":"prototype", "firstResponseSeconds":elapsed,
                  "elapsedSeconds":elapsed, "fileCount":scanner.scanned_files,
                  "directoryCount":scanner.scanned_folders, "state":"prototype",
                  "cPeakRssBytes":None, "firstDataSeconds":elapsed}
        # Keep the resulting tree alive until Windows reports peak working set.
        assert tree is not None
    else:
        if not args.scanner: raise RuntimeError("Supply --scanner with the real C executable's absolute WSL path")
        temp_base = ROOT / "fixtures/generated"; temp_base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_base) as temp:
            metrics = Path(temp) / "c-rss.txt"
            manager = MeasuredManager(ScanStore(str(Path(temp) / "results.sqlite3")), metrics)
            manager.scanner_wsl_path = args.scanner
            manager.wsl_distro = args.distro
            first_data = None
            try:
                started = time.perf_counter()
                scan_id = manager.start_scan({"path":args.path})["id"]
                response_time = time.perf_counter() - started
                while True:
                    status = manager.get_status(scan_id)
                    if first_data is None and status["directoryCount"]:
                        first_data = time.perf_counter() - started
                    if status["state"] not in {"queued", "running", "cancelling"}: break
                    time.sleep(0.05)
                elapsed = time.perf_counter() - started
            finally:
                manager.shutdown()
            rss = None
            if metrics.exists():
                numeric = [line for line in metrics.read_text().splitlines() if line.strip().isdigit()]
                if numeric: rss = int(numeric[-1]) * 1024
            result = {"engine":"new", "firstResponseSeconds":response_time,
                      "firstDataSeconds":first_data, "elapsedSeconds":elapsed,
                      "fileCount":status["fileCount"], "directoryCount":status["directoryCount"],
                      "state":status["state"], "errorCount":status["errorCount"],
                      "skippedCount":status["skippedCount"], "error":status["error"], "cPeakRssBytes":rss}
    result["pythonPeakWorkingSetBytes"] = python_peak_bytes()
    result["filesPerSecond"] = result["fileCount"] / elapsed if elapsed else None
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.engine == "new" and result["state"] not in {"completed", "partial"}:
        raise RuntimeError("New scan failed; see the saved result")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True)
    parser.add_argument("--scanner", default=os.environ.get("CORESPACE_SCANNER_WSL_PATH", ""))
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", default="docs/results/benchmark.json")
    parser.add_argument("--engine", choices=("prototype", "new"), help=argparse.SUPPRESS)
    parser.add_argument("--test-only", action="store_true", help="label controlled mock runs; never use as C performance evidence")
    args = parser.parse_args()
    args.path = os.path.abspath(args.path)
    if args.engine: return worker(args)
    if args.runs < 1: parser.error("--runs must be positive")
    if not args.scanner or not args.scanner.startswith("/"): parser.error("--scanner must be an absolute WSL path")
    if not os.path.isdir(args.path): parser.error("--path must be an existing folder")
    output = Path(args.output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    temp_base = ROOT / "fixtures/generated"; temp_base.mkdir(parents=True, exist_ok=True)
    report = {"path":args.path, "scanner":args.scanner, "distro":args.distro,
              "testOnly":args.test_only, "runsPerEngine":args.runs,
              "methods":{"time":"wall clock including launch, parse, allocation and SQLite for new engine",
                         "pythonMemory":"Windows peak working set, fresh Python process per run",
                         "cMemory":"GNU time maximum resident set size (KiB converted to bytes)",
                         "cache":"not cleared; alternate old/new order; median of measured runs",
                         "firstResponse":"old: complete scan; new: job creation returns; not HTTP/browser latency"},
              "runs":[]}
    with tempfile.TemporaryDirectory(dir=temp_base) as temp:
        for run in range(args.runs):
            order = ("prototype", "new") if run % 2 == 0 else ("new", "prototype")
            for engine in order:
                single = Path(temp) / f"{run}-{engine}.json"
                command = [sys.executable, str(Path(__file__).resolve()), "--engine", engine,
                           "--path", args.path, "--scanner", args.scanner, "--distro", args.distro,
                           "--output", str(single)]
                completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if single.exists(): report["runs"].append(dict(json.loads(single.read_text(encoding="utf-8")), run=run+1))
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                if completed.returncode:
                    raise RuntimeError(f"{engine} run failed: {completed.stderr[-1000:]}; partial evidence saved at {output}")
    report["medians"] = {}
    for engine in ("prototype", "new"):
        runs = [r for r in report["runs"] if r["engine"] == engine]
        report["medians"][engine] = {key: statistics.median(r[key] for r in runs if r[key] is not None)
                                    if any(r[key] is not None for r in runs) else None
                                    for key in ("elapsedSeconds", "firstResponseSeconds", "filesPerSecond", "pythonPeakWorkingSetBytes", "cPeakRssBytes")}
    file_counts = {r["fileCount"] for r in report["runs"]}
    report["comparableFileCounts"] = len(file_counts) == 1
    report["warning"] = "Do not claim a speedup if counts differ, results are partial, or testOnly is true. Old/new engines perform different work."
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(output))


if __name__ == "__main__": main()
