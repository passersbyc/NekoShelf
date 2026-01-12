import os
import tempfile
import unittest

from core.database import DatabaseManager
from core.file_manager import FileManager
from core.import_engine import ImportEngine


class TestKemonoDedup(unittest.TestCase):
    def test_overwrite_and_rename(self):
        with tempfile.TemporaryDirectory() as td:
            lib_dir = os.path.join(td, "library")
            os.makedirs(lib_dir, exist_ok=True)
            db_path = os.path.join(td, "test.db")
            db = DatabaseManager(db_path)
            fm = FileManager(lib_dir)
            eng = ImportEngine(db, fm, import_exts={".txt"})

            src = os.path.join(td, "Alice - Hello (kemono：patreon：1：2).txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write("v1")

            ok, is_dup, _ = eng.import_one(src, dup_mode="skip", hash_cache={})
            self.assertTrue(ok)
            self.assertFalse(is_dup)
            self.assertEqual(len(list(db.list_books())), 1)
            dr = db.get_download_record("kemono", "patreon:1:2")
            self.assertIsNotNone(dr)

            with open(src, "w", encoding="utf-8") as f:
                f.write("v2")
            ok2, is_dup2, _ = eng.import_one(src, dup_mode="overwrite", hash_cache={})
            self.assertTrue(ok2)
            self.assertFalse(is_dup2)
            self.assertEqual(len(list(db.list_books())), 1)

            with open(src, "w", encoding="utf-8") as f:
                f.write("v3")
            ok3, is_dup3, _ = eng.import_one(src, dup_mode="rename", hash_cache={})
            self.assertTrue(ok3)
            self.assertFalse(is_dup3)
            books = list(db.list_books())
            self.assertEqual(len(books), 2)
            titles = sorted([b["title"] for b in books])
            self.assertEqual(titles[0], "Hello")
            self.assertEqual(titles[1], "Hello (2)")

            db.close()


if __name__ == "__main__":
    unittest.main()
