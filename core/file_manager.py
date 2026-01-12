import os
import shutil
import hashlib
import datetime
from pathlib import Path
from .config import LIBRARY_DIR

class FileManager:
    def __init__(self, library_dir):
        self.library_dir = Path(library_dir)
        if not self.library_dir.exists():
            self.library_dir.mkdir(parents=True)

    def _sanitize_component(self, s):
        s = "" if s is None else str(s)
        s = s.strip()
        if not s:
            return ""

        table = {
            '/': '／',
            '\\': '＼',
            '?': '？',
            ':': '：',
            '*': '＊',
            '"': '＂',
            '<': '＜',
            '>': '＞',
            '|': '｜'
        }
        
        out = []
        for ch in s:
            # Check for control characters
            if ord(ch) < 32:
                continue
            out.append(table.get(ch, ch))
            
        return "".join(out).strip()

    def _resolve_author_dir(self, safe_author):
        # 1. 优先检查精确匹配
        exact_path = self.library_dir / safe_author
        if exact_path.exists():
            return exact_path
            
        # 2. 检查带前缀的目录 (例如: 【漫画】Author)
        # 遍历库目录，寻找以 safe_author 结尾且前缀合法的目录
        if self.library_dir.exists():
            for path in self.library_dir.iterdir():
                if path.is_dir():
                    name = path.name
                    if name.endswith(safe_author):
                        prefix = name[:-len(safe_author)]
                        # 如果前缀以 ] 或 】 结尾，视为同一作者目录
                        if prefix and (prefix.endswith('】') or prefix.endswith(']')):
                            return path
        
        # 3. 默认为精确路径 (如果不存在，后续会创建)
        return exact_path

    def _calculate_md5(self, file_path):
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except FileNotFoundError:
            return ""

    def _get_unique_path(self, directory, filename):
        base, ext = os.path.splitext(filename)
        counter = 1
        new_filename = filename
        dest_path = directory / new_filename
        
        while dest_path.exists():
            new_filename = f"{base} ({counter}){ext}"
            dest_path = directory / new_filename
            counter += 1
            
        return dest_path

    def _cleanup_empty_dirs(self, directory):
        try:
            if directory != self.library_dir and directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
                parent = directory.parent
                if parent != self.library_dir and parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
        except Exception:
            pass

    def import_file(self, source_path, title, author, series="", filename_pattern: str = ""):
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"找不到文件喵: {source_path}")

        safe_author = self._sanitize_component(author) or "佚名"
        safe_title = self._sanitize_component(title) or "未命名"
        
        # 确定作者目录 (自动识别现有带前缀的目录)
        author_dir = self._resolve_author_dir(safe_author)
        if not author_dir.exists():
            author_dir.mkdir(parents=True)

        # 确定目标目录 (默认为作者目录，如果有系列则创建系列子目录)
        dest_dir = author_dir
        if series:
            safe_series = self._sanitize_component(series)
            if safe_series:
                dest_dir = author_dir / safe_series
                if not dest_dir.exists():
                    dest_dir.mkdir(parents=True)

        extension = source.suffix

        base_name = safe_title
        pat = "" if filename_pattern is None else str(filename_pattern).strip()
        if pat:
            try:
                raw_base = pat.format(title=title, author=author, series=series, ext=extension.lstrip("."))
            except Exception:
                raw_base = title
            base_name = self._sanitize_component(raw_base) or safe_title

        dest_filename = f"{base_name}{extension}"
        dest_path = dest_dir / dest_filename

        # 如果源文件和目标文件一致，直接返回
        try:
            if source.resolve() == dest_path.resolve():
                return str(dest_path), extension.lstrip('.')
        except Exception:
            pass

        # 如果文件已存在，检查内容
        if dest_path.exists():
            # 内容一致，跳过
            if self._calculate_md5(source) == self._calculate_md5(dest_path):
                return str(dest_path), extension.lstrip('.')
            
            # 内容不一致，获取唯一文件名
            dest_path = self._get_unique_path(dest_dir, dest_filename)

        # 复制文件
        shutil.copy2(source, dest_path)
        return str(dest_path), extension.lstrip('.')

    def delete_file(self, file_path):
        path = Path(file_path)
        if path.exists():
            try:
                os.remove(path)
                self._cleanup_empty_dirs(path.parent)
                return True
            except Exception as e:
                print(f"删除文件失败喵: {e}")
                return False
        return False

    def clear_library(self):
        """Clear all files in the library directory."""
        if not self.library_dir.exists():
            return True
            
        try:
            for item in self.library_dir.iterdir():
                if item.is_file():
                    os.remove(item)
                elif item.is_dir():
                    shutil.rmtree(item)
            return True
        except Exception as e:
            print(f"清空书库失败喵: {e}")
            return False

    def move_book_file(self, current_path, new_title, new_author, new_series="", filename_pattern: str = ""):
        # 1. 计算新的目标路径
        safe_author = self._sanitize_component(new_author) or "佚名"
        safe_title = self._sanitize_component(new_title) or "未命名"
        
        author_dir = self._resolve_author_dir(safe_author)
        if not author_dir.exists():
            author_dir.mkdir(parents=True)
            
        dest_dir = author_dir
        if new_series:
            safe_series = self._sanitize_component(new_series)
            if safe_series:
                dest_dir = author_dir / safe_series
                if not dest_dir.exists():
                    dest_dir.mkdir(parents=True)
        
        current = Path(current_path)
        extension = current.suffix

        base_name = safe_title
        pat = "" if filename_pattern is None else str(filename_pattern).strip()
        if pat:
            try:
                raw_base = pat.format(title=new_title, author=new_author, series=new_series, ext=extension.lstrip("."))
            except Exception:
                raw_base = new_title
            base_name = self._sanitize_component(raw_base) or safe_title

        new_filename = f"{base_name}{extension}"
        new_path = dest_dir / new_filename
        
        # 2. 如果路径没变，直接返回
        if current.resolve() == new_path.resolve():
            return str(new_path)
            
        # 3. 如果目标文件已存在
        if new_path.exists():
             # 检查内容是否一致
             if self._calculate_md5(current) == self._calculate_md5(new_path):
                 # 内容一致，直接删除源文件，返回目标路径
                 try:
                     os.remove(current)
                     self._cleanup_empty_dirs(current.parent)
                 except:
                     pass
                 return str(new_path)
             
             # 内容不一致，重命名目标路径
             new_path = self._get_unique_path(dest_dir, new_filename)
             
        # 4. 移动文件
        if current.exists():
            shutil.move(current, new_path)
            self._cleanup_empty_dirs(current.parent)
            return str(new_path)
        else:
            raise FileNotFoundError(f"找不到原文件喵: {current_path}")
