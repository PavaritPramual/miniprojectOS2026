import tempfile
import unittest
from pathlib import Path
from backend.scan_store import ScanStore


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = ScanStore(str(Path(self.directory.name) / 'search.sqlite3'))
        self.store.create_scan('one', 'D:\\one', 'wsl', False)
        self.store.set_state('one', 'running')
        self.add('', None, 'directory', 0)
        for i in range(60):
            self.add(f'child-{i:02}.txt', '', 'file', i)
        self.add('100%_done.txt', '', 'file', 3)
        self.add('ชื่อ ไทย.txt', '', 'file', None)
        self.add('folder', '', 'directory', 1)
        self.add('folder/รายงาน.txt', 'folder', 'file', 1)

    def add(self, relative, parent, kind, size):
        self.store.add_entry('one', dict(relativePath=relative, parentRelativePath=parent,
            name=relative or 'root', kind=kind, logicalBytes=1, allocatedBytes=size, partial=size is None))

    def test_pages_preserve_all_results_and_partial_status(self):
        first = self.store.search_entries('one', 'child-', 0, 50)
        second = self.store.search_entries('one', 'child-', 50, 50)
        self.assertEqual(first['total'], 60)
        self.assertTrue(first['partial'])
        self.assertEqual(len(first['items']), 50)
        self.assertEqual(len(second['items']), 10)
        self.assertEqual(len({x['relativePath'] for x in first['items'] + second['items']}), 60)

    def test_wildcards_are_literal_and_scans_are_isolated(self):
        self.assertEqual(self.store.search_entries('one', '%_', 0, 50)['total'], 1)
        self.assertEqual(self.store.search_entries('one', "' OR 1=1 --", 0, 50)['total'], 0)
        self.assertIsNone(self.store.search_entries('unknown', 'child', 0, 50))
        self.store.create_scan('two', 'D:\\two', 'wsl', False)
        self.assertEqual(self.store.search_entries('two', 'child', 0, 50)['total'], 0)

    def test_unicode_and_unknown_are_not_zero(self):
        result = self.store.search_entries('one', 'ไทย', 0, 50)
        self.assertEqual(result['total'], 1)
        self.assertIsNone(result['items'][0]['allocatedBytes'])
        self.assertTrue(result['items'][0]['partial'])

    def test_windows_full_path_and_relative_path(self):
        self.assertEqual(self.store.search_entries('one', 'D:\\one\\folder\\รายงาน.txt', 0, 50)['total'], 1)
        self.assertEqual(self.store.search_entries('one', 'folder\\รายงาน', 0, 50)['total'], 1)


if __name__ == '__main__':
    unittest.main()
