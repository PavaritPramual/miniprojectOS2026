"""
CoreSpace Benchmark CLI Tool
Responsible for Student 3: Theerameth Saikham

Used to run empirical benchmarks comparing:
1. Traditional Python os.walk (Single-Threaded, Queue Depth QD=1)
2. CoreSpace Multi-Threaded Engine (1 vs 2 vs 4 vs 8 vs 16 Threads)

Generates exact numbers and speedup factors for the final presentation slides.
"""

import os
import sys
import time

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


from backend.scanner import DirectoryScanner
from backend.os_storage import format_bytes

def run_benchmark(target_path: str):
    target = os.path.abspath(target_path)
    if not os.path.exists(target):
        print(f"[Error] Target path not found: {target}")
        return

    print("=" * 70)
    print(f"⚡ CoreSpace OS Benchmark Suite")
    print(f"📁 Target: {target}")
    print("=" * 70)

    # 1. Baseline os.walk
    print("\n[1/2] Running Baseline (Traditional os.walk, QD=1)...")
    scanner_base = DirectoryScanner(target, max_workers=1)
    base_res = scanner_base.scan_single_threaded()
    base_time = max(base_res["duration_seconds"], 0.001)
    base_files = base_res["files_scanned"]
    base_speed = base_res["files_per_second"]
    print(f"      Duration: {base_time:.3f} s | Files: {base_files} | Speed: {base_speed:.1f} files/s")

    # 2. Multi-threaded runs
    threads_to_test = [1, 2, 4, 8, 16]
    results = []

    print("\n[2/2] Running CoreSpace Multi-threaded Engine (Win32 LARGE_FETCH)...")
    for t in threads_to_test:
        scanner = DirectoryScanner(target, max_workers=t)
        start = time.perf_counter()
        root_node = scanner.scan_concurrent()
        duration = max(time.perf_counter() - start, 0.001)
        files = scanner.scanned_files
        speed = files / duration
        speedup = base_time / duration

        results.append({
            "threads": t,
            "duration": duration,
            "files": files,
            "speed": speed,
            "speedup": speedup
        })
        print(f"      [Threads: {t:2d}] {duration:.3f} s | Speed: {speed:8.1f} files/s | Speedup: {speedup:.1f}x")

    # Summary Table
    print("\n" + "=" * 70)
    print("🏆 EMPIRICAL BENCHMARK SUMMARY (For Presentation Slides)")
    print("=" * 70)
    print(f"{'Engine / Mode':<32} | {'Time (s)':<10} | {'Files/sec':<12} | {'Speedup':<8}")
    print("-" * 70)
    print(f"{'Baseline os.walk (QD=1)':<32} | {base_time:<10.3f} | {base_speed:<12.1f} | {'1.0x':<8}")
    for r in results:
        label = f"CoreSpace ({r['threads']} Threads)"
        print(f"{label:<32} | {r['duration']:<10.3f} | {r['speed']:<12.1f} | {r['speedup']:<7.1f}x")
    print("=" * 70)

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(".")
    run_benchmark(path)
