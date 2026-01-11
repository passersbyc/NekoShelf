import sqlite3
import datetime
from .config import DB_FILE

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self._connect()

    def _connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                tags TEXT,
                status INTEGER DEFAULT 0,
                series TEXT,
                file_path TEXT NOT NULL,
                file_hash TEXT,
                file_type TEXT,
                import_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 检查是否需要添加 status 和 series 字段 (针对旧数据库)
        cursor.execute("PRAGMA table_info(books)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'status' not in columns:
            cursor.execute("ALTER TABLE books ADD COLUMN status INTEGER DEFAULT 0")
        
        if 'series' not in columns:
            cursor.execute("ALTER TABLE books ADD COLUMN series TEXT")

        if 'file_hash' not in columns:
            cursor.execute("ALTER TABLE books ADD COLUMN file_hash TEXT")

        if 'import_date' not in columns:
            # 对于旧数据，将 created_at 作为 import_date (如果有的话)，或者当前时间
            cursor.execute("ALTER TABLE books ADD COLUMN import_date TIMESTAMP")
            cursor.execute("UPDATE books SET import_date = created_at WHERE import_date IS NULL")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_file_hash ON books(file_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_file_path ON books(file_path)")
        
        # 创建 authors 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS authors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                is_full INTEGER DEFAULT 0,
                last_work_date TEXT,
                contact TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 检查是否需要添加新字段 (针对旧数据库 authors 表)
        cursor.execute("PRAGMA table_info(authors)")
        a_columns = [info[1] for info in cursor.fetchall()]
        
        if 'is_full' not in a_columns:
            cursor.execute("ALTER TABLE authors ADD COLUMN is_full INTEGER DEFAULT 0")
        if 'last_work_date' not in a_columns:
            cursor.execute("ALTER TABLE authors ADD COLUMN last_work_date TEXT")
        if 'contact' not in a_columns:
            cursor.execute("ALTER TABLE authors ADD COLUMN contact TEXT")
        if 'last_import_date' not in a_columns:
            cursor.execute("ALTER TABLE authors ADD COLUMN last_import_date TIMESTAMP")
        
        # 尝试从 books 表同步作者到 authors 表
        cursor.execute('''
            INSERT OR IGNORE INTO authors (name)
            SELECT DISTINCT author FROM books 
            WHERE author IS NOT NULL AND author != ""
        ''')

        # 回填 authors.last_import_date (从 books.import_date)
        cursor.execute('''
            UPDATE authors 
            SET last_import_date = (
                SELECT MAX(import_date) 
                FROM books 
                WHERE books.author = authors.name
            )
            WHERE last_import_date IS NULL
        ''')

        self.conn.commit()

    def _ensure_author(self, name):
        if not name:
            return
        try:
            cursor = self.conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO authors (name) VALUES (?)', (name,))
            self.conn.commit()
        except Exception:
            pass

    def add_book(self, title, author, tags, status, series, file_path, file_type, file_hash=None, import_date=None):
        if import_date is None:
            import_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO books (title, author, tags, status, series, file_path, file_hash, file_type, import_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (title, author, tags, status, series, file_path, file_hash, file_type, import_date))
        self.conn.commit()
        
        # 确保作者存在于 authors 表
        self._ensure_author(author)
        # 同步更新作者的最后导入时间
        self.update_author_import_date(author, import_date)
        
        return cursor.lastrowid

    def update_author_import_date(self, author_name, import_date):
        if not author_name:
            return
        cursor = self.conn.cursor()
        # 只在新的 import_date 比现有的更新时才更新
        cursor.execute('''
            UPDATE authors 
            SET last_import_date = ? 
            WHERE name = ? AND (last_import_date IS NULL OR last_import_date < ?)
        ''', (import_date, author_name, import_date))
        self.conn.commit()

    def find_books_by_file_hash(self, file_hash, limit=20):
        if not file_hash:
            return []
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM books WHERE file_hash = ? ORDER BY created_at DESC LIMIT ?', (file_hash, int(limit)))
        return cursor.fetchall()

    def find_books_by_file_path(self, file_path, limit=20):
        if not file_path:
            return []
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM books WHERE file_path = ? ORDER BY created_at DESC LIMIT ?', (file_path, int(limit)))
        return cursor.fetchall()

    def find_books_by_signature(self, title, author, series=None, limit=50):
        title = "" if title is None else str(title)
        author = "" if author is None else str(author)
        series = "" if series is None else str(series)
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT * FROM books WHERE title = ? AND author = ? AND IFNULL(series, "") = ? ORDER BY created_at DESC LIMIT ?',
            (title, author, series, int(limit)),
        )
        return cursor.fetchall()

    def list_books(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM books ORDER BY created_at DESC')
        return cursor.fetchall()

    def list_authors(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT a.id, a.name, a.is_full, a.last_work_date, a.last_import_date, a.contact, COUNT(b.id) as book_count
            FROM authors a
            LEFT JOIN books b ON b.author = a.name
            GROUP BY a.id
            ORDER BY book_count DESC, a.name ASC
        ''')
        return cursor.fetchall()

    def update_author(self, author_id, **kwargs):
        if not kwargs:
            return False
        
        columns = ", ".join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values())
        values.append(author_id)
        
        cursor = self.conn.cursor()
        cursor.execute(f'UPDATE authors SET {columns} WHERE id = ?', values)
        self.conn.commit()
        return cursor.rowcount > 0

    def get_author(self, author_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM authors WHERE id = ?', (author_id,))
        return cursor.fetchone()

    def get_author_by_name(self, name):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM authors WHERE name = ?', (name,))
        return cursor.fetchone()

    def search_books(self, keyword):
        cursor = self.conn.cursor()
        pattern = f"%{keyword}%"
        cursor.execute('''
            SELECT * FROM books 
            WHERE title LIKE ? OR author LIKE ? OR tags LIKE ?
        ''', (pattern, pattern, pattern))
        return cursor.fetchall()

    def advanced_search(self, query=None, filters=None):
        if not query and not filters:
            return []

        def _to_ascii_punct(s):
            s = "" if s is None else str(s)
            table = {
                ord("！"): "!",
                ord("？"): "?",
                ord("："): ":",
                ord("；"): ";",
                ord("，"): ",",
                ord("。"): ".",
                ord("（"): "(",
                ord("）"): ")",
            }
            return s.translate(table)

        def _to_fullwidth_punct(s):
            s = "" if s is None else str(s)
            table = {
                ord("!"): "！",
                ord("?"): "？",
                ord(":"): "：",
                ord(";"): "；",
                ord(","): "，",
                ord("."): "。",
                ord("("): "（",
                ord(")"): "）",
            }
            return s.translate(table)

        def _like_patterns(value):
            raw = "" if value is None else str(value)
            cands = [raw, _to_ascii_punct(raw), _to_fullwidth_punct(raw)]
            out = []
            seen = set()
            for v in cands:
                v = "" if v is None else str(v)
                if not v:
                    continue
                if v in seen:
                    continue
                seen.add(v)
                out.append(f"%{v}%")
            return out
            
        cursor = self.conn.cursor()
        sql = "SELECT * FROM books WHERE 1=1"
        params = []
        
        # 通用关键词搜索 (标题/作者/标签) - 支持模糊搜索
        if query:
            
            # 模糊匹配逻辑: "魔圆" -> "%魔%圆%"
            # 移除空格以支持跨空格匹配 (如输入 "魔圆" 匹配 "魔 法 圆")
            clean_query = "".join(query.split())
            if clean_query:
                fuzzy_pattern = "%" + "%".join(list(clean_query)) + "%"
            else:
                fuzzy_pattern = f"%{query}%"
            
            # 尝试检测是否为 ID
            qid = None
            try:
                qid = int(query.strip())
            except Exception:
                pass

            if qid is not None:
                sql += " AND (title LIKE ? OR author LIKE ? OR tags LIKE ? OR id = ?)"
                params.extend([fuzzy_pattern, fuzzy_pattern, fuzzy_pattern, qid])
            else:
                sql += " AND (title LIKE ? OR author LIKE ? OR tags LIKE ?)"
                params.extend([fuzzy_pattern, fuzzy_pattern, fuzzy_pattern])
            
        # 精确/特定字段过滤
        if filters:
            for key, value in filters.items():
                if key == 'status':
                    sql += " AND status = ?"
                    params.append(value)
                elif key == 'file_type':
                    sql += " AND file_type LIKE ?" # 后缀不区分大小写
                    params.append(value)
                elif key == 'ids':
                    # value should be a list of integers
                    if value:
                        placeholders = ",".join("?" for _ in value)
                        sql += f" AND id IN ({placeholders})"
                        params.extend(value)
                elif key in ['author', 'series', 'tags', 'title']:
                    pats = _like_patterns(value)
                    if not pats:
                        continue
                    if len(pats) == 1:
                        sql += f" AND {key} LIKE ?"
                        params.append(pats[0])
                    else:
                        sql += " AND (" + " OR ".join([f"{key} LIKE ?"] * len(pats)) + ")"
                        params.extend(pats)
                    
        cursor.execute(sql, params)
        return cursor.fetchall()

    def get_stats(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM books')
        total_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT file_type, COUNT(*) FROM books GROUP BY file_type')
        type_counts = dict(cursor.fetchall())
        
        cursor.execute('SELECT author, COUNT(*) FROM books GROUP BY author ORDER BY COUNT(*) DESC LIMIT 5')
        top_authors = cursor.fetchall()

        cursor.execute('SELECT series, COUNT(*) FROM books WHERE series IS NOT NULL AND series != "" GROUP BY series ORDER BY COUNT(*) DESC LIMIT 5')
        top_series = cursor.fetchall()
        
        return {
            "total": total_count,
            "types": type_counts,
            "authors": top_authors,
            "series": top_series
        }

    def get_book(self, book_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM books WHERE id = ?', (book_id,))
        return cursor.fetchone()

    def delete_book(self, book_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM books WHERE id = ?', (book_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def clear_all(self):
        """Clear all data from the database."""
        cursor = self.conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute("DELETE FROM books")
            cursor.execute("DELETE FROM authors")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='books'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='authors'")
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    def update_book(self, book_id, **kwargs):
        if not kwargs:
            return False
        
        # 如果更新了作者，确保作者存在于 authors 表
        if 'author' in kwargs:
            self._ensure_author(kwargs['author'])
        
        columns = ", ".join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values())
        values.append(book_id)
        
        cursor = self.conn.cursor()
        cursor.execute(f'UPDATE books SET {columns} WHERE id = ?', values)
        self.conn.commit()
        return cursor.rowcount > 0

    def close(self):
        if self.conn:
            self.conn.close()
