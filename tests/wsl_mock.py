#!/usr/bin/env python3
"""TEST ONLY. Emits controlled records; this is not the group's C scanner."""
import argparse
import json
import signal
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True)
parser.add_argument("--ndjson", action="store_true")
parser.add_argument("--mode", choices=("demo", "slow", "silent", "ignore-term", "crash"), default="demo")
args = parser.parse_args()

def emit(record):
    print(json.dumps(record, ensure_ascii=False), flush=True)

if args.mode == "demo":
    for line in (Path(__file__).resolve().parents[1] / "docs/examples/scan.ndjson").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        record.pop("allocatedBytes", None)
        emit(record)
    sys.exit(0)

if args.mode == "ignore-term":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
emit({"type":"entry","relativePath":"","parentRelativePath":None,
      "name":Path(args.root).name,"kind":"directory","logicalBytes":0})
if args.mode == "crash":
    print("intentional test crash", file=sys.stderr, flush=True)
    sys.exit(2)
if args.mode in {"slow", "ignore-term"}:
    emit({"type":"entry","relativePath":"zero.bin","parentRelativePath":"",
          "name":"zero.bin","kind":"file","logicalBytes":0})
time.sleep(60)
