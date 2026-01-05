import os
import shutil
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

        forbidden = set('<>:"/\\|?*')
        out = []
        for ch in s:
            if ch in forbidden:
                continue
            oc = ord(ch)
            if oc < 32:
                continue
            out.append(ch)
        return "".join(out).strip()

    def import_file(self, source_path, title, author, series=""):
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"找不到文件喵: {source_path}")

        safe_author = self._sanitize_component(author) or "佚名"
        safe_title = self._sanitize_component(title) or "未命名"
        
        # 创建作者目录
        author_dir = self.library_dir / safe_author
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

        # 目标文件路径
        extension = source.suffix
        dest_filename = f"{safe_title}{extension}"
        dest_path = dest_dir / dest_filename

        # 如果文件已存在，添加时间戳避免覆盖
        if dest_path.exists():
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            dest_filename = f"{safe_title}_{timestamp}{extension}"
            dest_path = dest_dir / dest_filename

        # 复制文件
        shutil.copy2(source, dest_path)
        return str(dest_path), extension.lstrip('.')

    def delete_file(self, file_path):
        path = Path(file_path)
        if path.exists():
            try:
                os.remove(path)
                # 尝试删除可能变空的目录 (系列目录 和 作者目录)
                parent = path.parent
                if parent != self.library_dir and not any(parent.iterdir()):
                    parent.rmdir()
                    grandparent = parent.parent
                    if grandparent != self.library_dir and not any(grandparent.iterdir()):
                        grandparent.rmdir()
                return True
            except Exception as e:
                print(f"删除文件失败喵: {e}")
                return False
        return False

    def move_book_file(self, current_path, new_title, new_author, new_series=""):
        # 1. 计算新的目标路径
        safe_author = self._sanitize_component(new_author) or "佚名"
        safe_title = self._sanitize_component(new_title) or "未命名"
        
        author_dir = self.library_dir / safe_author
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
        new_filename = f"{safe_title}{extension}"
        new_path = dest_dir / new_filename
        
        # 2. 如果路径没变，直接返回
        if current.resolve() == new_path.resolve():
            return str(new_path)
            
        # 3. 如果目标文件已存在，报错或者加时间戳 (这里选择加时间戳)
        if new_path.exists():
             timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
             new_filename = f"{safe_title}_{timestamp}{extension}"
             new_path = dest_dir / new_filename
             
        # 4. 移动文件
        if current.exists():
            shutil.move(current, new_path)
            # 清理旧目录
            try:
                old_parent = current.parent
                if old_parent != self.library_dir and not any(old_parent.iterdir()):
                    old_parent.rmdir()
                    old_grandparent = old_parent.parent
                    if old_grandparent != self.library_dir and not any(old_grandparent.iterdir()):
                        old_grandparent.rmdir()
            except:
                pass # 清理失败不影响主流程
            return str(new_path)
        else:
            raise FileNotFoundError(f"找不到原文件喵: {current_path}")
