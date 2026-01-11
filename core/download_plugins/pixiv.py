import os
import re
import requests
import time
import json
import shutil
import zipfile
import html
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
try:
    from PIL import Image
except ImportError:
    Image = None

from .base import DownloadPlugin
from ..utils import Colors
from ..config import DOWNLOAD_CONFIG

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class PixivPlugin(DownloadPlugin):
    BASE_URL = "https://www.pixiv.net"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Referer": "https://www.pixiv.net/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        # Disable certificate verification warning
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.headers.update(self.HEADERS)
        self._load_cookies()

    def _load_cookies(self):
        self.cookie = DOWNLOAD_CONFIG.get("pixiv_cookie", "")
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def _save_cookie(self, cookie):
        # Update in memory
        self.cookie = cookie
        DOWNLOAD_CONFIG["pixiv_cookie"] = cookie
        self.session.headers["Cookie"] = cookie
        
        # Try to update config.py file
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.py")
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Simple regex replacement to update the variable in file
            # Looking for DOWNLOAD_CONFIG = { ... "pixiv_cookie": "..." ... }
            # This is a bit fragile but works for simple structure
            new_content = re.sub(
                r'("pixiv_cookie":\s*")[^"]*(")',
                f'\\1{cookie}\\2',
                content
            )
            
            if new_content != content:
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(Colors.green("Cookie 已保存到配置文件喵！下次不用再输入啦~"))
        except Exception as e:
            print(Colors.red(f"保存 Cookie 失败: {e}"))

    def _check_cookie_validity(self):
        """Simple check if cookie is valid"""
        if not self.cookie:
            return
            
        try:
            # Try to fetch user self data or just a main page check
            # ajax/user/extra returns login status
            url = f"{self.BASE_URL}/ajax/user/extra"
            res = self.session.get(url, timeout=5)
            if res.status_code == 200:
                # If we get a 200 OK from this endpoint with a body, we are likely fine.
                # The 'is_logged_in' field might be missing in some responses, so we relax the check.
                pass
        except Exception:
            pass

    @property
    def name(self) -> str:
        return "Pixiv Crawler"

    def can_handle(self, url: str) -> bool:
        return any(x in url for x in [
            "pixiv.net/users/", "pixiv.net/u/", "pixiv.net/en/users/",
            "pixiv.net/novel/series/"
        ])

    def download(self, url: str, output_dir: str, **kwargs) -> tuple[bool, str, str]:
        # Check for cookie
        self._check_cookie_validity()
        if not self.cookie:
            print(Colors.yellow("Pixiv 爬虫建议使用 Cookie 以获取完整作品 (含 R-18) 喵~"))
            print(Colors.cyan("请输入 Pixiv Cookie (留空则尝试匿名爬取):"))
            c = input("Cookie: ").strip()
            if c:
                self._save_cookie(c)

        mode, pid = self._parse_url(url)
        if not pid:
            return False, "无法解析 Pixiv URL (ID 未找到) 喵...", None

        print(Colors.pink(f"识别模式: {mode} (ID: {pid})，正在获取列表喵..."))
        
        try:
            author_name, works = self._get_download_targets(mode, pid)
            print(Colors.cyan(f"目标集合: {author_name}"))
        except Exception as e:
            return False, f"获取信息失败 (可能需要登录): {e}", None

        total_works = len(works['illusts']) + len(works['manga']) + len(works['novels'])
        print(Colors.cyan(f"共找到 {total_works} 个作品 (插画: {len(works['illusts'])}, 漫画: {len(works['manga'])}, 小说: {len(works['novels'])})"))

        if total_works == 0:
            return True, "没有找到可以下载的作品喵...", None

        # Create Author Directory in output_dir (temp dir) or LIBRARY_DIR if output_dir is not provided
        if output_dir:
            base_dir = output_dir
        else:
            from ..config import LIBRARY_DIR
            base_dir = LIBRARY_DIR

        author_dir = os.path.join(base_dir, self._sanitize_filename(author_name))
        os.makedirs(author_dir, exist_ok=True)
        
        success_count = 0
        fail_count = 0
        
        # Max threads
        max_workers = 5
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Download Novels
            if works['novels']:
                print(Colors.yellow(f"--- 开始下载 {len(works['novels'])} 部小说 ---"))
                with tqdm(total=len(works['novels']), unit="novel", desc="Downloading Novels") as pbar:
                    futures = {executor.submit(self._download_novel_safe, nid, author_dir): nid for nid in works['novels']}
                    for future in as_completed(futures):
                        if future.result():
                            success_count += 1
                        else:
                            fail_count += 1
                        pbar.update(1)

            # Download Manga/Illusts
            illust_manga_ids = works['illusts'] + works['manga']
            if illust_manga_ids:
                print(Colors.yellow(f"--- 开始下载 {len(illust_manga_ids)} 部漫画/插画 ---"))
                with tqdm(total=len(illust_manga_ids), unit="work", desc="Downloading Manga/Illusts") as pbar:
                    # Pass output_dir (temp dir) as the workspace for intermediate files
                    futures = {executor.submit(self._download_illust_safe, iid, author_dir, output_dir): iid for iid in illust_manga_ids}
                    for future in as_completed(futures):
                        if future.result():
                            success_count += 1
                        else:
                            fail_count += 1
                        pbar.update(1)

        return True, f"爬取完成喵！成功: {success_count}, 失败: {fail_count}", author_dir

    def _download_novel_safe(self, nid, save_dir):
        """Wrapper to retry download on failure"""
        for attempt in range(3):
            try:
                if self._download_novel(nid, save_dir):
                    return True
            except Exception as e:
                # Only print error on last attempt to avoid cluttering progress bar
                if attempt == 2:
                    tqdm.write(Colors.red(f"小说 {nid} 下载失败 (重试耗尽): {e}"))
            time.sleep(1 + attempt) # Backoff
        return False

    def _download_illust_safe(self, iid, save_dir, temp_root=None):
        """Wrapper to retry download on failure"""
        for attempt in range(3):
            try:
                if self._download_illust(iid, save_dir, temp_root):
                    return True
            except Exception as e:
                if attempt == 2:
                    tqdm.write(Colors.red(f"漫画/插画 {iid} 下载失败 (重试耗尽): {e}"))
            time.sleep(1 + attempt)
        return False

    def _parse_url(self, url):
        # Series
        m = re.search(r'novel/series/(\d+)', url)
        if m: return 'SERIES', m.group(1)
        
        # User ID
        m = re.search(r'users/(\d+)', url)
        if not m: return None, None
        uid = m.group(1)
        
        # Check sub-paths
        if 'bookmarks/novels' in url: return 'USER_BOOKMARKS_NOVELS', uid
        if 'illustrations' in url: return 'USER_ILLUSTS', uid
        if 'manga' in url: return 'USER_MANGA', uid
        if 'novels' in url: return 'USER_NOVELS', uid
        
        return 'USER_ALL', uid

    def _get_download_targets(self, mode, pid):
        works = {'illusts': [], 'manga': [], 'novels': []}
        author_name = "Unknown"
        
        if mode == 'SERIES':
            # Fetch series info
            meta = self._get_series_metadata(pid)
            author_name = meta.get('author', f"Series_{pid}")
            
            # Try to extract works from metadata first (if available)
            raw_body = meta.get('raw_body', {})
            
            works_from_meta = []
            
            # Check for scraped IDs first
            if raw_body.get('scraped_ids'):
                works_from_meta = raw_body['scraped_ids']
                
            # Check common keys for content list
            if not works_from_meta:
                potential_keys = ['seriesContents', 'works', 'novels', 'publishedContent']
                for k in potential_keys:
                    if k in raw_body and isinstance(raw_body[k], list):
                        works_from_meta = [str(x['id']) for x in raw_body[k] if isinstance(x, dict) and 'id' in x]
                        if works_from_meta:
                            break
            
            if works_from_meta:
                works['novels'] = works_from_meta
            else:
                works['novels'] = self._get_series_works(pid)
                
                # Fallback: Traversal if API list failed but we have start ID
                first_novel_id = raw_body.get('firstNovelId')
                if not works['novels'] and first_novel_id:
                    print(Colors.yellow("列表获取失败，尝试通过链式遍历获取作品列表喵..."))
                    works['novels'] = self._crawl_series_by_traversal(first_novel_id)
            
        elif mode == 'USER_BOOKMARKS_NOVELS':
            author_name = self._get_user_name(pid)
            author_name = f"{author_name}_Bookmarks"
            works['novels'] = self._get_bookmark_works(pid, 'novel')
            
        else:
            # User works
            author_name = self._get_user_name(pid)
            all_works = self._get_user_works(pid)
            
            if mode == 'USER_ALL':
                works = all_works
            elif mode == 'USER_ILLUSTS':
                works['illusts'] = all_works['illusts']
            elif mode == 'USER_MANGA':
                works['manga'] = all_works['manga']
            elif mode == 'USER_NOVELS':
                works['novels'] = all_works['novels']
                
        return author_name, works

    def _crawl_series_by_traversal(self, first_id):
        ids = []
        current_id = str(first_id)
        visited = set()
        
        with tqdm(desc="遍历系列作品", unit="章", leave=False) as pbar:
            while current_id and current_id not in visited:
                ids.append(current_id)
                visited.add(current_id)
                pbar.update(1)
                
                url = f"{self.BASE_URL}/ajax/novel/{current_id}"
                try:
                    res = self.session.get(url)
                    if res.status_code != 200:
                        break
                        
                    body = res.json().get('body', {})
                    if not body: break
                    
                    nav_data = body.get('seriesNavData') or {}
                    
                    # Check next
                    next_node = nav_data.get('next')
                    if next_node and isinstance(next_node, dict):
                        next_id = str(next_node.get('id'))
                        if next_id == current_id: break # Prevent self-loop
                        current_id = next_id
                    else:
                        current_id = None
                        
                    time.sleep(0.3)
                except Exception:
                    break
                    
        return ids

    def _get_series_metadata(self, series_id):
        # 1. Try AJAX API
        url = f"{self.BASE_URL}/ajax/novel/series/{series_id}"
        self.session.headers.update({"Referer": f"{self.BASE_URL}/novel/series/{series_id}"})
        
        res = self.session.get(url)
        if res.status_code == 200:
            body = res.json().get('body')
            if body:
                return {'title': body.get('title'), 'author': body.get('userName'), 'raw_body': body}
        
        # 2. Fallback: Scrape HTML Page
        # This is useful when API returns 404 (e.g. R-18 series without login, or API restrictions)
        # but the page is partially visible.
        print(Colors.yellow("Pixiv API 获取失败 (404/Error)，尝试网页解析模式喵..."))
        page_url = f"{self.BASE_URL}/novel/series/{series_id}"
        try:
            res = self.session.get(page_url)
            if res.status_code == 200:
                html_content = res.text
                # Extract Title
                # <title>Series Title/Author's Series [pixiv]</title>
                title_match = re.search(r'<title>(.*?)(?:/|\||\[).*?</title>', html_content)
                title = title_match.group(1).strip() if title_match else f"Series_{series_id}"
                
                ids = []
                
                # Method 1: Regex Scraping (Links)
                # Link format: /novel/show.php?id=123456 or /novel/123456
                ids.extend(re.findall(r'/novel/show\.php\?id=(\d+)', html_content))
                if not ids:
                    ids.extend(re.findall(r'/novel/(\d+)"', html_content))
                
                # Method 2: __NEXT_DATA__ JSON Extraction (Reliable for R-18/SPA)
                if not ids:
                    try:
                        # More robust regex for __NEXT_DATA__
                        next_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', html_content, re.DOTALL)
                        if next_match:
                            data = json.loads(next_match.group(1))
                            props = data.get('props', {}).get('pageProps', {})
                            
                            # Check seriesContents
                            contents = props.get('seriesContents', [])
                            if contents:
                                ids.extend([str(x['id']) for x in contents if isinstance(x, dict) and 'id' in x])
                                print(Colors.pink(f"通过 __NEXT_DATA__ 解析到 {len(ids)} 个作品喵！"))
                    except Exception as e:
                        # print(Colors.red(f"NEXT_DATA解析失败: {e}"))
                        pass
                
                # Method 3: global-data JSON Extraction
                if not ids:
                    try:
                        # More robust regex for global-data
                        meta_match = re.search(r'<meta\s+[^>]*name="global-data"\s+[^>]*content="([^"]+)"', html_content)
                        if not meta_match:
                             meta_match = re.search(r'<meta\s+[^>]*content="([^"]+)"\s+[^>]*name="global-data"', html_content)
                        
                        if meta_match:
                            json_str = html.unescape(meta_match.group(1))
                            data = json.loads(json_str)
                            
                            # 1. Try structured access
                            # Usually: data['novelSeries'][series_id]...
                            # But let's look for any list of objects with 'id' inside the series context
                            
                            # 2. Fallback: Regex on the JSON string (safest for unknown structure)
                            # We look for "id":"12345" patterns, but we need to be careful.
                            # Let's try to find the series contents array specifically.
                            # Usually "seriesContents":[{...}]
                            
                            series_contents_match = re.search(r'"seriesContents":\s*(\[[^\]]+\])', json_str)
                            if series_contents_match:
                                contents_json = series_contents_match.group(1)
                                ids_in_json = re.findall(r'"id":\s*"?(\d+)"?', contents_json)
                                if ids_in_json:
                                    ids.extend(ids_in_json)
                                    print(Colors.pink(f"通过 global-data 解析到 {len(ids_in_json)} 个作品喵！"))
                    except Exception:
                        pass
                
                ids = list(dict.fromkeys(ids)) # Deduplicate
                
                if ids:
                    print(Colors.pink(f"网页解析成功: 找到 {len(ids)} 个作品喵！"))
                    return {
                        'title': title,
                        'author': 'Unknown_Scraped', 
                        'raw_body': {'scraped_ids': ids, 'firstNovelId': ids[0]}
                    }
                else:
                    print(Colors.yellow(f"网页解析警告: 未找到任何作品ID。HTML预览: {html_content[:200]}..."))
                    print(Colors.yellow("提示: 如果这是R-18系列，请检查Cookie是否包含R-18权限，或者是否已过期喵！"))
        except Exception as e:
            print(Colors.red(f"网页解析失败: {e}"))
            
        return {}

    def _get_series_works(self, series_id):
        ids = []
        offset = 0
        limit = 30
        while True:
            url = f"{self.BASE_URL}/ajax/novel/series/{series_id}/content?limit={limit}&last_order={offset}&order_by=asc"
            res = self.session.get(url)
            if res.status_code != 200: break
            
            body = res.json().get('body')
            
            data = []
            if isinstance(body, list):
                data = body
            elif isinstance(body, dict) and 'page' in body:
                 # Handle pagination dictionary if present
                 data = body.get('page', {}).get('seriesContents', [])
            
            if not data: break
            
            batch_ids = [str(x['id']) for x in data if isinstance(x, dict) and 'id' in x]
            if not batch_ids: break
            
            ids.extend(batch_ids)
            
            if len(data) < limit: break
            offset += len(data)
            time.sleep(0.5)
        return ids

    def _get_bookmark_works(self, user_id, type='novel'):
        ids = []
        offset = 0
        limit = 48
        while True:
            # Only supports public bookmarks for now unless cookie has access
            url = f"{self.BASE_URL}/ajax/user/{user_id}/novels/bookmarks?tag=&offset={offset}&limit={limit}&rest=show"
            res = self.session.get(url)
            if res.status_code != 200: break
            body = res.json().get('body', {})
            works = body.get('works', [])
            if not works: break
            
            batch_ids = [str(x['id']) for x in works]
            ids.extend(batch_ids)
            
            total = body.get('total', 0)
            if len(ids) >= total or len(works) < limit: break
            offset += limit
            time.sleep(0.5)
        return ids

    def _extract_user_id(self, url):
        match = re.search(r'users/(\d+)', url)
        return match.group(1) if match else None

    def _get_user_name(self, user_id):
        url = f"{self.BASE_URL}/ajax/user/{user_id}?full=1"
        res = self.session.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        return data.get('body', {}).get('name', f"User_{user_id}")

    def _get_user_works(self, user_id):
        url = f"{self.BASE_URL}/ajax/user/{user_id}/profile/all"
        res = self.session.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        body = data.get('body', {})
        
        return {
            'illusts': self._extract_ids(body.get('illusts')),
            'manga': self._extract_ids(body.get('manga')),
            'novels': self._extract_ids(body.get('novels'))
        }

    def _extract_ids(self, data):
        """Safely extract IDs from a dict or list."""
        if isinstance(data, dict):
            return list(data.keys())
        return []

    def _download_novel(self, nid, save_dir):
        url = f"{self.BASE_URL}/ajax/novel/{nid}"
        res = self.session.get(url, timeout=10)
        if res.status_code != 200:
            return False
            
        data = res.json()
        if data.get('error'):
            return False
            
        body = data.get('body')
        if not body:
            # Body is missing, treat as failure to trigger retry
            return False
            
        title = body.get('title', f"novel_{nid}")
        content = body.get('content', '')
        # Fix for NoneType error: handle case where seriesNavData is None
        series_data = body.get('seriesNavData') or {}
        series_title = series_data.get('title', '')
        
        # Metadata
        tags_obj = body.get('tags') or {}
        tags = tags_obj.get('tags', [])
        tag_list = [t.get('tag') for t in tags if t.get('tag')]
        description = body.get('description', '')
        author_name = body.get('userName', '')
        
        # Format content with metadata header
        header = f"标题: {title}\n作者: {author_name}\n"
        if tag_list:
            header += f"标签: {','.join(tag_list)}\n"
        if series_title:
            header += f"系列: {series_title}\n"
            
        full_text = f"{header}\n简介:\n{description}\n\n{content}"

        # Save
        # Format: Title.txt
        filename = f"{self._sanitize_filename(title)}.txt"
        path = os.path.join(save_dir, filename)
            
        with open(path, 'w', encoding='utf-8') as f:
            f.write(full_text)
            
        # Use tqdm.write instead of print to avoid interfering with progress bar
        # tqdm.write(f"已下载小说: {title}") 
        return True

    def _download_illust(self, iid, save_dir, temp_root=None):
        # Reset meta_cache for this download
        self.meta_cache = {'iid': iid, 'title': f"illust_{iid}", 'tags': []}
        
        # Get pages
        url = f"{self.BASE_URL}/ajax/illust/{iid}/pages"
        res = self.session.get(url, timeout=10)
        if res.status_code != 200:
            return False
            
        data = res.json()
        pages = data.get('body', [])
        
        if not pages:
            return False
            
        # Get metadata for title with retry
        title = f"illust_{iid}"
        meta_json = None
        for attempt in range(3):
            try:
                meta_url = f"{self.BASE_URL}/ajax/illust/{iid}"
                res = self.session.get(meta_url, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    if data.get('body'):
                        meta_json = data
                        break
            except Exception:
                pass
            if attempt < 2:
                time.sleep(1)
        
        if meta_json:
            try:
                body = meta_json.get('body') or {}
                raw_title = body.get('title') or f"illust_{iid}"
                # Append ID to title to ensure uniqueness and better identification
                title = f"{raw_title} ({iid})"
                
                # Extract full metadata
                tags_obj = body.get('tags') or {}
                raw_tags_data = tags_obj.get('tags', [])
                processed_tags = []
                for t in raw_tags_data:
                    tag_name = t.get('tag', '')
                    if tag_name:
                        processed_tags.append(tag_name)
                        # Add English translation if available
                        trans_obj = t.get('translation') or {}
                        tag_trans = trans_obj.get('en')
                        if tag_trans:
                            processed_tags.append(tag_trans)
                
                # Deduplicate while preserving order
                processed_tags = list(dict.fromkeys(processed_tags))

                self.meta_cache.update({
                    'title': raw_title,
                    'author': body.get('userName') or '',
                    'tags': processed_tags,
                    'description': body.get('description') or '',
                    'series': (body.get('seriesNavData') or {}).get('title', ''),
                    'createDate': body.get('createDate') or '',
                    'uploadDate': body.get('uploadDate') or '',
                    'iid': iid
                })
            except Exception as e:
                tqdm.write(Colors.yellow(f"元数据获取警告: {e}"))
                # Keep default meta_cache
                pass
        else:
             tqdm.write(Colors.yellow(f"无法获取元数据，使用默认标题: {title}"))
                
        # Incremental Download Check for PDF/CBZ
        title_safe = self._sanitize_filename(title)
        cbz_filename = f"{title_safe}.cbz"
        cbz_path = os.path.join(save_dir, cbz_filename)
        
        # Check CBZ existence (Prioritize CBZ)
        if os.path.exists(cbz_path) and os.path.getsize(cbz_path) > 0:
            tqdm.write(Colors.green(f"已存在跳过: {title}"))
            return True

        # Create temporary folder for downloading images
        # Use temp_root if provided, otherwise fallback to save_dir
        folder_name = title_safe
        if temp_root and os.path.exists(temp_root):
             work_dir = os.path.join(temp_root, f"_temp_{folder_name}_{iid}")
        else:
             work_dir = os.path.join(save_dir, f"_temp_{folder_name}_{iid}")
             
        os.makedirs(work_dir, exist_ok=True)
        
        # Prepare download tasks
        download_tasks = []
        for idx, page in enumerate(pages):
            img_url = page.get('urls', {}).get('original')
            if not img_url:
                continue
            fname = f"{idx:04d}_{os.path.basename(img_url)}"
            save_path = os.path.join(work_dir, fname)
            download_tasks.append((img_url, save_path))
            
        # Parallel Download Images
        downloaded_images = []
        
        # Use a localized thread pool for this manga's pages
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_path = {
                executor.submit(self._download_image_content, url, path): path 
                for url, path in download_tasks
            }
            
            # Show progress bar if page count > 5
            iterator = as_completed(future_to_path)
            if len(download_tasks) > 5:
                iterator = tqdm(iterator, total=len(download_tasks), leave=False, unit="img", desc=f"DL {title[:10]}...")
            
            for future in iterator:
                path = future_to_path[future]
                if future.result():
                    downloaded_images.append(path)
                else:
                    tqdm.write(Colors.yellow(f"图片下载失败: {os.path.basename(path)}"))
        
        if not downloaded_images:
            shutil.rmtree(work_dir, ignore_errors=True)
            return False

        # Sort images by filename (already numbered)
        downloaded_images.sort()

        # Create CBZ with ComicInfo.xml
        try:
            with zipfile.ZipFile(cbz_path, 'w', zipfile.ZIP_STORED) as zf:
                # Write images with standardized numbering (001.jpg, 002.jpg...)
                # This ensures compatibility with most comic readers
                for i, img_path in enumerate(downloaded_images):
                    ext = os.path.splitext(img_path)[1]
                    new_name = f"{i+1:03d}{ext}"
                    zf.write(img_path, new_name)
                
                # Write ComicInfo.xml if metadata available
                if hasattr(self, 'meta_cache'):
                    try:
                        m = self.meta_cache
                        root = ET.Element("ComicInfo")
                        
                        # Add standard fields
                        ET.SubElement(root, "Title").text = str(m.get("title", ""))
                        ET.SubElement(root, "Series").text = str(m.get("series", ""))
                        ET.SubElement(root, "Summary").text = str(m.get("description", ""))
                        ET.SubElement(root, "Writer").text = str(m.get("author", ""))
                        ET.SubElement(root, "PageCount").text = str(len(downloaded_images))
                        ET.SubElement(root, "LanguageISO").text = "ja"
                        ET.SubElement(root, "Manga").text = "YesAndRightToLeft"
                        
                        # Handle dates (Pixiv format: 2023-10-27T12:00:00+09:00)
                        date_str = m.get('createDate') or m.get('uploadDate')
                        if date_str:
                            try:
                                dt = datetime.fromisoformat(date_str)
                                ET.SubElement(root, "Year").text = str(dt.year)
                                ET.SubElement(root, "Month").text = str(dt.month)
                                ET.SubElement(root, "Day").text = str(dt.day)
                            except:
                                pass
                        
                        # Handle tags safely (remove commas to avoid splitting issues)
                        tags = m.get("tags", [])
                        clean_tags = [t.replace(",", "，") for t in tags if t]
                        ET.SubElement(root, "Tags").text = ",".join(clean_tags)
                        
                        ET.SubElement(root, "Web").text = f"{self.BASE_URL}/artworks/{m.get('iid', '')}"
                        
                        # Pretty print
                        if hasattr(ET, 'indent'):
                            ET.indent(root, space="  ")
                        xml_bytes = ET.tostring(root, encoding='utf-8', method='xml')
                        
                        zf.writestr("ComicInfo.xml", xml_bytes)
                    except Exception as e:
                        tqdm.write(Colors.yellow(f"ComicInfo.xml 生成警告: {e}"))
                    
            tag_count = len(self.meta_cache.get('tags', [])) if hasattr(self, 'meta_cache') else 0
            tqdm.write(Colors.green(f"已生成 CBZ: {os.path.basename(cbz_path)} [标签: {tag_count}]"))
            
            # Warn if partial download
            if len(downloaded_images) < len(download_tasks):
                missing_count = len(download_tasks) - len(downloaded_images)
                tqdm.write(Colors.yellow(f"注意: 有 {missing_count} 张图片下载失败，CBZ 内容不完整！"))
                
        except Exception as e:
            tqdm.write(Colors.red(f"CBZ 打包失败: {e}"))
            shutil.rmtree(work_dir, ignore_errors=True)
            return False

        # Cleanup
        shutil.rmtree(work_dir, ignore_errors=True)
        return True

    def _download_image_content(self, url, save_path):
        """Helper to download a single image with retries"""
        for attempt in range(3):
            try:
                res = self.session.get(url, stream=True, timeout=20)
                if res.status_code == 200:
                    expected_size = int(res.headers.get('content-length', 0))
                    
                    with open(save_path, 'wb') as f:
                        for chunk in res.iter_content(8192):
                            f.write(chunk)
                            
                    # Validate size if Content-Length provided
                    if expected_size > 0 and os.path.getsize(save_path) != expected_size:
                        continue # Retry
                        
                    return True
                else:
                    if attempt == 2: # Last attempt
                        tqdm.write(Colors.yellow(f"图片下载失败 {url}: Status {res.status_code}"))
            except Exception:
                time.sleep(1)
        return False

    def _sanitize_filename(self, name):
        # Replace illegal characters with full-width alternatives (visually similar but safe)
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
        cleaned = ""
        for char in name:
            cleaned += table.get(char, char)
            
        # Truncate to ensure filename is within filesystem byte limits (usually 255 bytes)
        # We assume UTF-8 encoding (up to 4 bytes per char), so 60 chars is safely < 255 bytes
        # even if all are 4-byte emojis. 60 chars is plenty for readability.
        if len(cleaned) > 60:
            cleaned = cleaned[:60]
            
        return cleaned.strip()
