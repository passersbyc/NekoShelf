import os
import re
import time
import json
import shutil
import zipfile
import hashlib
import tempfile
import requests
import html
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional, Any
from tqdm import tqdm
from bs4 import BeautifulSoup

from core.utils import Colors
from core.database import DatabaseManager
from .base import DownloadPlugin
from .utils import sanitize_filename, set_file_time, create_cbz, create_pdf
from ... import config

class KemonoPlugin(DownloadPlugin):
    """
    Plugin for downloading novels and comics from Kemono.cr / Kemono.su
    Supports: Patreon, Fanbox, Fantia, etc. via Kemono.
    """
    
    BASE_URL = "https://kemono.cr"
    API_BASE = "https://kemono.cr/api/v1"
    
    def __init__(self):
        self.session = requests.Session()
        retries = requests.adapters.Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        # 优化: 增大连接池大小，避免并发下载时连接被回收
        adapter = requests.adapters.HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        
        self._refresh_config(reload=True)

    def _refresh_config(self, reload: bool = False):
        cfg = config.get_download_config(reload=reload)
        self.BASE_URL = str(cfg.get("kemono_base_url", "https://kemono.cr") or "https://kemono.cr")
        self.API_BASE = str(cfg.get("kemono_api_base", "https://kemono.cr/api/v1") or "https://kemono.cr/api/v1")
        self.MAX_WORKERS = int(cfg.get("max_workers", 5) or 5)
        self.TIMEOUT = int(cfg.get("timeout", 10) or 10)
        self.MAX_RETRIES = int(cfg.get("max_retries", 3) or 3)

        # 更新 Session 的重试策略
        retries = requests.adapters.Retry(
            total=self.MAX_RETRIES, 
            backoff_factor=1, 
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)

        headers = {
            "User-Agent": cfg.get("user_agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
            "Referer": self.BASE_URL,
            "Accept": "text/css",
        }
        cookie = cfg.get("kemono_cookie")
        if cookie:
            headers["Cookie"] = cookie
        else:
            if "Cookie" in self.session.headers:
                try:
                    del self.session.headers["Cookie"]
                except Exception:
                    pass

        self.session.headers.update(headers)
        return cfg

    @property
    def name(self) -> str:
        return "Kemono"

    def can_handle(self, url: str) -> bool:
        return re.search(r"kemono\.(cr|su|party)/(?P<service>\w+)/user/(?P<user_id>\d+)", url) is not None

    def get_artist_name(self, url: str) -> str:
        user_match = re.search(r"kemono\.(cr|su|party)/(?P<service>\w+)/user/(?P<user_id>\d+)", url)
        if user_match:
            service = user_match.group("service")
            user_id = user_match.group("user_id")
            return self._get_author_name(service, user_id)
        return ""

    def download(self, url: str, output_dir: str, **kwargs) -> tuple[bool, str, str]:
        db_instance = kwargs.get("db")
        self.db_path = db_instance.db_path if db_instance else None
        
        print(Colors.pink(f"正在解析 Kemono 链接喵: {url}"))
        
        post_match = re.search(r"kemono\.(cr|su|party)/(?P<service>\w+)/user/(?P<user_id>\d+)/post/(?P<post_id>\d+)", url)
        user_match = re.search(r"kemono\.(cr|su|party)/(?P<service>\w+)/user/(?P<user_id>\d+)", url)
        
        if post_match:
            return self._download_single_post_mode(post_match, output_dir, **kwargs)
        elif user_match:
            return self._download_user_mode(user_match, output_dir, **kwargs)
        else:
            return False, "链接格式不对喵... 需要类似 https://kemono.cr/patreon/user/12345 或 具体帖子链接", None

    def _download_single_post_mode(self, match, output_dir, **kwargs) -> tuple[bool, str, str]:
        cfg = self._refresh_config(reload=True)
        service = match.group("service")
        user_id = match.group("user_id")
        post_id = match.group("post_id")
        
        author_name = self._get_author_name(service, user_id)
        print(Colors.cyan(f"找到作者: {author_name} (ID: {user_id})"))
        
        base_dir = output_dir if output_dir else config.get_paths(reload=False)[0]
        author_dir = os.path.join(base_dir, sanitize_filename(author_name))
        os.makedirs(author_dir, exist_ok=True)
        
        print(Colors.pink(f"正在获取帖子 {post_id} 数据..."))
        post = self._get_single_post(service, user_id, post_id)
        if not post:
             return False, f"无法获取帖子数据 ({post_id})", None
             
        # Normalize post data
        if not post.get("service"): post["service"] = service
        if not post.get("user"): post["user"] = user_id
             
        config_save_content = bool(cfg.get("kemono_save_content", False))
        should_save_content = kwargs.get("save_content", False) or config_save_content
        dl_mode = kwargs.get("kemono_dl_mode", "attachment")
        
        success = self._download_post_safe(post, author_dir, author_name, should_save_content, dl_mode)
        
        project_temp = os.path.join(os.getcwd(), "temp_downloads")
        if os.path.exists(project_temp):
            try: 
                os.rmdir(project_temp)
            except: pass
            
        if success:
            return True, "单贴下载完成喵！", author_dir
        else:
            return False, "下载失败喵...", author_dir

    def _download_user_mode(self, match, output_dir, **kwargs) -> tuple[bool, str, str]:
        cfg = self._refresh_config(reload=True)
        service = match.group("service")
        user_id = match.group("user_id")
        
        author_name = self._get_author_name(service, user_id)
        print(Colors.cyan(f"找到作者: {author_name} (ID: {user_id})"))
        
        base_dir = output_dir if output_dir else config.get_paths(reload=False)[0]
        author_dir = os.path.join(base_dir, sanitize_filename(author_name))
        os.makedirs(author_dir, exist_ok=True)
        
        print(Colors.pink("正在获取帖子列表，可能需要一点时间喵..."))
        posts = self._get_all_posts(service, user_id)
        
        # 预先过滤已下载的帖子
        db = kwargs.get("db")
        local_db = None
        if not db and self.db_path:
            try:
                local_db = DatabaseManager(self.db_path)
                db = local_db
            except Exception:
                pass
        
        filtered_posts = []
        skipped_count = 0
        
        if db:
            print(Colors.pink("正在比对数据库记录喵..."))
            for post in posts:
                # Normalize post data in place
                if not post.get("service"): post["service"] = service
                if not post.get("user"): post["user"] = user_id
                
                p_service = post.get("service") or service
                p_user = post.get("user") or user_id
                p_id = post.get("id") or "0"
                work_sig = f"kemono:{p_service}:{p_user}:{p_id}".strip(":")
                
                rec = db.get_download_record("kemono", work_sig)
                if rec:
                    skipped_count += 1
                else:
                    # tqdm.write(Colors.dim(f"Check miss: {work_sig}"))
                    filtered_posts.append(post)
        else:
            # Still normalize posts even if no db
            for post in posts:
                if not post.get("service"): post["service"] = service
                if not post.get("user"): post["user"] = user_id
            filtered_posts = posts
            
        if local_db:
            try:
                local_db.conn.close()
            except Exception:
                pass

        if skipped_count > 0:
            print(Colors.green(f"共发现 {len(posts)} 个帖子，其中 {skipped_count} 个已存在，准备搬运 {len(filtered_posts)} 个新帖子喵！"))
        else:
            print(Colors.green(f"共发现 {len(posts)} 个帖子喵！准备开始搬运..."))
        
        posts = filtered_posts

        if not posts:
            return True, f"没有找到新帖子喵 (跳过 {skipped_count} 个)...", author_dir

        results = {'success': 0, 'fail': 0}
        
        config_save_content = bool(cfg.get("kemono_save_content", False))
        should_save_content = kwargs.get("save_content", False) or config_save_content
        dl_mode = kwargs.get("kemono_dl_mode", "attachment")
        
        self._process_batch(posts, author_dir, "Posts", 
                          lambda p, d: self._download_post_safe(p, d, author_name, should_save_content, dl_mode), results)
        
        project_temp = os.path.join(os.getcwd(), "temp_downloads")
        if os.path.exists(project_temp):
            try:
                os.rmdir(project_temp)
            except OSError:
                pass
                
        return True, f"下载完成喵！成功: {results['success']}, 失败: {results['fail']}", author_dir

    def _process_batch(self, items: List[Any], save_dir: str, desc: str, func, stats: Dict):
        tqdm.write(Colors.yellow(f"--- 开始处理 {len(items)} 个 {desc} ---"))
        with tqdm(total=len(items), unit="work", desc=f"Processing {desc}", leave=False) as pbar:
            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
                futures = {executor.submit(func, item, save_dir): item for item in items}
                
                for future in as_completed(futures):
                    try:
                        if future.result():
                            stats['success'] += 1
                        else:
                            stats['fail'] += 1
                    except Exception as e:
                        tqdm.write(Colors.red(f"任务执行异常: {e}"))
                        stats['fail'] += 1
                    finally:
                        pbar.update(1)

    def _download_post_safe(self, post: Dict, save_dir: str, author_name: str, save_content: bool = False, dl_mode: str = "attachment") -> bool:
        db = None
        try:
            if self.db_path:
                try:
                    db = DatabaseManager(self.db_path)
                except Exception as e:
                    tqdm.write(Colors.red(f"DB连接失败: {e}"))
                    pass
            
            return self._download_post(post, save_dir, author_name, save_content, dl_mode, db=db)
        except Exception as e:
            tqdm.write(Colors.red(f"帖子处理失败 ({post.get('id')}): {e}"))
            return False
        finally:
            if db:
                try:
                    db.conn.close()
                except Exception:
                    pass

    def _download_post(self, post: Dict, save_dir: str, author_name: str, save_content: bool = False, dl_mode: str = "attachment", db=None) -> bool:
        post_id = post.get("id") or "0"
        title = post.get("title", "Untitled") or "Untitled"

        service = post.get("service") or ""
        user_id = post.get("user") or ""
        post_id = post.get("id") or "0"
        work_sig = f"kemono:{service}:{user_id}:{post_id}".strip(":")
        
        # 1. 检查下载记录 (Download Record)
        if db:
            rec = db.get_download_record("kemono", work_sig)
            if rec:
                # tqdm.write(Colors.dim(f"发现下载记录，已跳过喵 ({work_sig})"))
                return True

        title = post.get("title", "Untitled") or "Untitled"
        safe_title = sanitize_filename(f"{author_name} - {title} ({work_sig})")
        
        content = post.get("content", "")
        attachments = post.get("attachments", [])
        file_info = post.get("file")
        
        targets = []
        if file_info: targets.append(file_info)
        if attachments: targets.extend(attachments)
        
        # tqdm.write(Colors.blue(f"初始附件数: {len(targets)}"))
        
        if content:
            # tqdm.write(Colors.blue(f"正在解析正文内容 (长度: {len(content)})..."))
            try:
                soup = BeautifulSoup(content, 'html.parser')
                imgs = soup.find_all('img')
                # tqdm.write(Colors.blue(f"正文中发现 {len(imgs)} 个 img 标签"))
                
                for img in imgs:
                    src = img.get('src')
                    if not src: continue
                    if src.startswith('/'):
                        src = f"{self.BASE_URL}{src}"
                        
                    if any(t.get('path') == src for t in targets):
                        continue
                        
                    fname = os.path.basename(src.split('?')[0])
                    targets.append({
                        "path": src,
                        "name": fname
                    })
            except Exception as e:
                tqdm.write(Colors.red(f"正文解析失败: {e}"))
        
        has_attachments = len(targets) > 0
        
        if dl_mode == "txt":
            if content:
                 self._save_novel(post, save_dir, safe_title, author_name)
            return True

        if dl_mode == "image":
            if has_attachments:
                return self._process_attachments(post, targets, save_dir, safe_title, author_name, dl_mode="image", db=db)
            return True

        if content and save_content:
            novel_title = f"{safe_title}_content" if has_attachments else safe_title
            self._save_novel(post, save_dir, novel_title, author_name)
        
        if has_attachments:
            return self._process_attachments(post, targets, save_dir, safe_title, author_name, dl_mode="attachment", db=db)
            
        return True

    def _process_attachments(self, post: Dict, targets: List[Dict], save_dir: str, safe_title: str, author_name: str, dl_mode: str = "attachment", db=None) -> bool:
        cfg = config.get_download_config(reload=False)
        fmt = str(cfg.get("kemono_format", "pdf") or "pdf").lower()
        if fmt not in ["cbz", "pdf"]: fmt = "pdf"
        output_ext = f".{fmt}"
        output_path = os.path.join(save_dir, f"{safe_title}{output_ext}")
        
        packed_exists = os.path.exists(output_path) and os.path.getsize(output_path) > 0
        
        if not packed_exists:
            lib_author_dir = os.path.join(config.get_paths(reload=False)[0], sanitize_filename(author_name))
            lib_output_path = os.path.join(lib_author_dir, f"{safe_title}{output_ext}")
            if os.path.exists(lib_output_path) and os.path.getsize(lib_output_path) > 0:
                # tqdm.write(Colors.yellow(f"书库中已存在: {safe_title}{output_ext}，跳过下载喵~"))
                packed_exists = True
                
                # 补录下载记录
                if db:
                    try:
                        p_service = post.get("service") or ""
                        p_user = post.get("user") or ""
                        p_id = post.get("id") or "0"
                        work_id = f"kemono:{p_service}:{p_user}:{p_id}".strip(":")

                        db.upsert_download_record(
                            platform="kemono",
                            work_id=work_id,
                            author=author_name,
                            title=post.get('title', 'Untitled'),
                            download_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            file_path=lib_output_path,
                            file_hash="EXISTING_FILE_SKIPPED",
                            source_url=f"{self.BASE_URL}/{p_service}/user/{p_user}/post/{p_id}"
                        )
                        db.conn.commit()
                    except Exception as e:
                        tqdm.write(Colors.red(f"补录下载记录失败: {e}"))
                        pass

        files_to_download = []
        
        for t in targets:
            url = t.get("path", "")
            if not url: continue
            
            fname = t.get("name")
            url_clean = url.split('?')[0]
            
            if not fname:
                fname = os.path.basename(url_clean)
                
            ext = os.path.splitext(fname)[1].lower()
            if not ext:
                ext = os.path.splitext(os.path.basename(url_clean))[1].lower()
            if not ext: ext = ".jpg"
            
            is_image = ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
            
            if dl_mode == "attachment":
                if is_image: continue
            elif dl_mode == "image":
                if not is_image: continue
            
            if not is_image:
                safe_name = sanitize_filename(fname)
                if not safe_name: safe_name = f"attachment_{ext}"
                dest_path = os.path.join(save_dir, safe_name)
                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                    continue
                    
            files_to_download.append(t)
        
        if not files_to_download:
            if dl_mode == "image":
                 tqdm.write(Colors.yellow(f"警告: 在 Image 模式下未找到任何图片文件喵 (共扫描 {len(targets)} 个目标)~"))
            return True

        # tqdm.write(Colors.blue(f"准备下载 {len(files_to_download)} 个文件喵..."))
        
        results = []

        project_temp = os.path.join(os.getcwd(), "temp_downloads")
        os.makedirs(project_temp, exist_ok=True)
        
        with tempfile.TemporaryDirectory(prefix=f"kemono_{post.get('id')}_", dir=project_temp) as temp_dir:
            downloaded_files = self._download_images(files_to_download, temp_dir)
            # tqdm.write(Colors.blue(f"实际下载成功 {len(downloaded_files)} / {len(files_to_download)} 个文件喵"))
            
            self._extract_zips(temp_dir)
            
            final_images = self._scan_images(temp_dir)
            # tqdm.write(Colors.blue(f"扫描到有效图片 {len(final_images)} 张喵"))
            
            if final_images and not packed_exists:
                if fmt == "cbz":
                    create_cbz(
                        images=final_images,
                        output_path=output_path,
                        title=post.get('title', ''),
                        author=author_name,
                        description=BeautifulSoup(post.get('content', ''), 'html.parser').get_text(),
                        source_url=f"{self.BASE_URL}/{post.get('service')}/user/{post.get('user')}/post/{post.get('id')}",
                        tags=post.get("tags", []),
                        published_time=post.get("published")
                    )
                else:
                    create_pdf(
                        images=final_images,
                        output_path=output_path,
                        title=post.get('title', ''),
                        author=author_name,
                        tags=post.get("tags", []),
                        published_time=post.get("published")
                    )
            
            self._move_other_files(temp_dir, final_images, save_dir, safe_title)
            
            # 记录下载成功
            if db:
                try:
                    p_service = post.get("service") or ""
                    p_user = post.get("user") or ""
                    p_id = post.get("id") or "0"
                    
                    work_id = f"kemono:{p_service}:{p_user}:{p_id}".strip(":")
                    
                    db.upsert_download_record(
                        platform="kemono",
                        work_id=work_id,
                        author=author_name,
                        title=post.get('title', 'Untitled'),
                        download_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        file_path=output_path if final_images else save_dir,
                        file_hash="DOWNLOADED_NEW",
                        source_url=f"{self.BASE_URL}/{p_service}/user/{p_user}/post/{p_id}"
                    )
                    db.conn.commit()
                except Exception as e:
                    tqdm.write(Colors.red(f"保存下载记录失败: {e}"))
                    pass
                
        return True

    def _is_same_file(self, src: str, dst: str) -> bool:
        if os.path.getsize(src) != os.path.getsize(dst):
            return False
            
        hash_src = hashlib.md5()
        hash_dst = hashlib.md5()
        chunk_size = 65536
        
        with open(src, 'rb') as f1, open(dst, 'rb') as f2:
            while True:
                b1 = f1.read(chunk_size)
                b2 = f2.read(chunk_size)
                if b1 != b2: 
                    return False
                if not b1: 
                    return True
        return True

    def _move_other_files(self, temp_dir: str, packaged_images: List[str], save_dir: str, base_name: str = ""):
        all_files = []
        for root, _, filenames in os.walk(temp_dir):
            for f in filenames:
                all_files.append(os.path.join(root, f))
        
        non_image_files = [f for f in all_files if f not in packaged_images]
        
        for src_path in non_image_files:
            original_name = os.path.basename(src_path)
            
            if base_name:
                if base_name in original_name:
                    dst_name = original_name
                else:
                    dst_name = f"{base_name} - {original_name}"
            else:
                dst_name = original_name
                
            dst_name = sanitize_filename(dst_name)
            dst_path = os.path.join(save_dir, dst_name)
            
            if os.path.exists(dst_path):
                if self._is_same_file(src_path, dst_path):
                    try:
                        os.remove(dst_path)
                    except: pass
                else:
                    base, ext = os.path.splitext(dst_name)
                    counter = 1
                    while True:
                        new_name = f"{base} ({counter}){ext}"
                        new_path = os.path.join(save_dir, new_name)
                        
                        if not os.path.exists(new_path):
                            dst_path = new_path
                            break
                            
                        if self._is_same_file(src_path, new_path):
                            dst_path = new_path
                            try: os.remove(dst_path)
                            except: pass
                            break
                            
                        counter += 1
                
            try:
                shutil.move(src_path, dst_path)
            except Exception as e:
                tqdm.write(Colors.red(f"移动文件失败 {dst_name}: {e}"))

    def _save_novel(self, post: Dict, save_dir: str, title_safe: str, author_name: str) -> bool:
        filename = f"{title_safe}.txt"
        file_path = os.path.join(save_dir, filename)
        
        if os.path.exists(file_path): return True
        
        content = post.get("content", "")
        soup = BeautifulSoup(content, 'html.parser')
        text_content = soup.get_text("\n")
        
        header = f"标题: {post.get('title')}\n作者: {author_name}\n发布时间: {post.get('published')}\nURL: {self.BASE_URL}/{post.get('service')}/user/{post.get('user')}/post/{post.get('id')}\n"
        full_text = f"{header}\n{text_content}"
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_text)
            
        set_file_time(file_path, post.get("published"))
        return True

    def _download_images(self, files: List[Dict], temp_dir: str) -> List[str]:
        downloaded = []
        with ThreadPoolExecutor(max_workers=32) as executor:
            futures = []
            for i, f in enumerate(files):
                url = f.get("path")
                if not url: continue
                if not url.startswith("http"): url = self.BASE_URL + url
                
                fname = f.get("name")
                url_clean = url.split('?')[0]
                
                if not fname:
                    fname = os.path.basename(url_clean)
                    
                ext = os.path.splitext(fname)[1].lower()
                
                if not ext:
                    ext = os.path.splitext(os.path.basename(url_clean))[1].lower()
                
                if not ext: ext = ".jpg"
                
                is_image = ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
                
                if is_image:
                    save_name = f"{i+1:03d}{ext}"
                else:
                    save_name = sanitize_filename(fname)
                    if not save_name: save_name = f"attachment_{i+1}{ext}"
                
                save_path = os.path.join(temp_dir, save_name)
                
                futures.append(executor.submit(self._download_file, url, save_path))
                downloaded.append(save_path)
                
            for f in futures:
                try:
                    f.result()
                except Exception as e:
                    tqdm.write(Colors.red(f"图片下载失败: {e}"))
        return downloaded

    def _extract_zips(self, temp_dir: str):
        for fname in os.listdir(temp_dir):
            if fname.lower().endswith('.zip'):
                zip_path = os.path.join(temp_dir, fname)
                try:
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        zf.extractall(path=temp_dir)
                    os.remove(zip_path)
                except Exception:
                    pass

    def _scan_images(self, temp_dir: str) -> List[str]:
        exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        files = []
        for root, _, filenames in os.walk(temp_dir):
            for f in filenames:
                if os.path.splitext(f)[1].lower() in exts:
                    files.append(os.path.join(root, f))
        return sorted(files)

    def _download_file(self, url: str, path: str):
        existing = 0
        try:
            if os.path.exists(path):
                existing = os.path.getsize(path)
        except Exception:
            existing = 0

        for attempt in range(self.MAX_RETRIES):
            try:
                headers = {}
                if existing > 0:
                    headers["Range"] = f"bytes={existing}-"

                res = self.session.get(url, stream=True, timeout=self.TIMEOUT, headers=headers or None)
                if existing > 0 and res.status_code in (416,):
                    return

                res.raise_for_status()

                if existing > 0 and res.status_code != 206:
                    try:
                        os.remove(path)
                    except Exception:
                        pass
                    existing = 0
                    headers = {}
                    res = self.session.get(url, stream=True, timeout=self.TIMEOUT)
                    res.raise_for_status()
                
                chunk_size = 1024 * 1024
                mode = 'ab' if existing > 0 and res.status_code == 206 else 'wb'
                with open(path, mode) as f:
                    for chunk in res.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                return
            except Exception as e:
                if attempt == self.MAX_RETRIES - 1:
                    if os.path.exists(path):
                        os.remove(path)
                    raise Exception(f"Failed after {self.MAX_RETRIES} attempts: {e}")
                time.sleep(1)

    def _get_author_name(self, service: str, user_id: str) -> str:
        try:
            profile_url = f"{self.API_BASE}/{service}/user/{user_id}/profile"
            res = self.session.get(profile_url, timeout=self.TIMEOUT)
            if res.status_code == 200:
                data = res.json()
                if name := data.get("name"):
                    return name
        except Exception as e:
            print(Colors.yellow(f"Profile API 获取作者名失败: {e}"))
            
        try:
            url = f"{self.BASE_URL}/{service}/user/{user_id}"
            res = self.session.get(url, timeout=self.TIMEOUT)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                meta = soup.find('meta', attrs={'name': 'artist_name'})
                if meta and meta.get('content'):
                    return meta.get('content')
                
                title = soup.find('title')
                if title:
                    return title.text.split('|')[0].strip()
        except Exception:
            pass
            
        return f"{service}_{user_id}"

    def _get_single_post(self, service: str, user_id: str, post_id: str) -> Optional[Dict]:
        url = f"{self.API_BASE}/{service}/user/{user_id}/post/{post_id}"
        try:
            res = self.session.get(url, timeout=self.TIMEOUT)
            if res.status_code == 200:
                data = res.json()
                
                if isinstance(data, dict) and "post" in data:
                    return data["post"]
                
                if isinstance(data, list) and len(data) > 0:
                    return data[0]
                return data
        except Exception as e:
            print(Colors.red(f"API请求失败: {e}"))
        return None

    def _get_all_posts(self, service: str, user_id: str) -> List[Dict]:
        all_posts = []
        offset = 0
        step = 50
        retry_count = 0
        
        while True:
            url = f"{self.API_BASE}/{service}/user/{user_id}/posts?o={offset}"
            try:
                res = self.session.get(url, timeout=self.TIMEOUT)
                if res.status_code != 200:
                    if res.status_code == 400 and offset > 0:
                        # Kemono API returns 400 when offset is out of bounds (end of list)
                        # This is expected behavior, so we just stop pagination.
                        break

                    if retry_count < self.MAX_RETRIES:
                        retry_count += 1
                        print(Colors.yellow(f"API 请求失败 ({res.status_code})，正在重试 ({retry_count}/{self.MAX_RETRIES})..."))
                        time.sleep(2)
                        continue
                    else:
                        print(Colors.red(f"API 请求失败喵: {res.status_code} (Offset: {offset})"))
                        break
                
                retry_count = 0
                
                data = res.json()
                if not data:
                    break
                    
                all_posts.extend(data)
                offset += step
                time.sleep(0.5)
                
            except Exception as e:
                print(Colors.red(f"获取帖子列表出错喵: {e}"))
                if retry_count < self.MAX_RETRIES:
                    retry_count += 1
                    time.sleep(2)
                    continue
                break
                
        return all_posts
