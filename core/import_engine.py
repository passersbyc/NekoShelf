import hashlib
import os
import re
import shlex
import shutil

from .utils import Colors


class ImportEngine:
    def __init__(self, db, fm, import_exts=None, import_config=None):
        self.db = db
        self.fm = fm
        self.import_exts = set(import_exts or {".txt", ".pdf", ".doc", ".docx", ".epub"})
        self.import_config = import_config

    def get_import_config(self):
        cfg = {}
        try:
            cfg = dict(self.import_config or {})
        except Exception:
            cfg = {}

        defaults = {}
        try:
            defaults = dict(cfg.get("defaults") or {})
        except Exception:
            defaults = {}

        return {
            "recursive": bool(cfg.get("recursive", False)),
            "dry_run": bool(cfg.get("dry_run", False)),
            "delete_mode": str(cfg.get("delete_mode", "keep") or "keep"),
            "dup_mode": str(cfg.get("dup_mode", "ask") or "ask"),
            "parent_as_series_mode": str(cfg.get("parent_as_series_mode", "ask") or "ask"),
            "defaults": {
                "title": str(defaults.get("title", "") or ""),
                "author": str(defaults.get("author", "") or ""),
                "tags": str(defaults.get("tags", "") or ""),
                "status": defaults.get("status", None),
                "series": str(defaults.get("series", "") or ""),
            },
        }

    def file_hash(self, file_path, algo="sha256"):
        try:
            h = hashlib.new(algo)
        except Exception:
            h = hashlib.sha256()

        try:
            with open(file_path, "rb") as f:
                while True:
                    buf = f.read(1024 * 1024)
                    if not buf:
                        break
                    h.update(buf)
        except Exception:
            return ""
        return h.hexdigest()

    def abs_norm(self, p):
        try:
            return os.path.normpath(os.path.abspath(str(p)))
        except Exception:
            return str(p)

    def pick_duplicate_action(self, fp, dup_book, ask_choice=None):
        if ask_choice in {"skip_all", "import_all"}:
            return (ask_choice == "import_all"), ask_choice

        bid = dup_book["id"] if dup_book is not None and "id" in dup_book.keys() else "?"
        title = dup_book["title"] if dup_book is not None and "title" in dup_book.keys() else ""
        author = dup_book["author"] if dup_book is not None and "author" in dup_book.keys() else ""
        series = dup_book["series"] if dup_book is not None and "series" in dup_book.keys() else ""
        file_path = dup_book["file_path"] if dup_book is not None and "file_path" in dup_book.keys() else ""
        series_info = f" [系列: {Colors.cyan(series)}]" if series else ""

        print(Colors.yellow("发现重复导入候选喵~"))
        print(
            f"  现有记录: [{Colors.yellow(str(bid))}] {Colors.BOLD}{title}{Colors.RESET} - {Colors.green(author)}{series_info}"
        )
        if file_path:
            print(Colors.cyan(f"  已归档: {file_path}"))
        print(Colors.cyan(f"  本次来源: {fp}"))
        ans = input(Colors.pink("选择: [s]跳过 [i]仍导入 [a]以后都导入 [n]以后都跳过 > ")).strip().lower()
        if ans in {"i", "import"}:
            return True, ask_choice
        if ans in {"a", "all"}:
            return True, "import_all"
        if ans in {"n", "none"}:
            return False, "skip_all"
        return False, ask_choice

    def looks_like_part_suffix(self, suffix):
        s = (suffix or "").strip()
        if not s:
            return False
        if len(s) > 12:
            return False

        if s.isdigit():
            return True

        if s in {"上", "中", "下", "番外", "外传", "后日谈", "序章", "终章", "终"}:
            return True

        low = s.lower()
        if re.fullmatch(r"(?:v|vol|vol\.|ep|ep\.|ch|ch\.)\d{1,4}", low):
            return True

        if re.fullmatch(r"\d{1,4}(?:章|话|回|节|卷|集)?", s):
            return True

        if re.fullmatch(r"\d{1,4}\s*[-~～至]\s*\d{1,4}(?:章|话|回|节|卷|集)?", s):
            return True

        if re.fullmatch(r"第?[一二三四五六七八九十百千零〇两]{1,8}(?:章|话|回|节|卷|集)", s):
            return True

        if re.fullmatch(r"[A-Za-z]{1,4}\d{1,4}", s):
            return True

        if re.fullmatch(r"[\u4e00-\u9fff]{1,4}\d{1,4}", s):
            return True

        if re.fullmatch(r"[\u4e00-\u9fff]{1,4}\d{1,4}\s*[-~～至]\s*[\u4e00-\u9fff]{0,2}\d{1,4}", s):
            return True

        return False

    def normalize_tags(self, tags):
        if tags is None:
            return ""
        tags = str(tags).strip()
        if not tags:
            return ""
        tags = tags.replace("+", ",").replace("，", ",")
        parts = [p.strip() for p in tags.split(",") if p.strip()]
        return ",".join(parts)

    def parse_status(self, raw, default=0):
        if raw is None:
            return default
        s = str(raw).strip().lower()
        if s == "":
            return default
        if s.isdigit():
            v = int(s)
            if v in (0, 1):
                return v
            return default
        if s in {"完结", "已完结", "end", "done", "completed"}:
            return 1
        if s in {"连载", "未完结", "ongoing"}:
            return 0
        return default

    def infer_status_from_text(self, text, default=None):
        if not text:
            return default
        s = str(text).strip().lower()
        if not s:
            return default
        if any(k in s for k in ["全完结", "已完结", "完结", "完本", "完结篇", "the end", "completed"]):
            return 1
        if any(k in s for k in ["连载", "连载中", "更新中", "ongoing"]):
            return 0
        return default

    def strip_trailing_brackets(self, title):
        s = (title or "").strip()
        if not s:
            return "", ""

        removed = []
        pairs = [("【", "】"), ("[", "]"), ("(", ")"), ("（", "）")]
        changed = True
        while changed:
            changed = False
            ss = s.rstrip()
            for l, r in pairs:
                if ss.endswith(r):
                    li = ss.rfind(l)
                    if li != -1:
                        inner = ss[li + 1 : -len(r)]
                        if self.infer_status_from_text(inner, default=None) is not None:
                            removed.append(inner)
                            s = ss[:li].rstrip()
                            changed = True
                            break

        return s, " ".join(removed)

    def strip_trailing_id(self, title):
        s = (title or "").strip()
        if not s:
            return ""
        s2 = re.sub(r"\s*[\(（]\s*\d{3,20}\s*[\)）]\s*$", "", s).rstrip()
        return s2

    def infer_series_from_titlepart(self, title_part):
        s = (title_part or "").strip()
        if not s:
            return ""

        parts = s.rsplit(None, 1)
        if len(parts) != 2:
            return ""

        prefix, suffix = parts
        prefix = prefix.strip()
        suffix = suffix.strip()
        if not prefix or not suffix:
            return ""

        if self.looks_like_part_suffix(suffix):
            return prefix

        return ""

    def peek_text_head(self, file_path, max_chars=4096):
        try:
            with open(file_path, "rb") as f:
                raw = f.read(max_chars)
        except Exception:
            return ""

        for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
            try:
                return raw.decode(enc, errors="ignore")
            except Exception:
                continue
        return raw.decode(errors="ignore")

    def parse_text_header(self, text):
        meta = {"author": "", "tags": "", "title": "", "series": ""}
        if not text:
            return meta
            
        lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
        for ln in lines[:40]:
            low = ln.lower()
            
            # Author
            if not meta["author"] and (low.startswith("作者") or low.startswith("author")):
                if ":" in ln:
                    _, v = ln.split(":", 1)
                    meta["author"] = v.strip().strip("【】[]()（）")
                elif "：" in ln:
                    _, v = ln.split("：", 1)
                    meta["author"] = v.strip().strip("【】[]()（）")
            
            # Tags
            if not meta["tags"] and (low.startswith("标签") or low.startswith("tags")):
                if ":" in ln:
                    _, v = ln.split(":", 1)
                    meta["tags"] = v.strip()
                elif "：" in ln:
                    _, v = ln.split("：", 1)
                    meta["tags"] = v.strip()

            # Title
            if not meta["title"] and (low.startswith("标题") or low.startswith("title")):
                if ":" in ln:
                    _, v = ln.split(":", 1)
                    meta["title"] = v.strip()
                elif "：" in ln:
                    _, v = ln.split("：", 1)
                    meta["title"] = v.strip()

            # Series
            if not meta["series"] and (low.startswith("系列") or low.startswith("series")):
                if ":" in ln:
                    _, v = ln.split(":", 1)
                    meta["series"] = v.strip()
                elif "：" in ln:
                    _, v = ln.split("：", 1)
                    meta["series"] = v.strip()

            if all(meta.values()):
                break
        return meta

    def infer_author_tags_from_text(self, text):
        # Backward compatibility wrapper
        m = self.parse_text_header(text)
        return m["author"], m["tags"]

    def parse_cbz_metadata(self, file_path):
        """Extract metadata from ComicInfo.xml in CBZ/ZIP file."""
        import zipfile
        import xml.etree.ElementTree as ET
        
        meta = {"title": "", "author": "", "tags": "", "series": "", "status": None}
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                if 'ComicInfo.xml' in zf.namelist():
                    with zf.open('ComicInfo.xml') as f:
                        tree = ET.parse(f)
                        root = tree.getroot()
                        
                        # Map ComicInfo fields to our metadata
                        # Title
                        title = root.find('Title')
                        if title is not None and title.text:
                            meta['title'] = title.text.strip()
                            
                        # Author (Writer)
                        writer = root.find('Writer')
                        if writer is not None and writer.text:
                            meta['author'] = writer.text.strip()
                            
                        # Series
                        series = root.find('Series')
                        if series is not None and series.text:
                            meta['series'] = series.text.strip()
                            
                        # Tags
                        tags = root.find('Tags')
                        if tags is not None and tags.text:
                            meta['tags'] = tags.text.strip()
                            
                        # Summary (optional, not used in main meta yet but good to have)
                        
        except Exception:
            pass
            
        return meta

    def parse_title_series_from_titlepart(self, title_part):
        title_part = (title_part or "").strip()
        if not title_part:
            return "", ""
        cleaned, _ = self.strip_trailing_brackets(title_part)
        if cleaned:
            title_part = cleaned
        title_part = self.strip_trailing_id(title_part)
        series = self.infer_series_from_titlepart(title_part)
        return title_part, series

    def parse_metadata_from_filename(self, file_path):
        filename = os.path.basename(file_path)
        stem = os.path.splitext(filename)[0]

        # Try to match: Author - Title (ID) - OriginalName
        # or: Author - Title (ID)
        # Regex explanation:
        # ^\s*(?P<author>[^-_]+?)\s*-\s* -> Start with Author followed by " - " (exclude -_ to avoid splitting too early if author has them, but wait, author can have anything. 
        # Actually, let's just match the first " - " as separator)
        # (?P<title>.+?)               -> Capture Title (non-greedy)
        # \s*\(\d+\)                   -> Match (ID) e.g. (12345)
        # (?:\s*-\s*.+)?$              -> Optional suffix " - anything" (e.g. original filename)
        
        # We need to be specific to avoid false positives. The (ID) is the key signature of Kemono downloads.
        # Allow ID to be 'None' just in case, and capture the original filename suffix
        m_kemono = re.match(r"^\s*(?P<author>.+?)\s*-\s*(?P<title>.+?)\s*\((?P<id>\d+|None)\)(?:\s*-\s*(?P<original>.+))?$", stem)
        if m_kemono:
             author = m_kemono.group("author").strip()
             title = m_kemono.group("title").strip()
             original = m_kemono.group("original")
             
             # If title is "Untitled" and we have an original filename, use that instead
             if title.lower() == "untitled" and original:
                 title = original.strip()

             # Try to parse series from title if possible
             # Fix: If title contains series like "[Series] Title", parse_title_series_from_titlepart will handle it
             # But if title is just "Title", it returns "Title", ""
             # However, parse_title_series_from_titlepart might be too aggressive if the title is "[Work] Sketch" and we expect "Sketch" with series "Work"
             # Let's verify parse_title_series_from_titlepart logic.
             # It calls strip_trailing_brackets first.
             # If title is "[Work] Sketch", strip_trailing_brackets won't touch leading brackets.
             # infer_series_from_titlepart splits by space and checks last part. 
             # Wait, parse_title_series_from_titlepart logic:
             # cleaned, _ = self.strip_trailing_brackets(title_part) -> removes trailing brackets
             # strip_trailing_id -> removes trailing (ID)
             # infer_series_from_titlepart -> looks for "Title Part 1" pattern
             
             # It seems parse_title_series_from_titlepart DOES NOT handle "[Series] Title" format.
             # The "[Series] Title" logic is inside parse_metadata_from_filename (lines 379-382 in original file)
             
             # So we should replicate that logic here.
             
             series = ""
             # Check for [Series] Title format inside the extracted title
             m_series = re.match(r"^\s*[\[【](?P<series>.+?)[\]】]\s*(?P<title>.+)$", title)
             if m_series:
                 series = m_series.group("series").strip()
                 title = m_series.group("title").strip()
             else:
                 # Fallback to suffix series logic
                 t2, s2 = self.parse_title_series_from_titlepart(title)
                 if s2:
                     title = t2
                     series = s2

             return {"title": title, "series": series, "author": author, "tags": "", "status": None}

        parts = stem.split("_")

        if len(parts) < 2:
            m = re.match(r"^\s*(?P<author>.+?)\s*[-－—]\s*(?P<title>.+?)\s*$", stem)
            if m:
                author = (m.group("author") or "").strip()
                title_raw = (m.group("title") or "").strip()
                title_raw = self.strip_trailing_id(title_raw)
                title, series = self.parse_title_series_from_titlepart(title_raw)
                return {"title": title, "series": series, "author": author, "tags": "", "status": None}
            
            # Check for [Series] Title format
            series = ""
            title = stem
            # Match [Series] Title
            m_series = re.match(r"^\s*[\[【](?P<series>.+?)[\]】]\s*(?P<title>.+)$", stem)
            if m_series:
                series = m_series.group("series").strip()
                title = m_series.group("title").strip()
            
            # Still strip trailing ID from title
            title = self.strip_trailing_id(title)
            
            # Try to infer series if not found (e.g. trailing Part 1)
            if not series:
                 t2, s2 = self.parse_title_series_from_titlepart(title)
                 if s2:
                     title = t2
                     series = s2

            return {"title": title, "series": series, "author": "", "tags": "", "status": None}

        raw_title = parts[0]
        title, series = self.parse_title_series_from_titlepart(raw_title)
        author = (parts[1] or "").strip()

        tags = ""
        status = None

        if len(parts) >= 3:
            part3 = (parts[2] or "").strip()
            maybe_status = self.parse_status(part3, default=None)
            if maybe_status is not None and len(parts) == 3:
                status = maybe_status
            else:
                tags = self.normalize_tags(part3)

        if len(parts) >= 4:
            status = self.parse_status(parts[3], default=status)

        # Try to read internal metadata for CBZ/ZIP
        ext = os.path.splitext(file_path)[1].lower()
        if ext in {'.cbz', '.zip'}:
            cbz_meta = self.parse_cbz_metadata(file_path)
            # Merge: prefer CBZ metadata if present
            if cbz_meta['title']: title = cbz_meta['title']
            if cbz_meta['author']: author = cbz_meta['author']
            if cbz_meta['series']: series = cbz_meta['series']
            if cbz_meta['tags']: tags = cbz_meta['tags']

        return {"title": title, "series": series, "author": author, "tags": tags, "status": status}

    def _strip_author_prefix(self, name):
        tag_prefixes = ("【小说+漫画】", "【小说】", "【漫画】")
        s = "" if name is None else str(name)
        for p in tag_prefixes:
            if s.startswith(p):
                return s[len(p) :].lstrip()
        return s

    def import_one(self, file_path, overrides=None, dry_run=False, dup_mode="ask", dup_choice=None, hash_cache=None):
        overrides = overrides or {}
        meta = self.parse_metadata_from_filename(file_path) or {}

        title = (overrides.get("title") or meta.get("title") or "").strip()
        author = (overrides.get("author") or meta.get("author") or "").strip()
        series = (overrides.get("series") or meta.get("series") or "").strip()
        tags = self.normalize_tags(overrides.get("tags") if "tags" in overrides else meta.get("tags", ""))
        status = None
        if "status" in overrides:
            status = self.parse_status(overrides.get("status"), default=0)
        else:
            meta_status = meta.get("status", None)
            if meta_status is not None:
                status = self.parse_status(meta_status, default=None)

        if not title:
            stem = os.path.splitext(os.path.basename(file_path))[0].strip()
            title = stem
            if stem and (not series and "series" not in overrides):
                series2 = self.infer_series_from_titlepart(stem)
                if series2:
                    series = series2

        if title and "title" not in overrides:
            cleaned_title, status_hint = self.strip_trailing_brackets(title)
            if cleaned_title:
                title = cleaned_title

            title = self.strip_trailing_id(title)

            if status is None and status_hint:
                status = self.infer_status_from_text(status_hint, default=None)

        if status is None:
            status = self.infer_status_from_text(title, default=None)

        # Try to enrich metadata from text content (header)
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".txt":
            head = self.peek_text_head(file_path)
            text_meta = self.parse_text_header(head)
            
            if "title" not in overrides and text_meta["title"]:
                title = text_meta["title"]
                
            if "author" not in overrides and (not author or author == "佚名") and text_meta["author"]:
                author = text_meta["author"]
                
            if "series" not in overrides and not series and text_meta["series"]:
                series = text_meta["series"]
                
            if "tags" not in overrides and not tags and text_meta["tags"]:
                tags = self.normalize_tags(text_meta["tags"])
                
            if status is None and head:
                status = self.infer_status_from_text(head, default=None)
        
        elif ext == ".cbz":
            cbz_meta = self.parse_cbz_metadata(file_path)
            
            if "title" not in overrides and cbz_meta["title"]:
                title = cbz_meta["title"]
                
            if "author" not in overrides and (not author or author == "佚名") and cbz_meta["author"]:
                author = cbz_meta["author"]
                
            if "series" not in overrides and not series and cbz_meta["series"]:
                series = cbz_meta["series"]
                
            if "tags" not in overrides and not tags and cbz_meta["tags"]:
                tags = self.normalize_tags(cbz_meta["tags"])

        try:
            lib_root = os.path.abspath(str(getattr(self.fm, "library_dir", "")))
        except Exception:
            lib_root = ""
        if lib_root:
            try:
                src_abs = os.path.abspath(file_path)
                if os.path.commonpath([src_abs, lib_root]) == lib_root:
                    rel = os.path.relpath(src_abs, lib_root)
                    pparts = rel.split(os.sep)
                    if len(pparts) >= 2:
                        if (not author or author == "佚名") and ("author" not in overrides) and not meta.get("author"):
                            author = self._strip_author_prefix(pparts[0])
                        if (not series) and ("series" not in overrides) and not meta.get("series") and len(pparts) >= 3:
                            series = pparts[1]
            except Exception:
                pass

        if not author:
            author = "佚名"

        if status is None:
            status = 0

        if not title:
            print(Colors.red(f"无法解析书籍信息喵: {os.path.basename(file_path)}"))
            print(Colors.yellow("请使用 --title 手动补全，或按规范命名文件喵~"))
            return False, False, dup_choice

        fp_raw = "" if file_path is None else str(file_path)
        fp_norm = os.path.normpath(fp_raw)
        fp_abs = self.abs_norm(fp_raw)
        file_hash = ""
        if hash_cache is not None and fp_abs in hash_cache:
            file_hash = hash_cache.get(fp_abs) or ""
        else:
            file_hash = self.file_hash(fp_abs)
            if hash_cache is not None:
                hash_cache[fp_abs] = file_hash

        dup_book = None
        try:
            by_path = self.db.find_books_by_file_path(fp_raw, limit=5)
            if not by_path and fp_norm != fp_raw:
                by_path = self.db.find_books_by_file_path(fp_norm, limit=5)
            if not by_path and fp_abs:
                by_path = self.db.find_books_by_file_path(fp_abs, limit=5)
            if by_path:
                dup_book = by_path[0]
        except Exception:
            dup_book = None

        if dup_book is None and file_hash:
            try:
                by_hash = self.db.find_books_by_file_hash(file_hash, limit=5)
                if by_hash:
                    dup_book = by_hash[0]
            except Exception:
                dup_book = None

        if dup_book is None:
            try:
                cands = self.db.find_books_by_signature(title, author, series, limit=20)
            except Exception:
                cands = []
            for b in cands:
                try:
                    bh = b["file_hash"] if "file_hash" in b.keys() else ""
                except Exception:
                    bh = ""
                if bh and file_hash and bh == file_hash:
                    dup_book = b
                    break

                bp = ""
                try:
                    bp = b["file_path"] if "file_path" in b.keys() else ""
                except Exception:
                    bp = ""
                if not bp or not os.path.exists(bp) or not file_hash:
                    continue

                bp_abs = self.abs_norm(bp)
                if hash_cache is not None and bp_abs in hash_cache:
                    bh2 = hash_cache.get(bp_abs) or ""
                else:
                    bh2 = self.file_hash(bp_abs)
                    if hash_cache is not None:
                        hash_cache[bp_abs] = bh2
                if bh2 and bh2 == file_hash:
                    dup_book = b
                    try:
                        bid = b["id"] if "id" in b.keys() else None
                        if bid is not None:
                            self.db.update_book(int(bid), file_hash=file_hash)
                    except Exception:
                        pass
                    break

        if dup_book is not None:
            if dry_run:
                print(Colors.yellow("预览发现重复，默认跳过喵~"))
                try:
                    bid = dup_book["id"]
                    print(Colors.cyan(f"  已存在记录 ID: {bid}"))
                except Exception:
                    pass
                print(Colors.yellow(f"  源文件: {file_path}"))
                return True, True, dup_choice

            if dup_mode == "skip":
                print(Colors.yellow("发现重复导入，已跳过喵~"))
                try:
                    bid = dup_book["id"]
                    print(Colors.cyan(f"  已存在记录 ID: {bid}"))
                except Exception:
                    pass
                return True, True, dup_choice

            if dup_mode == "ask":
                do_imp, dup_choice = self.pick_duplicate_action(file_path, dup_book, ask_choice=dup_choice)
                if not do_imp:
                    print(Colors.cyan("本次重复已跳过喵~"))
                    return True, True, dup_choice

        if dry_run:
            status_str = "已完结" if status == 1 else "连载中"
            series_info = f" [系列: {series}]" if series else ""
            print(Colors.cyan(f"预览导入: {title} (作者: {author}) {status_str}{series_info} [{tags}]"))
            print(Colors.yellow(f"  源文件: {file_path}"))
            return True, False, dup_choice

        print(Colors.cyan(f"正在搬运书籍: {title} (作者: {author})..."))
        saved_path, file_type = self.fm.import_file(file_path, title, author, series)
        self.db.add_book(title, author, tags, status, series, saved_path, file_type, file_hash=file_hash)
        status_str = "已完结" if status == 1 else "连载中"
        series_info = f" [系列: {series}]" if series else ""
        print(Colors.green(f"成功归档喵！状态: {status_str}{series_info}, 已存入: {saved_path}"))
        return True, False, dup_choice

    def iter_import_files(self, path, recursive=False):
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in self.import_exts:
                yield path
            return
        if not os.path.isdir(path):
            return

        if recursive:
            for root, _, files in os.walk(path):
                for name in files:
                    ext = os.path.splitext(name)[1].lower()
                    if ext in self.import_exts:
                        yield os.path.join(root, name)
        else:
            for name in os.listdir(path):
                full = os.path.join(path, name)
                if os.path.isfile(full):
                    ext = os.path.splitext(name)[1].lower()
                    if ext in self.import_exts:
                        yield full

    def looks_like_flagged_invocation(self, raw):
        return bool(re.search(r"\s--\w", raw or ""))

    def try_parse_as_single_path(self, raw):
        raw = (raw or "").strip()
        if not raw:
            return ""
        if self.looks_like_flagged_invocation(raw):
            return ""
        if os.path.exists(raw):
            return raw
        return ""

    def parse_import_tokens(self, tokens, defaults=None):
        defaults = defaults or {}

        overrides = {}
        recursive = bool(defaults.get("recursive", False))
        dry_run = bool(defaults.get("dry_run", False))
        delete_mode = str(defaults.get("delete_mode", "keep") or "keep")
        dup_mode = str(defaults.get("dup_mode", "ask") or "ask")
        parent_as_series = bool(defaults.get("parent_as_series", True))
        paths = []

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token == "--recursive":
                recursive = True
                i += 1
                continue
            if token == "--dry-run":
                dry_run = True
                i += 1
                continue
            if token == "--dup-mode":
                if i + 1 < len(tokens):
                    dup_mode = tokens[i+1]
                    i += 2
                    continue
                else:
                    # Handle --dup-mode=skip format if needed, but simple split handles it usually?
                    # wait, self.tokenize might split it.
                    # Assuming parse_args style.
                    pass
            
            # Support --dup-mode=value
            if token.startswith("--dup-mode="):
                dup_mode = token.split("=", 1)[1]
                i += 1
                continue

            if token == "--delete-source":
                delete_mode = "always"
                i += 1
                continue
            if token == "--ask-delete":
                delete_mode = "ask"
                i += 1
                continue
            if token == "--keep-source":
                delete_mode = "keep"
                i += 1
                continue

            if token == "--skip-dup":
                dup_mode = "skip"
                i += 1
                continue
            if token == "--import-dup":
                dup_mode = "import"
                i += 1
                continue
            if token == "--ask-dup":
                dup_mode = "ask"
                i += 1
                continue

            if token == "--parent-as-series":
                parent_as_series = True
                i += 1
                continue

            if token == "--no-parent-as-series":
                parent_as_series = False
                i += 1
                continue

            # Handle --key=value syntax for overrides
            handled_override = False
            for key in ("title", "author", "tags", "status", "series"):
                prefix = f"--{key}="
                if token.startswith(prefix):
                    overrides[key] = token[len(prefix):]
                    i += 1
                    handled_override = True
                    break
            if handled_override:
                continue

            if token in {"--title", "--author", "--tags", "--status", "--series"}:
                if i + 1 >= len(tokens):
                    raise ValueError(f"参数缺失喵: {token} 需要一个值")
                overrides[token[2:]] = tokens[i + 1]
                i += 2
                continue

            if token.startswith("--"):
                print(Colors.yellow(f"未知参数已忽略喵: {token}"))
                i += 1
                continue

            paths.append(token)
            i += 1

        return {
            "paths": paths,
            "overrides": overrides,
            "recursive": recursive,
            "dry_run": dry_run,
            "delete_mode": delete_mode,
            "dup_mode": dup_mode,
            "parent_as_series": parent_as_series,
        }

    def apply_legacy_positional_overrides(self, parsed):
        paths = parsed["paths"]
        overrides = parsed["overrides"]

        if not paths or len(paths) < 3:
            return parsed

        if "title" in overrides or "author" in overrides:
            return parsed

        file_path = paths[0]
        if not os.path.isfile(file_path):
            return parsed

        title_raw = paths[1]
        author_raw = paths[2]
        tags_raw = paths[3] if len(paths) > 3 else ""

        if os.path.exists(title_raw):
            return parsed

        title, series = self.parse_title_series_from_titlepart(title_raw)
        merged = {
            "title": title,
            "author": author_raw,
            "tags": tags_raw,
            "series": overrides.get("series") or series,
            **{k: v for k, v in overrides.items() if k in {"status"}},
        }

        parsed["overrides"] = merged
        parsed["paths"] = [file_path]
        return parsed

    def should_delete_source(self, delete_mode, ask_choice):
        if delete_mode == "keep":
            return False, ask_choice
        if delete_mode == "always":
            return True, ask_choice
        if delete_mode != "ask":
            return False, ask_choice

        if ask_choice == "all":
            return True, ask_choice
        if ask_choice == "none":
            return False, ask_choice

        ans = input(Colors.pink("要删除源文件吗喵？(yes/no/all/none): ")).strip().lower()
        if ans in {"y", "yes"}:
            return True, ask_choice
        if ans in {"a", "all"}:
            return True, "all"
        if ans in {"none"}:
            return False, "none"
        return False, ask_choice

    def safe_delete_source(self, fp):
        try:
            lib_root = os.path.abspath(str(getattr(self.fm, "library_dir", "")))
        except Exception:
            lib_root = ""
        try:
            src_abs = os.path.abspath(fp)
        except Exception:
            src_abs = fp

        if lib_root:
            try:
                if os.path.commonpath([src_abs, lib_root]) == lib_root:
                    print(Colors.yellow(f"源文件已在藏书目录中，跳过删除喵: {fp}"))
                    return False
            except Exception:
                pass

        try:
            os.remove(fp)
            print(Colors.green(f"源文件已删除喵: {fp}"))
            return True
        except Exception as e:
            print(Colors.yellow(f"源文件删除失败喵: {fp} ({e})"))
            return False

    def safe_delete_dir(self, directory):
        """
        安全删除文件夹。
        
        会检查文件夹是否包含藏书目录，或者是否在藏书目录内，防止误删。
        只有当文件夹存在且通过安全检查时才会执行删除。
        """
        try:
            lib_root = os.path.abspath(str(getattr(self.fm, "library_dir", "")))
        except Exception:
            lib_root = ""
        
        try:
            dir_abs = os.path.abspath(directory)
        except Exception:
            dir_abs = directory
            
        if lib_root:
            try:
                # 检查是否为藏书目录或在藏书目录内
                if dir_abs == lib_root or os.path.commonpath([dir_abs, lib_root]) == lib_root:
                    print(Colors.yellow(f"文件夹在藏书目录中，跳过删除喵: {directory}"))
                    return False
                # 检查藏书目录是否在文件夹内 (防止误删父目录)
                if os.path.commonpath([dir_abs, lib_root]) == dir_abs:
                     print(Colors.yellow(f"藏书目录在文件夹内，跳过删除喵: {directory}"))
                     return False
            except Exception:
                pass
                
        try:
            if not os.path.exists(directory):
                return False
                
            shutil.rmtree(directory)
            print(Colors.green(f"源文件夹已删除喵: {directory}"))
            return True
        except Exception as e:
            print(Colors.yellow(f"源文件夹删除失败喵: {directory} ({e})"))
            return False

    def run(self, arg):
        try:
            cfg = self.get_import_config()
            cfg_defaults = cfg.get("defaults") or {}
            base_overrides = {}
            for k in ("title", "author", "tags", "series"):
                v = (cfg_defaults.get(k) or "").strip()
                if v:
                    base_overrides[k] = v
            if cfg_defaults.get("status", None) is not None:
                base_overrides["status"] = cfg_defaults.get("status")

            raw = (arg or "").strip()
            if not raw:
                print(Colors.red("请提供文件或文件夹路径喵！"))
                return

            single_path = self.try_parse_as_single_path(raw)
            if single_path:
                parsed = {
                    "paths": [single_path],
                    "overrides": dict(base_overrides),
                    "recursive": bool(cfg.get("recursive", False)),
                    "dry_run": bool(cfg.get("dry_run", False)),
                    "delete_mode": str(cfg.get("delete_mode", "keep") or "keep"),
                    "dup_mode": str(cfg.get("dup_mode", "ask") or "ask"),
                    "parent_as_series": True,
                }
            else:
                tokens = shlex.split(arg)
                if not tokens:
                    print(Colors.red("请提供文件或文件夹路径喵！"))
                    return

                try:
                    parsed = self.parse_import_tokens(
                        tokens,
                        defaults={
                            "recursive": bool(cfg.get("recursive", False)),
                            "dry_run": bool(cfg.get("dry_run", False)),
                            "delete_mode": str(cfg.get("delete_mode", "keep") or "keep"),
                            "dup_mode": str(cfg.get("dup_mode", "ask") or "ask"),
                            "parent_as_series": True,
                        },
                    )
                except ValueError as e:
                    print(Colors.red(str(e)))
                    return

                if not parsed["paths"]:
                    print(Colors.red("请提供文件或文件夹路径喵！"))
                    return

                parsed = self.apply_legacy_positional_overrides(parsed)

                if base_overrides:
                    merged = dict(base_overrides)
                    merged.update(parsed.get("overrides") or {})
                    parsed["overrides"] = merged

            paths = parsed["paths"]
            overrides = parsed["overrides"]
            recursive = parsed["recursive"]
            dry_run = parsed["dry_run"]
            delete_mode = parsed["delete_mode"]
            dup_mode = parsed.get("dup_mode", "ask")
            parent_as_series = bool(parsed.get("parent_as_series", False))
            parent_as_series_mode = str(cfg.get("parent_as_series_mode", "ask") or "ask").strip().lower()

            imported = 0
            failed = 0
            files_total = 0
            ask_choice = None
            dup_choice = None
            dup_skipped = 0
            hash_cache = {}

            for p in paths:
                if not os.path.exists(p):
                    print(Colors.red(f"找不到路径喵: {p}"))
                    failed += 1
                    continue
                
                is_directory = os.path.isdir(p)
                p_overrides = overrides
                if parent_as_series and is_directory and ("series" not in overrides):
                    try:
                        parent = os.path.basename(os.path.abspath(p)).strip()
                    except Exception:
                        parent = ""
                    if parent:
                        if parent_as_series_mode == "never":
                            pass
                        elif parent_as_series_mode == "always":
                            p_overrides = {**overrides, "series": parent}
                        else:
                            ans = input(
                                Colors.pink(f"要把文件夹名作为系列名吗喵？[{Colors.cyan(parent)}] (yes/no): ")
                            ).strip().lower()
                            if ans in {"y", "yes", ""}:
                                p_overrides = {**overrides, "series": parent}

                for fp in self.iter_import_files(p, recursive=recursive):
                    files_total += 1
                    ok, skipped_dup, dup_choice = self.import_one(
                        fp,
                        overrides=p_overrides,
                        dry_run=dry_run,
                        dup_mode=dup_mode,
                        dup_choice=dup_choice,
                        hash_cache=hash_cache,
                    )
                    if ok:
                        if skipped_dup:
                            dup_skipped += 1
                        else:
                            imported += 1
                        if not dry_run:
                            do_delete, ask_choice = self.should_delete_source(delete_mode, ask_choice)
                            if do_delete:
                                self.safe_delete_source(fp)
                    else:
                        failed += 1
                
                # 如果用户在删除提示中选择了 "all"，并且当前处理的是文件夹，则尝试删除整个文件夹
                if not dry_run and is_directory and ask_choice == "all":
                    self.safe_delete_dir(p)

            if files_total == 0:
                print(Colors.yellow("没有找到可导入的文件喵~ (支持: txt/pdf/doc/docx/epub)"))
                return

            if dry_run:
                extra = f"，重复跳过 {dup_skipped}" if dup_skipped else ""
                print(Colors.green(f"预览结束喵！可导入 {imported}/{files_total} 个文件{extra}。"))
            else:
                extra = f"，重复跳过 {dup_skipped}" if dup_skipped else ""
                print(Colors.green(f"导入完成喵！成功 {imported}/{files_total}，失败 {failed}{extra}。"))
        except Exception as e:
            print(Colors.red(f"出错了喵... {e}"))
