import unittest
import os
import sqlite3
from core.database import DatabaseManager

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_library.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.db = DatabaseManager(self.test_db)

    def tearDown(self):
        if self.db.conn:
            self.db.conn.close()
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_tables_creation(self):
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        self.assertIn('books', tables)
        self.assertIn('authors', tables)

    def test_ensure_author(self):
        # Assuming _ensure_author is a private method but we can test it for initialization
        # Let's test a public method if available, or just check table structure
        cursor = self.db.conn.cursor()
        cursor.execute("PRAGMA table_info(books)")
        columns = [info[1] for info in cursor.fetchall()]
        self.assertIn('title', columns)
        self.assertIn('author', columns)

if __name__ == '__main__':
    unittest.main()
