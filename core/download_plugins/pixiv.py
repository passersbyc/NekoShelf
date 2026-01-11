import os
import re
import time
import json
import shutil
import zipfile
import html
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List, Tuple, Any, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

from .base import DownloadPlugin
from ..utils import Colors
from ..config import DOWNLOAD_CONFIG

# Optional PIL support
try:
    from PIL import Image
except ImportError:
    Image = None

class PixivPlugin(DownloadPlugin):
    BASE_URL = "https://www.pixiv.net"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Referer": "https://www.pixiv.net/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    MAX_RETRIES = 3
    TIMEOUT = 10
    MAX_WORKERS = 5

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self._configure_session()
        self._load_cookies()

    def _configure_session(self):
        retries = Retry(
            total=self.MAX_RETRIES, 
            backoff_factor=1, 
            status_forcelist=[500, 502, 503, 504]
        )
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.headers.update(self.HEADERS)

    def _load_cookies(self):
        self.cookie = DOWNLOAD_CONFIG.get("pixiv_cookie", "")
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def _save_cookie(self, cookie: str):
        self.cookie = cookie
        DOWNLOAD_CONFIG["pixiv_cookie"] = cookie
        self.session.headers["Cookie"] = cookie
        
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.py")
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            new_content = re.sub(
                r'("pixiv_cookie":\s*")[^"]*(")',
                f'\\1{cookie}\\2',
                content
            )
            
            if new_content != content:
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                tqdm.write(Colors.green("Cookie 已保存到配置文件喵！"))
        except Exception as e:
            tqdm.write(Colors.red(f"保存 Cookie 失败: {e}"))

    def _check_cookie_validity(self):
        if not self.cookie: return
        try:
            self.session.get(f"{self.BASE_URL}/ajax/user/extra", timeout=5)
        except Exception:
            pass

    @property
    def name(self) -> str:
        return "Pixiv Crawler"

    def can_handle(self, url: str) -> bool:
        targets = [
            "pixiv.net/users/", "pixiv.net/u/", "pixiv.net/en/users/",
            "pixiv.net/novel/series/", "pixiv.net/artworks/", "pixiv.net/novel/show"
        ]
        return any(t in url for t in targets)

    def download(self, url: str, output_dir: str, **kwargs) -> Tuple[bool, str, Optional[str]]:
        self._check_cookie_validity()
        if not self.cookie:
            tqdm.write(Colors.yellow("Pixiv 爬虫建议使用 Cookie 以获取完整作品 (含 R-18) 喵~"))
        
        mode, pid = self._parse_url(url)
        if not pid:
            return False, "无法解析 Pixiv URL (ID 未找到) 喵...", None

        tqdm.write(Colors.pink(f"识别模式: {mode} (ID: {pid})，正在获取列表喵..."))
        
        try:
            author_name, works = self._get_download_targets(mode, pid)
            tqdm.write(Colors.cyan(f"目标集合: {author_name}"))
        except Exception as e:
            return False, f"获取信息失败: {e}", None

        total_works = len(works['illusts']) + len(works['manga']) + len(works['novels'])
        tqdm.write(Colors.cyan(f"共找到 {total_works} 个作品 (插画: {len(works['illusts'])}, 漫画: {len(works['manga'])}, 小说: {len(works['novels'])})"))

        if total_works == 0:
            return True, "没有找到可以下载的作品喵...", None

        # Determine output directory
        from ..config import LIBRARY_DIR
        base_dir = output_dir if output_dir else LIBRARY_DIR
        author_dir = os.path.join(base_dir, self._sanitize_filename(author_name))
        os.makedirs(author_dir, exist_ok=True)
        
        results = {'success': 0, 'fail': 0}
        
        # Process Novels
        if works['novels']:
            self._process_batch(works['novels'], author_dir, "Novel", self._download_novel_safe, results)

        # Process Illusts/Manga
        illust_manga_ids = works['illusts'] + works['manga']
        if illust_manga_ids:
            self._process_batch(illust_manga_ids, author_dir, "Illust/Manga", 
                              lambda iid, d: self._download_illust_safe(iid, d, output_dir), results)

        return True, f"爬取完成喵！成功: {results['success']}, 失败: {results['fail']}", author_dir

    def _process_batch(self, items: List[str], save_dir: str, desc: str, func, stats: Dict):
        tqdm.write(Colors.yellow(f"--- 开始下载 {len(items)} 部 {desc} ---"))
        with tqdm(total=len(items), unit="work", desc=f"Downloading {desc}") as pbar:
            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
                futures = {executor.submit(func, item, save_dir): item for item in items}
                for future in as_completed(futures):
                    if future.result():
                        stats['success'] += 1
                    else:
                        stats['fail'] += 1
                    pbar.update(1)

    def _request(self, url: str, stream: bool = False, json_response: bool = True) -> Any:
        """Unified request helper with retry."""
        for attempt in range(self.MAX_RETRIES):
            try:
                res = self.session.get(url, timeout=self.TIMEOUT, stream=stream)
                if res.status_code == 200:
                    if json_response:
                        return res.json()
                    return res
                elif res.status_code == 404:
                    return None
            except Exception:
                pass
            time.sleep(1 + attempt)
        return None

    def _download_novel_safe(self, nid: str, save_dir: str) -> bool:
        try:
            return self._download_novel(nid, save_dir)
        except Exception as e:
            tqdm.write(Colors.red(f"小说 {nid} 下载失败: {e}"))
            return False

    def _download_illust_safe(self, iid: str, save_dir: str, temp_root: Optional[str] = None) -> bool:
        try:
            return self._download_illust(iid, save_dir, temp_root)
        except Exception as e:
            tqdm.write(Colors.red(f"漫画/插画 {iid} 下载失败: {e}"))
            return False

    def _parse_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        if m := re.search(r'novel/series/(\d+)', url): return 'SERIES', m.group(1)
        if m := re.search(r'users/(\d+)', url):
            uid = m.group(1)
            if 'bookmarks/novels' in url: return 'USER_BOOKMARKS_NOVELS', uid
            if 'illustrations' in url: return 'USER_ILLUSTS', uid
            if 'manga' in url: return 'USER_MANGA', uid
            if 'novels' in url: return 'USER_NOVELS', uid
            return 'USER_ALL', uid
        return None, None

    def _get_download_targets(self, mode: str, pid: str) -> Tuple[str, Dict[str, List[str]]]:
        works = {'illusts': [], 'manga': [], 'novels': []}
        author_name = "Unknown"
        
        if mode == 'SERIES':
            meta = self._get_series_metadata(pid)
            author_name = meta.get('author', f"Series_{pid}")
            
            raw_body = meta.get('raw_body', {})
            works['novels'] = raw_body.get('scraped_ids', [])
            
            if not works['novels']:
                works['novels'] = self._fetch_paginated_ids(
                    f"{self.BASE_URL}/ajax/novel/series/{pid}/content",
                    lambda x: x.get('page', {}).get('seriesContents', []) if isinstance(x, dict) and 'page' in x else x
                )
            
            # Traversal fallback
            if not works['novels'] and (first_id := raw_body.get('firstNovelId')):
                tqdm.write(Colors.yellow("列表获取失败，尝试通过链式遍历获取作品列表喵..."))
                works['novels'] = self._crawl_series_by_traversal(first_id)

        elif mode == 'USER_BOOKMARKS_NOVELS':
            author_name = f"{self._get_user_name(pid)}_Bookmarks"
            works['novels'] = self._get_bookmark_works(pid)
            
        else: # User modes
            author_name = self._get_user_name(pid)
            all_works = self._get_user_works(pid)
            if mode == 'USER_ALL': works = all_works
            elif mode == 'USER_ILLUSTS': works['illusts'] = all_works['illusts']
            elif mode == 'USER_MANGA': works['manga'] = all_works['manga']
            elif mode == 'USER_NOVELS': works['novels'] = all_works['novels']
                
        return author_name, works

    def _crawl_series_by_traversal(self, first_id: str) -> List[str]:
        ids = []
        current_id = str(first_id)
        visited = set()
        
        with tqdm(desc="遍历系列作品", unit="章", leave=False) as pbar:
            while current_id and current_id not in visited:
                ids.append(current_id)
                visited.add(current_id)
                pbar.update(1)
                
                data = self._request(f"{self.BASE_URL}/ajax/novel/{current_id}")
                if not data: break
                
                nav_data = data.get('body', {}).get('seriesNavData') or {}
                next_node = nav_data.get('next')
                
                if next_node and isinstance(next_node, dict):
                    next_id = str(next_node.get('id'))
                    if next_id == current_id: break
                    current_id = next_id
                else:
                    break
                time.sleep(0.3)
        return ids

    def _get_series_metadata(self, series_id: str) -> Dict:
        # 1. Try AJAX API
        self.session.headers.update({"Referer": f"{self.BASE_URL}/novel/series/{series_id}"})
        data = self._request(f"{self.BASE_URL}/ajax/novel/series/{series_id}")
        
        if data and (body := data.get('body')):
            return {'title': body.get('title'), 'author': body.get('userName'), 'raw_body': body}
        
        # 2. Fallback: Scrape HTML
        tqdm.write(Colors.yellow("Pixiv API 获取失败 (404/Error)，尝试网页解析模式喵..."))
        res = self._request(f"{self.BASE_URL}/novel/series/{series_id}", json_response=False)
        if res:
            return self._scrape_metadata_from_html(res.text, series_id)
            
        return {}

    def _scrape_metadata_from_html(self, html_content: str, series_id: str) -> Dict:
        title_match = re.search(r'<title>(.*?)(?:/|\||\[).*?</title>', html_content)
        title = title_match.group(1).strip() if title_match else f"Series_{series_id}"
        
        ids = []
        # Method 1: Regex Scraping (Links)
        ids.extend(re.findall(r'/novel/show\.php\?id=(\d+)', html_content))
        if not ids:
            ids.extend(re.findall(r'/novel/(\d+)"', html_content))
        
        # Method 2: __NEXT_DATA__
        if not ids:
            if next_match := re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', html_content, re.DOTALL):
                try:
                    data = json.loads(next_match.group(1))
                    contents = data.get('props', {}).get('pageProps', {}).get('seriesContents', [])
                    if contents:
                        ids.extend([str(x['id']) for x in contents if isinstance(x, dict) and 'id' in x])
                except Exception: pass
        
        # Method 3: global-data
        if not ids:
            if meta_match := re.search(r'<meta\s+[^>]*name="global-data"\s+[^>]*content="([^"]+)"', html_content):
                try:
                    json_str = html.unescape(meta_match.group(1))
                    if match := re.search(r'"seriesContents":\s*(\[[^\]]+\])', json_str):
                        ids.extend(re.findall(r'"id":\s*"?(\d+)"?', match.group(1)))
                except Exception: pass

        ids = list(dict.fromkeys(ids)) # Deduplicate
        
        if ids:
            tqdm.write(Colors.pink(f"网页解析成功: 找到 {len(ids)} 个作品喵！"))
            return {
                'title': title, 
                'author': 'Unknown_Scraped', 
                'raw_body': {'scraped_ids': ids, 'firstNovelId': ids[0]}
            }
        
        tqdm.write(Colors.yellow("网页解析警告: 未找到任何作品ID，可能是R-18权限问题喵！"))
        return {}

    def _fetch_paginated_ids(self, base_url: str, extractor) -> List[str]:
        ids = []
        offset, limit = 0, 30
        while True:
            url = f"{base_url}?limit={limit}&last_order={offset}&order_by=asc" if "?" not in base_url else f"{base_url}&offset={offset}&limit={limit}&rest=show"
            data = self._request(url)
            if not data: break
            
            body = data.get('body', {})
            items = extractor(body)
            if not items: break
            
            batch = [str(x['id']) for x in items if isinstance(x, dict) and 'id' in x]
            ids.extend(batch)
            
            if len(items) < limit: break
            offset += len(items)
            time.sleep(0.5)
        return ids

    def _get_bookmark_works(self, user_id: str) -> List[str]:
        return self._fetch_paginated_ids(
            f"{self.BASE_URL}/ajax/user/{user_id}/novels/bookmarks",
            lambda b: b.get('works', [])
        )

    def _get_user_name(self, user_id: str) -> str:
        data = self._request(f"{self.BASE_URL}/ajax/user/{user_id}?full=1")
        return data.get('body', {}).get('name', f"User_{user_id}") if data else f"User_{user_id}"

    def _get_user_works(self, user_id: str) -> Dict[str, List[str]]:
        data = self._request(f"{self.BASE_URL}/ajax/user/{user_id}/profile/all")
        body = data.get('body', {}) if data else {}
        return {
            'illusts': list(body.get('illusts', {}).keys()),
            'manga': list(body.get('manga', {}).keys()),
            'novels': list(body.get('novels', {}).keys())
        }

    def _download_novel(self, nid: str, save_dir: str) -> bool:
        data = self._request(f"{self.BASE_URL}/ajax/novel/{nid}")
        if not data or data.get('error'): return False
        
        body = data.get('body', {})
        if not body: return False

        title = body.get('title', f"novel_{nid}")
        content = body.get('content', '')
        series_title = (body.get('seriesNavData') or {}).get('title', '')
        
        tags = [t.get('tag') for t in (body.get('tags') or {}).get('tags', []) if t.get('tag')]
        author_name = body.get('userName', '')
        
        header = f"标题: {title}\n作者: {author_name}\n"
        if tags: header += f"标签: {','.join(tags)}\n"
        if series_title: header += f"系列: {series_title}\n"
            
        full_text = f"{header}\n简介:\n{body.get('description', '')}\n\n{content}"
        
        filename = f"{self._sanitize_filename(title)}.txt"
        with open(os.path.join(save_dir, filename), 'w', encoding='utf-8') as f:
            f.write(full_text)
        return True

    def _download_illust(self, iid: str, save_dir: str, temp_root: Optional[str] = None) -> bool:
        # 1. Fetch Pages
        data = self._request(f"{self.BASE_URL}/ajax/illust/{iid}/pages")
        if not data: return False
        pages = data.get('body', [])
        if not pages: return False

        # 2. Fetch Metadata
        meta_data = self._request(f"{self.BASE_URL}/ajax/illust/{iid}")
        meta_body = meta_data.get('body', {}) if meta_data else {}
        
        title = meta_body.get('title') or f"illust_{iid}"
        title_safe = self._sanitize_filename(f"{title} ({iid})")
        cbz_path = os.path.join(save_dir, f"{title_safe}.cbz")
        
        if os.path.exists(cbz_path) and os.path.getsize(cbz_path) > 0:
            tqdm.write(Colors.green(f"已存在跳过: {title_safe}"))
            return True

        # 3. Setup Temp Dir
        work_dir = os.path.join(temp_root or save_dir, f"_temp_{title_safe}")
        os.makedirs(work_dir, exist_ok=True)
        
        # 4. Download Images
        downloaded_images = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            tasks = []
            for idx, page in enumerate(pages):
                if url := page.get('urls', {}).get('original'):
                    fname = f"{idx:04d}_{os.path.basename(url)}"
                    path = os.path.join(work_dir, fname)
                    tasks.append((url, path))
            
            futures = {executor.submit(self._download_image, url, path): path for url, path in tasks}
            iterator = as_completed(futures)
            if len(tasks) > 5:
                iterator = tqdm(iterator, total=len(tasks), leave=False, unit="img", desc=f"DL {title[:10]}...")
                
            for future in iterator:
                if future.result(): downloaded_images.append(futures[future])

        if not downloaded_images:
            shutil.rmtree(work_dir, ignore_errors=True)
            return False

        # 5. Create CBZ
        downloaded_images.sort()
        success = self._create_cbz(downloaded_images, meta_body, cbz_path, iid)
        
        shutil.rmtree(work_dir, ignore_errors=True)
        return success

    def _download_image(self, url: str, save_path: str) -> bool:
        res = self._request(url, stream=True, json_response=False)
        if not res: return False
        
        try:
            with open(save_path, 'wb') as f:
                for chunk in res.iter_content(8192):
                    f.write(chunk)
            return True
        except Exception:
            return False

    def _create_cbz(self, images: List[str], meta: Dict, output_path: str, iid: str) -> bool:
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_STORED) as zf:
                for i, img_path in enumerate(images):
                    ext = os.path.splitext(img_path)[1]
                    zf.write(img_path, f"{i+1:03d}{ext}")
                
                # ComicInfo.xml
                root = ET.Element("ComicInfo")
                ET.SubElement(root, "Title").text = meta.get('title', '')
                ET.SubElement(root, "Series").text = (meta.get('seriesNavData') or {}).get('title', '')
                ET.SubElement(root, "Summary").text = meta.get('description', '')
                ET.SubElement(root, "Writer").text = meta.get('userName', '')
                ET.SubElement(root, "PageCount").text = str(len(images))
                ET.SubElement(root, "Web").text = f"{self.BASE_URL}/artworks/{iid}"
                
                tags = [t.get('tag') for t in (meta.get('tags') or {}).get('tags', []) if t.get('tag')]
                if tags: ET.SubElement(root, "Tags").text = ",".join(tags).replace(",", "，")
                
                if date_str := (meta.get('createDate') or meta.get('uploadDate')):
                    try:
                        dt = datetime.fromisoformat(date_str)
                        ET.SubElement(root, "Year").text = str(dt.year)
                        ET.SubElement(root, "Month").text = str(dt.month)
                        ET.SubElement(root, "Day").text = str(dt.day)
                    except: pass
                    
                if hasattr(ET, 'indent'): ET.indent(root, space="  ")
                zf.writestr("ComicInfo.xml", ET.tostring(root, encoding='utf-8', method='xml'))
                
            tqdm.write(Colors.green(f"已生成 CBZ: {os.path.basename(output_path)}"))
            return True
        except Exception as e:
            tqdm.write(Colors.red(f"CBZ 打包失败: {e}"))
            return False

    def _sanitize_filename(self, name: str) -> str:
        table = {'/': '／', '\\': '＼', '?': '？', ':': '：', '*': '＊', '"': '＂', '<': '＜', '>': '＞', '|': '｜'}
        cleaned = "".join(table.get(c, c) for c in name)
        return cleaned[:60].strip()
