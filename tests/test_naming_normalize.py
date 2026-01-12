import os
import tempfile
import unittest

from core.database import DatabaseManager
from core.file_manager import FileManager
from core.import_engine import ImportEngine
from core.utils import normalize_title


class TestNamingNormalize(unittest.TestCase):
    def test_fullwidth_to_halfwidth_title(self):
        self.assertEqual(normalize_title("ＡＢＣ１２３"), "ABC123")
        self.assertEqual(normalize_title("　Ａ－Ｂ＿Ｃ　"), "A-B_C")
        self.assertEqual(normalize_title("（１）"), "(1)")

    def test_import_renames_to_normalized_title(self):
        with tempfile.TemporaryDirectory() as td:
            lib_dir = os.path.join(td, "library")
            os.makedirs(lib_dir, exist_ok=True)

            src_dir = os.path.join(td, "src")
            os.makedirs(src_dir, exist_ok=True)

            src_name = "Alice - ＡＢＣ（１） (pixiv：novel：123).txt"
            src_path = os.path.join(src_dir, src_name)
            with open(src_path, "w", encoding="utf-8") as f:
                f.write("标题: ＡＢＣ（１）\n作者: Alice\n\ncontent")

            db_path = os.path.join(td, "library.db")
            db = DatabaseManager(db_path)
            fm = FileManager(lib_dir)
            eng = ImportEngine(
                db,
                fm,
                import_exts={".txt"},
                import_config={
                    "naming_rules": {
                        "title_fullwidth_to_halfwidth": True,
                        "title_collapse_spaces": True,
                        "title_keep_chars": "-_",
                        "filename_pattern": "{title}",
                    }
                },
            )

            ok, is_dup, _ = eng.import_one(src_path, dup_mode="skip")
            self.assertTrue(ok)
            self.assertFalse(is_dup)

            books = list(db.list_books())
            self.assertEqual(len(books), 1)
            self.assertEqual(books[0]["title"], "ABC(1)")
            saved_path = books[0]["file_path"]
            self.assertTrue(os.path.exists(saved_path))
            self.assertTrue(saved_path.endswith(os.path.join("Alice", "ABC(1).txt")))

            dr = db.get_download_record("pixiv", "novel:123")
            self.assertIsNotNone(dr)
            db.close()


if __name__ == "__main__":
    unittest.main()
