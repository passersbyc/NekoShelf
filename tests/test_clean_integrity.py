import os
import tempfile
import unittest

from core.commands.system import SystemCommandsMixin
from core.database import DatabaseManager
from core.file_manager import FileManager
from core.import_engine import ImportEngine


class _Dummy(SystemCommandsMixin):
    pass


class TestCleanIntegrity(unittest.TestCase):
    def test_relink_missing_file_by_hash(self):
        with tempfile.TemporaryDirectory() as td:
            lib_dir = os.path.join(td, "library")
            os.makedirs(os.path.join(lib_dir, "Alice"), exist_ok=True)
            fp = os.path.join(lib_dir, "Alice", "Hello.txt")
            with open(fp, "w", encoding="utf-8") as f:
                f.write("hello")

            db_path = os.path.join(td, "library.db")
            db = DatabaseManager(db_path)
            fm = FileManager(lib_dir)
            eng = ImportEngine(db, fm, import_exts={".txt"})
            fh = eng.file_hash(fp)

            wrong_path = os.path.join(lib_dir, "Alice", "Moved.txt")
            db.add_book("Hello", "Alice", "", 0, "", wrong_path, "txt", file_hash=fh)

            cli = _Dummy()
            cli.db = db
            cli.fm = fm
            cli._IMPORT_EXTS = {".txt"}

            cli.do_clean(f"--fix --yes --dir={lib_dir} --type=txt")

            books = list(db.list_books())
            self.assertEqual(len(books), 1)
            self.assertTrue(os.path.exists(books[0]["file_path"]))
            self.assertEqual(os.path.normpath(os.path.abspath(books[0]["file_path"])), os.path.normpath(os.path.abspath(fp)))
            db.close()

    def test_add_missing_db_record(self):
        with tempfile.TemporaryDirectory() as td:
            lib_dir = os.path.join(td, "library")
            os.makedirs(os.path.join(lib_dir, "Bob"), exist_ok=True)
            fp = os.path.join(lib_dir, "Bob", "Work.txt")
            with open(fp, "w", encoding="utf-8") as f:
                f.write("content")

            db_path = os.path.join(td, "library.db")
            db = DatabaseManager(db_path)
            fm = FileManager(lib_dir)

            cli = _Dummy()
            cli.db = db
            cli.fm = fm
            cli._IMPORT_EXTS = {".txt"}

            self.assertEqual(len(list(db.list_books())), 0)
            cli.do_clean(f"--fix --yes --dir={lib_dir} --type=txt")
            books = list(db.list_books())
            self.assertEqual(len(books), 1)
            self.assertTrue(os.path.exists(books[0]["file_path"]))
            db.close()


if __name__ == "__main__":
    unittest.main()

