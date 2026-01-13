import sqlite3
import datetime
import os
from .config import DB_FILE
from typing import Optional

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self._suspend_commit = False
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
                file_size INTEGER,
                file_mtime REAL,
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

        if 'file_size' not in columns:
            cursor.execute("ALTER TABLE books ADD COLUMN file_size INTEGER")

        if 'file_mtime' not in columns:
            cursor.execute("ALTER TABLE books ADD COLUMN file_mtime REAL")

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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS download_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                work_id TEXT NOT NULL,
                author TEXT NOT NULL,
                title TEXT NOT NULL,
                download_date TIMESTAMP NOT NULL,
                file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                source_url TEXT,
                book_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(platform, work_id)
            )
        ''')

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_download_records_platform_work ON download_records(platform, work_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_download_records_file_hash ON download_records(file_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_download_records_book_id ON download_records(book_id)")

        # 创建 subscriptions 表 (追更功能)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                alias TEXT,
                last_check TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建 posts 表 (存储作品元数据)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                work_id TEXT NOT NULL,
                author TEXT NOT NULL,
                title TEXT,
                content TEXT,
                tags TEXT,
                published_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(platform, work_id)
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_platform_work ON posts(platform, work_id)")

        # 创建 resources 表 (存储作品包含的文件资源)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                file_url TEXT,
                file_path TEXT,
                file_hash TEXT,
                file_size INTEGER,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_resources_post_id ON resources(post_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_resources_file_hash ON resources(file_hash)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_resources_post_file ON resources(post_id, file_path)")

        self.conn.commit()

    def add_subscription(self, url, alias=None):
        cursor = self.conn.cursor()
        try:
            cursor.execute("INSERT INTO subscriptions (url, alias) VALUES (?, ?)", (url, alias))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def is_subscribed(self, url):
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM subscriptions WHERE url = ?", (url,))
        return cursor.fetchone() is not None

    def remove_subscription(self, url):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM subscriptions WHERE url = ?", (url,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_subscriptions(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM subscriptions ORDER BY created_at DESC")
        return cursor.fetchall()

    def update_subscription_last_check(self, url):
        cursor = self.conn.cursor()
        now = datetime.datetime.now()
        cursor.execute("UPDATE subscriptions SET last_check = ? WHERE url = ?", (now, url))
        self.conn.commit()

    def update_subscription_alias(self, url, alias):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE subscriptions SET alias = ? WHERE url = ?", (alias, url))
        self.conn.commit()
        return cursor.rowcount > 0

    def _commit_if_needed(self):
        try:
            if self.conn is None:
                return
        except Exception:
            return

        try:
            if getattr(self, "_suspend_commit", False):
                return
        except Exception:
            pass
        try:
            self.conn.commit()
        except Exception:
            pass

    def _ensure_author(self, name):
        if not name:
            return
        try:
            cursor = self.conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO authors (name) VALUES (?)', (name,))
            self._commit_if_needed()
        except Exception:
            pass

    def add_book(self, title, author, tags, status, series, file_path, file_type, file_hash=None, import_date=None):
        if import_date is None:
            import_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        file_size = None
        file_mtime = None
        try:
            if file_path and os.path.exists(file_path):
                st = os.stat(file_path)
                file_size = int(st.st_size)
                file_mtime = float(st.st_mtime)
        except Exception:
            file_size = None
            file_mtime = None

        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO books (title, author, tags, status, series, file_path, file_hash, file_size, file_mtime, file_type, import_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (title, author, tags, status, series, file_path, file_hash, file_size, file_mtime, file_type, import_date))
        self._commit_if_needed()
        
        # 确保作者存在于 authors 表
        self._ensure_author(author)
        # 同步更新作者的最后导入时间
        self.update_author_import_date(author, import_date)
        
        return cursor.lastrowid

    def add_download_record(
        self,
        platform: str,
        work_id: str,
        author: str,
        title: str,
        local_path: str,
        file_hash: str = "",
        source_url: str = "",
        book_id: Optional[int] = None
    ):
        """兼容性别名：add_download_record -> upsert_download_record"""
        # 如果调用者没有提供 file_hash，这里尝试计算一下，或者留空
        if not file_hash and local_path and os.path.exists(local_path):
             # 避免在这里引入太多依赖，简单处理，或者留空
             # 真正的 hash 计算通常在 DownloadManager 或 ImportEngine 中
             pass

        # 构造 download_date
        download_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return self.upsert_download_record(
            platform=platform,
            work_id=work_id,
            author=author,
            title=title,
            download_date=download_date,
            file_path=local_path,
            file_hash=file_hash or "PENDING", # 临时占位，避免插入失败
            source_url=source_url,
            book_id=book_id
        )

    def upsert_download_record(
        self,
        platform: str,
        work_id: str,
        author: str,
        title: str,
        download_date: str,
        file_path: str,
        file_hash: str,
        source_url: str = "",
        book_id: Optional[int] = None,
    ):
        platform = "" if platform is None else str(platform).strip().lower()
        work_id = "" if work_id is None else str(work_id).strip()
        author = "" if author is None else str(author).strip()
        title = "" if title is None else str(title).strip()
        download_date = "" if download_date is None else str(download_date).strip()
        file_path = "" if file_path is None else str(file_path).strip()
        file_hash = "" if file_hash is None else str(file_hash).strip()
        source_url = "" if source_url is None else str(source_url).strip()

        if not platform or not work_id or not author or not title or not download_date or not file_path or not file_hash:
            return False

        cursor = self.conn.cursor()
        cursor.execute(
            '''
            INSERT INTO download_records (platform, work_id, author, title, download_date, file_path, file_hash, source_url, book_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform, work_id) DO UPDATE SET
                author=excluded.author,
                title=excluded.title,
                download_date=excluded.download_date,
                file_path=excluded.file_path,
                file_hash=excluded.file_hash,
                source_url=excluded.source_url,
                book_id=excluded.book_id
            ''',
            (platform, work_id, author, title, download_date, file_path, file_hash, source_url, book_id),
        )
        self._commit_if_needed()
        return True

    def get_download_record(self, platform: str, work_id: str):
        platform = "" if platform is None else str(platform).strip().lower()
        work_id = "" if work_id is None else str(work_id).strip()
        if not platform or not work_id:
            return None
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT * FROM download_records WHERE platform = ? AND work_id = ? LIMIT 1',
            (platform, work_id),
        )
        return cursor.fetchone()

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
        self._commit_if_needed()

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
        self._commit_if_needed()
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
        self._commit_if_needed()
        return cursor.rowcount > 0

    def clear_all(self):
        """Clear all data from the database."""
        cursor = self.conn.cursor()
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.execute("DELETE FROM books")
            cursor.execute("DELETE FROM authors")
            cursor.execute("DELETE FROM subscriptions")
            cursor.execute("DELETE FROM download_records")
            cursor.execute("DELETE FROM posts")
            cursor.execute("DELETE FROM resources")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='books'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='authors'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='subscriptions'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='download_records'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='posts'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='resources'")
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    def upsert_post(self, platform, work_id, author, title=None, content=None, tags=None, published_at=None):
        platform = "" if platform is None else str(platform).strip().lower()
        work_id = "" if work_id is None else str(work_id).strip()
        
        if not platform or not work_id:
            return None
            
        cursor = self.conn.cursor()
        
        # 检查是否存在
        cursor.execute('SELECT id FROM posts WHERE platform = ? AND work_id = ?', (platform, work_id))
        row = cursor.fetchone()
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if row:
            post_id = row['id']
            cursor.execute('''
                UPDATE posts 
                SET author = ?, title = ?, content = ?, tags = ?, published_at = ?, updated_at = ?
                WHERE id = ?
            ''', (author, title, content, tags, published_at, now, post_id))
        else:
            cursor.execute('''
                INSERT INTO posts (platform, work_id, author, title, content, tags, published_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (platform, work_id, author, title, content, tags, published_at, now, now))
            post_id = cursor.lastrowid
            
        self._commit_if_needed()
        return post_id

    def add_resource(self, post_id, file_path, file_url=None, file_hash=None, file_size=None):
        if not post_id or not file_path:
            return False
            
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO resources (post_id, file_path, file_url, file_hash, file_size)
            VALUES (?, ?, ?, ?, ?)
        ''', (post_id, file_path, file_url, file_hash, file_size))
        self._commit_if_needed()
        return True

    def get_post(self, platform, work_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM posts WHERE platform = ? AND work_id = ?', (platform, work_id))
        return cursor.fetchone()

    def get_post_resources(self, post_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM resources WHERE post_id = ?', (post_id,))
        return cursor.fetchall()

    def update_book(self, book_id, **kwargs):
        if not kwargs:
            return False
        
        # 如果更新了作者，确保作者存在于 authors 表
        if 'author' in kwargs:
            self._ensure_author(kwargs['author'])
        
        if "file_path" in kwargs and ("file_size" not in kwargs or "file_mtime" not in kwargs):
            try:
                fp = kwargs.get("file_path")
                if fp and os.path.exists(fp):
                    st = os.stat(fp)
                    if "file_size" not in kwargs:
                        kwargs["file_size"] = int(st.st_size)
                    if "file_mtime" not in kwargs:
                        kwargs["file_mtime"] = float(st.st_mtime)
            except Exception:
                pass

        columns = ", ".join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values())
        values.append(book_id)
        
        cursor = self.conn.cursor()
        cursor.execute(f'UPDATE books SET {columns} WHERE id = ?', values)
        self._commit_if_needed()
        return cursor.rowcount > 0

    def close(self):
        if self.conn:
            self.conn.close()
