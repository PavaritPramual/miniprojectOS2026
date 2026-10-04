"""Generate explicitly fictional scan/API examples for the shared 64-file fixture."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.scan_store import ScanStore


def entry(path, kind, size=0):
    record = {"type": "entry", "relativePath": path,
              "parentRelativePath": path.rpartition("/")[0] if path else None,
              "name": path.rsplit("/", 1)[-1] if path else "demo",
              "kind": kind, "logicalBytes": size}
    if kind == "file":
        # These values are fabricated, never measurements from Windows.
        record["allocatedBytes"] = ((size + 4095) // 4096) * 4096
    return record


def demo_records():
    records = [entry("", "directory"), entry("empty", "directory"), entry("depth", "directory")]
    path = "depth"
    for i in range(1, 9):
        path += f"/level-{i:02d}"
        records.append(entry(path, "directory"))
    records.append(entry(path + "/leaf.txt", "file", 4))
    records.append(entry("many", "directory"))
    records.extend(entry(f"many/child-{i:03d}.txt", "file", 1) for i in range(1, 61))
    records.extend([entry("ชื่อ ไทย", "directory"), entry("ชื่อ ไทย/รายงาน 1.txt", "file", 5),
                    entry("zero.bin", "file", 0), entry("large.bin", "file", 1024 * 1024)])
    records.append({"type": "done", "fileCount": 64, "directoryCount": 13,
                    "errorCount": 0, "skippedCount": 0, "complete": True})
    return records


def main():
    records = demo_records()
    output = ROOT / "docs" / "examples"
    output.joinpath("scan.ndjson").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records) + "\n",
        encoding="utf-8")
    temp_base = ROOT / "fixtures" / "generated"
    temp_base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_base) as temp:
        store = ScanStore(str(Path(temp) / "samples.sqlite3"))
        scan_id = "scan-demo-001"
        store.create_scan(scan_id, r"D:\demo", "sample", False)
        store.set_state(scan_id, "running")
        store.add_records(scan_id, records[:-1])
        store.finish_scan(scan_id, "completed")
        status = {"id": scan_id, "rootPath": r"D:\demo", "source": "sample", "isSample": True,
                  "state": "completed", "fileCount": 64, "directoryCount": 13,
                  "errorCount": 0, "skippedCount": 0, "elapsedSeconds": 0.0,
                  "partial": False, "error": None}
        examples = {"note": "Fictional data: allocated sizes and elapsed time are not measurements.",
                    "startSampleRequest": {"path": r"D:\demo", "source": "sample"},
                    "startSampleResponse": {"id": scan_id, "state": "queued", "source": "sample"},
                    "runningStatus": dict(status, state="running", fileCount=17, directoryCount=11),
                    "completedStatus": status,
                    "rootChildren": store.list_children(scan_id, "", 0, 50),
                    "childrenPage1": store.list_children(scan_id, "many", 0, 50),
                    "childrenPage2": store.list_children(scan_id, "many", 50, 50),
                    "emptyChildren": store.list_children(scan_id, "empty", 0, 50),
                    "issuesPage": store.list_issues(scan_id, 0, 50),
                    "cancelResponse": {"id": scan_id, "state": "cancelling"},
                    "latestRealRequest": "/api/scans/latest?path=D%3A%5Cdemo",
                    "latestRealResponseShape": dict(status, source="wsl", isSample=False),
                    "errorExample": {"code": "SCAN_NOT_FOUND", "detail": "ไม่พบงานสแกน"}}
        output.joinpath("api.json").write_text(json.dumps(examples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
