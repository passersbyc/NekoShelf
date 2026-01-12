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
import xml.etree.ElementTree as ET
from datetime import datetime
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional, Any
from tqdm import tqdm
from bs4 import BeautifulSoup

from core.utils import Colors
from .base import DownloadPlugin
from ..config import DOWNLOAD_CONFIG

class KemonoPlugin(DownloadPlugin):
    """
    Plugin for downloading novels and comics from Kemono.cr / Kemono.su
    Supports: Patreon, Fanbox, Fantia, etc. via Kemono.
    """
    
    BASE_URL = DOWNLOAD_CONFIG.get("kemono_base_url", "https://kemono.cr")
    API_BASE = DOWNLOAD_CONFIG.get("kemono_api_base", "https://kemono.cr/api/v1")
    MAX_WORKERS = DOWNLOAD_CONFIG.get("max_workers", 5)
    
    def __init__(self):
        self.session = requests.Session()
        retries = requests.adapters.Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        # 优化: 增大连接池大小，避免并发下载时连接被回收
        # pool_connections: 池中缓存的连接数
        # pool_maxsize: 每个连接池的最大连接数
        adapter = requests.adapters.HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        
        headers = {
            "User-Agent": DOWNLOAD_CONFIG.get("user_agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
            "Referer": self.BASE_URL,
            # DDOS-Guard bypass for Kemono.cr
            "Accept": "text/css" 
        }
        
        if cookie := DOWNLOAD_CONFIG.get("kemono_cookie"):
            headers["Cookie"] = cookie
            
        self.session.headers.update(headers)

    @property
    def name(self) -> str:
        return "Kemono"

    def can_handle(self, url: str) -> bool:
        # Matches: https://kemono.cr/patreon/user/94927303
        # Matches: https://kemono.su/fanbox/user/12345
        return re.search(r"kemono\.(cr|su|party)/(?P<service>\w+)/user/(?P<user_id>\d+)", url) is not None

    def download(self, url: str, output_dir: str, **kwargs) -> tuple[bool, str, str]:
        print(Colors.pink(f"正在解析 Kemono 链接喵: {url}"))
        
        # 1. 尝试匹配单帖子
        post_match = re.search(r"kemono\.(cr|su|party)/(?P<service>\w+)/user/(?P<user_id>\d+)/post/(?P<post_id>\d+)", url)
        
        # 2. 尝试匹配用户页
        user_match = re.search(r"kemono\.(cr|su|party)/(?P<service>\w+)/user/(?P<user_id>\d+)", url)
        
        if post_match:
            return self._download_single_post_mode(post_match, output_dir, **kwargs)
        elif user_match:
            return self._download_user_mode(user_match, output_dir, **kwargs)
        else:
            return False, "链接格式不对喵... 需要类似 https://kemono.cr/patreon/user/12345 或 具体帖子链接", None

    def _download_single_post_mode(self, match, output_dir, **kwargs) -> tuple[bool, str, str]:
        service = match.group("service")
        user_id = match.group("user_id")
        post_id = match.group("post_id")
        
        # 获取作者信息
        author_name = self._get_author_name(service, user_id)
        print(Colors.cyan(f"找到作者: {author_name} (ID: {user_id})"))
        
        # 准备目录
        from ..config import LIBRARY_DIR
        base_dir = output_dir if output_dir else LIBRARY_DIR
        author_dir = os.path.join(base_dir, self._sanitize_filename(author_name))
        os.makedirs(author_dir, exist_ok=True)
        
        # 获取帖子数据
        print(Colors.pink(f"正在获取帖子 {post_id} 数据..."))
        post = self._get_single_post(service, user_id, post_id)
        if not post:
             return False, f"无法获取帖子数据 ({post_id})", None
             
        # 下载
        # 确定是否保存内容
        config_save_content = DOWNLOAD_CONFIG.get("kemono_save_content", False)
        should_save_content = kwargs.get("save_content", False) or config_save_content
        
        success = self._download_post_safe(post, author_dir, author_name, should_save_content)
        
        # 清理 temp
        project_temp = os.path.join(os.getcwd(), "temp_downloads")
        if os.path.exists(project_temp):
            try: 
                # 只有空目录才删？或者不管？
                # 这里只尝试删除空目录，避免误删正在进行的其他任务
                os.rmdir(project_temp)
            except: pass
            
        if success:
            return True, "单贴下载完成喵！", author_dir
        else:
            return False, "下载失败喵...", author_dir

    def _download_user_mode(self, match, output_dir, **kwargs) -> tuple[bool, str, str]:
        service = match.group("service")
        user_id = match.group("user_id")
        
        # 1. 获取作者信息
        author_name = self._get_author_name(service, user_id)
        print(Colors.cyan(f"找到作者: {author_name} (ID: {user_id})"))
        
        # 2. 准备下载目录
        # 统一使用 Pixiv 风格的目录结构: Library/AuthorName/
        from ..config import LIBRARY_DIR
        base_dir = output_dir if output_dir else LIBRARY_DIR
        author_dir = os.path.join(base_dir, self._sanitize_filename(author_name))
        os.makedirs(author_dir, exist_ok=True)
        
        # 3. 获取所有帖子
        print(Colors.pink("正在获取帖子列表，可能需要一点时间喵..."))
        posts = self._get_all_posts(service, user_id)
        print(Colors.green(f"共发现 {len(posts)} 个帖子喵！准备开始搬运..."))
        
        if not posts:
            return True, "没有找到任何帖子喵...", author_dir

        results = {'success': 0, 'fail': 0}
        
        # 确定是否保存内容
        # 优先使用传入参数，其次使用配置
        config_save_content = DOWNLOAD_CONFIG.get("kemono_save_content", False)
        should_save_content = kwargs.get("save_content", False) or config_save_content

        # 统一使用批量处理逻辑
        # 传递 author_name 用于 metadata
        self._process_batch(posts, author_dir, "Posts", 
                          lambda p, d: self._download_post_safe(p, d, author_name, should_save_content), results)
        
        # 尝试删除 temp_downloads (如果为空)
        project_temp = os.path.join(os.getcwd(), "temp_downloads")
        if os.path.exists(project_temp):
            try:
                os.rmdir(project_temp)
            except OSError:
                pass
                
        return True, f"下载完成喵！成功: {results['success']}, 失败: {results['fail']}", author_dir

    def _process_batch(self, items: List[Any], save_dir: str, desc: str, func, stats: Dict):
        """统一的批量处理函数 (参考 PixivPlugin)"""
        tqdm.write(Colors.yellow(f"--- 开始处理 {len(items)} 个 {desc} ---"))
        with tqdm(total=len(items), unit="work", desc=f"Processing {desc}") as pbar:
            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
                # 提交任务
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

    def _download_post_safe(self, post: Dict, save_dir: str, author_name: str, save_content: bool = False) -> bool:
        try:
            return self._download_post(post, save_dir, author_name, save_content)
        except Exception as e:
            tqdm.write(Colors.red(f"帖子处理失败 ({post.get('id')}): {e}"))
            return False

    def _download_post(self, post: Dict, save_dir: str, author_name: str, save_content: bool = False) -> bool:
        """
        处理单个帖子。
        优化后的逻辑:
        1. 准备元数据和文件名
        2. 处理小说文本 (如果需要)
        3. 处理附件 (下载、打包图片、移动其他文件)
        """
        post_id = post.get("id")
        title = post.get("title", "Untitled") or "Untitled"
        
        # 统一命名格式: Title (ID)
        safe_title = self._sanitize_filename(f"{title} ({post_id})")
        
        content = post.get("content", "")
        attachments = post.get("attachments", [])
        file_info = post.get("file")
        
        # 收集所有目标文件
        targets = []
        if file_info: targets.append(file_info)
        if attachments: targets.extend(attachments)
        
        has_attachments = len(targets) > 0
        
        # 1. 判定是否保存小说文本
        # 条件: (纯文本模式) 或 (附件模式且强制保存内容)
        if (not has_attachments and content) or (has_attachments and content and save_content):
            novel_title = f"{safe_title}_content" if has_attachments else safe_title
            self._save_novel(post, save_dir, novel_title, author_name)
        
        # 2. 处理附件 (如果有)
        if has_attachments:
            return self._process_attachments(post, targets, save_dir, safe_title, author_name)
            
        return True

    def _process_attachments(self, post: Dict, targets: List[Dict], save_dir: str, safe_title: str, author_name: str) -> bool:
        """下载并处理帖子的所有附件"""
        # 确定打包格式
        fmt = DOWNLOAD_CONFIG.get("kemono_format", "pdf").lower() 
        if fmt not in ["cbz", "pdf"]: fmt = "pdf"
        output_ext = f".{fmt}"
        output_path = os.path.join(save_dir, f"{safe_title}{output_ext}")
        
        # 智能跳过逻辑
        # 1. 检查 PDF/CBZ 是否存在 (在当前输出目录)
        packed_exists = os.path.exists(output_path) and os.path.getsize(output_path) > 0
        
        # 2. 检查 PDF/CBZ 是否存在 (在书库目录)
        # 即使我们在下载到临时目录，如果书库里已经有了，也应该跳过
        if not packed_exists:
            from ..config import LIBRARY_DIR
            # 注意: 这里假设书库结构也是 Library/AuthorName/
            lib_author_dir = os.path.join(LIBRARY_DIR, self._sanitize_filename(author_name))
            lib_output_path = os.path.join(lib_author_dir, f"{safe_title}{output_ext}")
            if os.path.exists(lib_output_path) and os.path.getsize(lib_output_path) > 0:
                tqdm.write(Colors.yellow(f"书库中已存在: {safe_title}{output_ext}，跳过下载喵~"))
                packed_exists = True

        # 3. 筛选需要下载的文件
        files_to_download = []
        
        # 优先下载逻辑:
        # 如果存在高优先级的附件 (压缩包、文档、视频等)，则忽略页面上的图片列表
        # 避免出现 "Title.pdf" (附件) 和 "Title (ID).pdf" (生成的) 重复的情况
        priority_exts = {
            '.zip', '.rar', '.7z', '.tar', '.gz', '.xz', 
            '.pdf', '.epub', '.cbz', '.cbr', 
            '.iso', '.dmg', 
            '.mp4', '.mkv', '.mov', '.avi', '.wmv', '.webm', 
            '.psd', '.clip', '.sai', '.sai2', '.kra'
        }
        
        has_priority_attachment = False
        for t in targets:
            url = t.get("path", "")
            if not url: continue
            fname = t.get("name") or os.path.basename(url)
            ext = os.path.splitext(fname)[1].lower()
            if ext in priority_exts:
                has_priority_attachment = True
                break
        
        if has_priority_attachment:
            tqdm.write(Colors.yellow(f"发现高优先级附件，将跳过页面图片下载，优先保留原始文件喵~"))

        for t in targets:
            # 预判文件名和类型
            url = t.get("path", "")
            if not url: continue
            
            fname = t.get("name") or os.path.basename(url)
            ext = os.path.splitext(fname)[1]
            if not ext and not fname: ext = ".jpg"
            
            is_image = ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
            
            if is_image:
                # 如果有高优先级附件，跳过图片
                if has_priority_attachment:
                    continue
                # 如果压缩包已存在，跳过图片下载
                if packed_exists:
                    continue
                files_to_download.append(t)
            else:
                # 非图片文件，检查是否存在
                safe_name = self._sanitize_filename(fname)
                if not safe_name: safe_name = f"attachment_{ext}"
                
                dest_path = os.path.join(save_dir, safe_name)
                # 如果文件存在且大小大于0，跳过
                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                    continue
                files_to_download.append(t)
        
        # 如果没有任何文件需要下载，直接返回
        if not files_to_download:
            return True

        # 准备临时目录
        project_temp = os.path.join(os.getcwd(), "temp_downloads")
        os.makedirs(project_temp, exist_ok=True)
        
        with tempfile.TemporaryDirectory(prefix=f"kemono_{post.get('id')}_", dir=project_temp) as temp_dir:
            # A. 下载筛选后的文件
            self._download_images(files_to_download, temp_dir)
            
            # B. 解压可能存在的 zip
            self._extract_zips(temp_dir)
            
            # C. 扫描图片
            final_images = self._scan_images(temp_dir)
            
            # D. 打包图片 (如果有，且压缩包不存在)
            # 如果 packed_exists 为 True，我们上面已经跳过了图片下载，所以 final_images 应该为空（除非 zip 里解压出来的）
            # 但为了保险，还是检查一下 packed_exists
            if final_images and not packed_exists:
                if fmt == "cbz":
                    self._create_cbz(final_images, post, output_path, author_name)
                else:
                    self._create_pdf(final_images, post, output_path, author_name)
            
            # E. 移动非图片文件 (保留原始附件)
            self._move_other_files(temp_dir, final_images, save_dir)
                
        return True

    def _is_same_file(self, src: str, dst: str) -> bool:
        """判断两个文件是否内容相同"""
        # 1. 检查大小
        if os.path.getsize(src) != os.path.getsize(dst):
            return False
            
        # 2. 检查哈希 (MD5)
        # 对于大文件，只读取部分块进行比较可能不够严谨，但为了性能，
        # 我们这里采用分块读取计算完整 MD5
        hash_src = hashlib.md5()
        hash_dst = hashlib.md5()
        
        chunk_size = 65536
        
        with open(src, 'rb') as f1, open(dst, 'rb') as f2:
            while True:
                b1 = f1.read(chunk_size)
                b2 = f2.read(chunk_size)
                if b1 != b2: # 如果读取到的块内容不一样，直接返回 False (快速失败)
                    return False
                if not b1: # 读完了
                    return True
        return True

    def _move_other_files(self, temp_dir: str, packaged_images: List[str], save_dir: str):
        """将未打包的文件移动到目标目录"""
        all_files = []
        for root, _, filenames in os.walk(temp_dir):
            for f in filenames:
                all_files.append(os.path.join(root, f))
        
        # 过滤掉已经打包的图片
        non_image_files = [f for f in all_files if f not in packaged_images]
        
        for src_path in non_image_files:
            dst_name = os.path.basename(src_path)
            dst_path = os.path.join(save_dir, dst_name)
            
            # 防止文件名冲突
            if os.path.exists(dst_path):
                if self._is_same_file(src_path, dst_path):
                    # 如果是同一文件，直接覆盖 (保持 dst_path 不变)
                    # 在 macOS/Linux 上 shutil.move 会覆盖，Windows 上可能需要先删后移
                    # 为了兼容性，我们先删除目标文件
                    try:
                        os.remove(dst_path)
                    except: pass
                else:
                    # 如果不是同一文件，重命名: 使用短编号 (1), (2) 而不是长长的时间戳
                    base, ext = os.path.splitext(dst_name)
                    counter = 1
                    while True:
                        new_name = f"{base} ({counter}){ext}"
                        new_path = os.path.join(save_dir, new_name)
                        
                        # 如果这个编号的文件不存在，就用它
                        if not os.path.exists(new_path):
                            dst_path = new_path
                            break
                            
                        # 如果存在，顺便检查一下是不是内容一样
                        # 如果一样，就直接覆盖这个副本，不再继续增加编号
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
        """保存为小说 TXT"""
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
            
        # 修改时间
        self._set_file_time(file_path, post.get("published"))
        return True

    def _download_images(self, files: List[Dict], temp_dir: str) -> List[str]:
        """并发下载图片到临时目录"""
        downloaded = []
        # 优化: 增大并发数 (IO 密集型)，从 10 提升到 32
        with ThreadPoolExecutor(max_workers=32) as executor:
            futures = []
            for i, f in enumerate(files):
                url = f.get("path")
                if not url: continue
                if not url.startswith("http"): url = self.BASE_URL + url
                
                fname = f.get("name") or os.path.basename(url)
                ext = os.path.splitext(fname)[1]
                # 如果没有扩展名，默认 jpg? 不一定，如果是附件可能是其他
                if not ext and not fname: ext = ".jpg" 
                
                # 只有常见的图片格式才重命名为 001.ext，以便 CBZ 排序
                # 其他文件（zip, mp4, psd 等）保持原名
                is_image = ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
                
                if is_image:
                    save_name = f"{i+1:03d}{ext}"
                else:
                    # 保持原名，但要清理非法字符
                    save_name = self._sanitize_filename(fname)
                    if not save_name: save_name = f"attachment_{i+1}{ext}"
                
                save_path = os.path.join(temp_dir, save_name)
                
                futures.append(executor.submit(self._download_file, url, save_path))
                downloaded.append(save_path)
                
            for f in futures:
                try:
                    f.result()
                except:
                    pass
        return downloaded

    def _extract_zips(self, temp_dir: str):
        """解压临时目录中的所有 zip"""
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
        """扫描目录下的所有图片并排序"""
        exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        files = []
        for root, _, filenames in os.walk(temp_dir):
            for f in filenames:
                if os.path.splitext(f)[1].lower() in exts:
                    files.append(os.path.join(root, f))
        return sorted(files)

    def _create_cbz(self, images: List[str], post: Dict, output_path: str, author_name: str) -> bool:
        """创建 CBZ 并写入 ComicInfo.xml"""
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_STORED) as zf:
                # 写入图片
                for i, img_path in enumerate(images):
                    ext = os.path.splitext(img_path)[1]
                    zf.write(img_path, f"{i+1:03d}{ext}")
                
                # ComicInfo.xml
                root = ET.Element("ComicInfo")
                ET.SubElement(root, "Title").text = post.get('title', '')
                ET.SubElement(root, "Summary").text = BeautifulSoup(post.get('content', ''), 'html.parser').get_text()
                ET.SubElement(root, "Writer").text = author_name
                ET.SubElement(root, "PageCount").text = str(len(images))
                ET.SubElement(root, "Web").text = f"{self.BASE_URL}/{post.get('service')}/user/{post.get('user')}/post/{post.get('id')}"
                
                tags = post.get("tags", [])
                if tags: ET.SubElement(root, "Tags").text = ",".join(tags).replace(",", "，")
                
                if date_str := post.get("published"):
                    try:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        ET.SubElement(root, "Year").text = str(dt.year)
                        ET.SubElement(root, "Month").text = str(dt.month)
                        ET.SubElement(root, "Day").text = str(dt.day)
                    except: pass
                    
                if hasattr(ET, 'indent'): ET.indent(root, space="  ")
                zf.writestr("ComicInfo.xml", ET.tostring(root, encoding='utf-8', method='xml'))
                
            self._set_file_time(output_path, post.get("published"))
            tqdm.write(Colors.green(f"已生成 CBZ: {os.path.basename(output_path)}"))
            return True
        except Exception as e:
            tqdm.write(Colors.red(f"CBZ 打包失败: {e}"))
            return False

    def _create_pdf(self, images: List[str], post: Dict, output_path: str, author_name: str) -> bool:
        """创建 PDF (保留原有逻辑但适配新结构)"""
        try:
            img_objs = []
            for img_path in images:
                try:
                    img = Image.open(img_path)
                    if img.mode != 'RGB': img = img.convert('RGB')
                    img_objs.append(img)
                except: pass
            
            if not img_objs: return False
            
            tags = post.get("tags", [])
            keywords = ", ".join(tags) if tags else ""
            
            img_objs[0].save(output_path, "PDF", resolution=100.0, save_all=True, append_images=img_objs[1:], 
                           title=post.get("title", ""), author=author_name, keywords=keywords)
            
            # Close images
            for img in img_objs: img.close()
            
            self._set_file_time(output_path, post.get("published"))
            tqdm.write(Colors.green(f"已生成 PDF: {os.path.basename(output_path)}"))
            return True
        except Exception as e:
            tqdm.write(Colors.red(f"PDF 生成失败: {e}"))
            return False

    def _set_file_time(self, filepath: str, date_str: str):
        if not date_str: return
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            ts = dt.timestamp()
            os.utime(filepath, (ts, ts))
        except: pass

    def _download_file(self, url: str, path: str):
        # 简单检查: 如果文件存在且大小 > 0，则跳过
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return
            
        # 增加超时设置，防止挂死
        # 增加重试逻辑 (针对流读取中断)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 缩短超时时间，避免长时间卡顿
                res = self.session.get(url, stream=True, timeout=15)
                res.raise_for_status()
                
                # 优化: 增大 buffer size 到 1MB 以提升下载速度 (之前是 64KB)
                chunk_size = 1024 * 1024 # 1MB
                with open(path, 'wb') as f:
                    for chunk in res.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                return # Success
            except Exception as e:
                if attempt == max_retries - 1:
                    # 删除可能损坏的文件
                    if os.path.exists(path):
                        os.remove(path)
                    # 抛出异常以便上层感知
                    raise Exception(f"Failed after {max_retries} attempts: {e}")
                time.sleep(1)

    def _sanitize_filename(self, name: str) -> str:
        # 1. 替换主要非法字符为全角字符，保持美观
        # / -> ／, : -> ：, ? -> ？, * -> ＊, " -> ”, < -> ＜, > -> ＞, | -> ｜
        replacements = {
            '/': '／', '\\': '＼',
            ':': '：', '?': '？',
            '*': '＊', '"': '”',
            '<': '＜', '>': '＞',
            '|': '｜'
        }
        cleaned = name
        for char, repl in replacements.items():
            cleaned = cleaned.replace(char, repl)
            
        # 2. 移除控制字符
        cleaned = "".join(c for c in cleaned if c.isprintable())
        
        # 3. 移除首尾空格和点 (Windows 限制)
        return cleaned.strip(". ")

    def _get_author_name(self, service: str, user_id: str) -> str:
        """从 Kemono API 获取作者名称"""
        try:
            # 优先尝试 Profile API
            profile_url = f"{self.API_BASE}/{service}/user/{user_id}/profile"
            res = self.session.get(profile_url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if name := data.get("name"):
                    return name
        except Exception as e:
            print(Colors.yellow(f"Profile API 获取作者名失败: {e}"))
            
        # Fallback: 尝试从页面获取 (虽然现在主要靠 API)
        try:
            url = f"{self.BASE_URL}/{service}/user/{user_id}"
            res = self.session.get(url, timeout=10)
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
        """获取单个帖子数据"""
        url = f"{self.API_BASE}/{service}/user/{user_id}/post/{post_id}"
        try:
            res = self.session.get(url, timeout=15)
            if res.status_code == 200:
                # API 返回的如果是列表（某些版本），取第一个；通常直接是对象
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    return data[0]
                return data
        except Exception as e:
            print(Colors.red(f"API请求失败: {e}"))
        return None

    def _get_all_posts(self, service: str, user_id: str) -> List[Dict]:
        """分页获取所有帖子"""
        all_posts = []
        offset = 0
        step = 50 # Kemono default page size
        retry_count = 0
        
        while True:
            url = f"{self.API_BASE}/{service}/user/{user_id}/posts?o={offset}"
            try:
                res = self.session.get(url, timeout=15)
                if res.status_code != 200:
                    if retry_count < 3:
                        retry_count += 1
                        print(Colors.yellow(f"API 请求失败 ({res.status_code})，正在重试 ({retry_count}/3)..."))
                        time.sleep(2)
                        continue
                    else:
                        print(Colors.red(f"API 请求失败喵: {res.status_code} (Offset: {offset})"))
                        break
                
                # 重置重试计数
                retry_count = 0
                
                data = res.json()
                if not data:
                    break
                    
                all_posts.extend(data)
                offset += step
                
                # 简单防刷延时
                time.sleep(0.5)
                
            except Exception as e:
                print(Colors.red(f"获取帖子列表出错喵: {e}"))
                if retry_count < 3:
                    retry_count += 1
                    time.sleep(2)
                    continue
                break
                
        return all_posts
