"""
High-Performance Concurrent File System Scanner
Responsible for Student 1: Saran Papornchai

Key OS Concepts Implemented:
1. Producer-Consumer Pattern with Thread-Safe Work Queue (queue.Queue).
2. Deadlock-Free Concurrency (Pushes NVMe Queue Depth QD > 1).
3. Direct Win32 FindFirstFileExW (LARGE_FETCH + Basic Info) integration.
4. Reparse Point & Junction Safety Gate (Prevents Infinite Circular Loops).
5. Single-Threaded Baseline Scanner for Live Benchmark Battle.
"""

import os
import queue
import threading
import time
from typing import Dict, List, Any

from backend.win32_api import fast_scan_directory, get_cluster_size
from backend.os_storage import calculate_physical_and_slack, get_file_category
from backend.arena import CompactFileNode

class DirectoryScanner:
    def __init__(self, root_path: str, max_workers: int = 8):
        self.root_path = os.path.abspath(root_path)
        self.max_workers = max_workers
        self.cluster_size = get_cluster_size(self.root_path)
        self.lock = threading.Lock()
        
        # Statistics
        self.scanned_files = 0
        self.scanned_folders = 0
        self.total_logical_bytes = 0
        self.total_physical_bytes = 0
        self.total_slack_bytes = 0
        self.categories: Dict[str, int] = {}
        self.largest_files: List[Dict[str, Any]] = []

    def scan_single_threaded(self) -> Dict[str, Any]:
        """
        Baseline scanner using standard Python os.walk.
        Used directly in the Live Benchmark Battle to demonstrate the OS bottleneck
        (Single-threaded blocking I/O with Queue Depth QD = 1).
        """
        start_time = time.perf_counter()
        file_count = 0
        folder_count = 0
        total_size = 0

        try:
            for root, dirs, files in os.walk(self.root_path):
                folder_count += 1
                for f in files:
                    file_count += 1
                    fp = os.path.join(root, f)
                    try:
                        total_size += os.path.getsize(fp)
                    except OSError:
                        pass
        except Exception:
            pass

        duration = time.perf_counter() - start_time
        speed = file_count / duration if duration > 0 else 0

        return {
            "mode": "Single-Threaded (os.walk)",
            "duration_seconds": round(duration, 3),
            "files_scanned": file_count,
            "folders_scanned": folder_count,
            "total_size_bytes": total_size,
            "files_per_second": round(speed, 1),
        }

    def scan_concurrent(self) -> CompactFileNode:
        """
        High-performance concurrent scan using Producer-Consumer pattern.
        Deadlock-free and scales smoothly across any thread count (1 to 32+).
        """
        root_node = CompactFileNode(self.root_path, is_dir=True, path=self.root_path)
        work_queue = queue.Queue()
        work_queue.put((self.root_path, root_node))

        active_tasks = 1
        active_tasks_lock = threading.Lock()
        stop_event = threading.Event()

        def worker():
            nonlocal active_tasks
            while not stop_event.is_set():
                try:
                    dir_path, dir_node = work_queue.get(timeout=0.05)
                except queue.Empty:
                    with active_tasks_lock:
                        if active_tasks == 0:
                            break
                    continue

                try:
                    entries = fast_scan_directory(dir_path)
                    with self.lock:
                        self.scanned_folders += 1

                    subdirs = []
                    files_info = []

                    for name, is_dir, is_reparse, file_size in entries:
                        child_path = os.path.join(dir_path, name)
                        if is_dir:
                            child_node = CompactFileNode(name, is_dir=True, path=child_path)
                            dir_node.add_child(child_node)
                            # Reparse Point Safety Gate (skip junctions/symlinks to avoid loops)
                            if not is_reparse:
                                subdirs.append((child_path, child_node))
                        else:
                            phys_size, slack = calculate_physical_and_slack(file_size, self.cluster_size)
                            file_node = CompactFileNode(
                                name,
                                is_dir=False,
                                path=child_path,
                                size_logical=file_size,
                                size_physical=phys_size,
                                slack_space=slack,
                            )
                            dir_node.add_child(file_node)

                            ext = os.path.splitext(name)[1]
                            files_info.append((child_path, name, file_size, phys_size, slack, ext))

                    # Batch record statistics
                    if files_info:
                        with self.lock:
                            for cp, nm, ls, ps, sk, ex in files_info:
                                self.scanned_files += 1
                                cat = get_file_category(ex)
                                self.categories[cat] = self.categories.get(cat, 0) + ls
                                self._record_largest_file(cp, nm, ls, ps, sk)

                    # Enqueue subdirectories
                    if subdirs:
                        with active_tasks_lock:
                            active_tasks += len(subdirs)
                        for sp, dn in subdirs:
                            work_queue.put((sp, dn))

                except Exception:
                    pass
                finally:
                    with active_tasks_lock:
                        active_tasks -= 1
                        if active_tasks == 0:
                            stop_event.set()
                    work_queue.task_done()



        threads = []
        num_threads = max(1, self.max_workers)
        for _ in range(num_threads):
            t = threading.Thread(target=worker)
            t.daemon = True
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        # Bottom-up post-order rollup
        root_node.rollup_sizes()

        self.total_logical_bytes = root_node.size_logical
        self.total_physical_bytes = root_node.size_physical
        self.total_slack_bytes = root_node.slack_space
        self.scanned_files = root_node.file_count

        return root_node

    def _record_largest_file(self, full_path: str, name: str, logical: int, physical: int, slack: int):
        """Maintains Top 20 largest files."""
        if len(self.largest_files) < 20:
            self.largest_files.append({
                "path": full_path,
                "name": name,
                "logical_size": logical,
                "physical_size": physical,
                "slack_space": slack,
            })
            self.largest_files.sort(key=lambda x: x["logical_size"], reverse=True)
        elif logical > self.largest_files[-1]["logical_size"]:
            self.largest_files[-1] = {
                "path": full_path,
                "name": name,
                "logical_size": logical,
                "physical_size": physical,
                "slack_space": slack,
            }
            self.largest_files.sort(key=lambda x: x["logical_size"], reverse=True)
