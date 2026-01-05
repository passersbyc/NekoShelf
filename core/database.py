import sqlite3
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

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_file_hash ON books(file_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_books_file_path ON books(file_path)")
        
        self.conn.commit()

    def add_book(self, title, author, tags, status, series, file_path, file_type, file_hash=None):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO books (title, author, tags, status, series, file_path, file_hash, file_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (title, author, tags, status, series, file_path, file_hash, file_type))
        self.conn.commit()
        return cursor.lastrowid

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
            sql += " AND (title LIKE ? OR author LIKE ? OR tags LIKE ?)"
            
            # 模糊匹配逻辑: "魔圆" -> "%魔%圆%"
            # 移除空格以支持跨空格匹配 (如输入 "魔圆" 匹配 "魔 法 圆")
            clean_query = "".join(query.split())
            if clean_query:
                fuzzy_pattern = "%" + "%".join(list(clean_query)) + "%"
            else:
                fuzzy_pattern = f"%{query}%"
                
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

    def update_book(self, book_id, **kwargs):
        if not kwargs:
            return False
        
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
