"""Isolated UI integration fixture: real HTTP handler/manager/store, no C/Windows calls."""
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from backend.scan_store import ScanStore
from backend.scan_manager import ScanManager


def entry(path, kind='directory', size=0):
    return dict(relativePath=path, parentRelativePath=path.rpartition('/')[0] if path else None,
                name=path.rsplit('/', 1)[-1] or 'fixture', kind=kind,
                logicalBytes=size, allocatedBytes=size, partial=False)


with tempfile.TemporaryDirectory(prefix='corespace-ui-review-') as directory:
    store = ScanStore(str(Path(directory) / 'scans.sqlite3'))
    main.SCAN_MANAGER = ScanManager(store)
    for scan_id in ['root', 'empty', 'issues', 'failed', 'live-failed', 'live-complete']:
        store.create_scan(scan_id, 'D:\\' + scan_id, 'sample', False)
        store.set_state(scan_id, 'running')
        store.add_entry(scan_id, entry(''))
        if scan_id in ['root', 'live-complete']:
            store.add_entry(scan_id, entry('nested'))
            store.add_entry(scan_id, entry('nested/large.bin', 'file', 1048576))
        if scan_id == 'issues':
            for i in range(60):
                store.add_issue(scan_id, f'secret-{i:02}.txt', 'ACCESS_DENIED' if i % 2 == 0 else 'SYMLINK_SKIPPED',
                                f'REVIEW_REASON_{i:02}', 'error' if i % 2 == 0 else 'skipped')
        if not scan_id.startswith('live-'):
            store.finish_scan(scan_id, 'failed' if scan_id == 'failed' else 'partial' if scan_id == 'issues' else 'completed',
                              'REVIEW_FAILED_SAVED' if scan_id == 'failed' else None)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), main.CoreSpaceRequestHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}'}), flush=True)
    try:
        for line in sys.stdin:
            command = json.loads(line)
            store.finish_scan(command['id'], command['state'], command.get('error'))
            print(json.dumps({'finished': command['id']}), flush=True)
    finally:
        server.shutdown()
        main.SCAN_MANAGER.shutdown()
