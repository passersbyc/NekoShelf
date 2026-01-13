import os
import re
import time
import json
import shutil
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

from .base import DownloadPlugin
from .utils import sanitize_filename, set_file_time, create_cbz, create_pdf
from ...utils import Colors
from ... import config
from ...database import DatabaseManager

class PixivPlugin(DownloadPlugin):
    BASE_URL = "https://www.pixiv.net"

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self._configure_session(config.get_download_config(reload=True))
        self._load_cookies(config.get_download_config(reload=False))

    def _configure_session(self, cfg: Dict[str, Any]):
        self.MAX_RETRIES = int(cfg.get("max_retries", 3) or 3)
        self.TIMEOUT = int(cfg.get("timeout", 10) or 10)
        self.MAX_WORKERS = int(cfg.get("max_workers", 5) or 5)
        
        retries = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=1, 
            status_forcelist=[500, 502, 503, 504] # 移除 429，由应用层控制
        )
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        headers = {
            "User-Agent": cfg.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"),
            "Referer": "https://www.pixiv.net/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        self.session.headers.update(headers)

    def _load_cookies(self, cfg: Dict[str, Any]):
        self.cookie = cfg.get("pixiv_cookie", "")
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def _check_cookie_validity(self):
        if not self.cookie: return
        try:
            res = self.session.get(f"{self.BASE_URL}/ajax/user/extra", timeout=5)
            if res.status_code == 200:
                data = res.json()
                if not data.get('body'):
                    tqdm.write(Colors.yellow("Cookie 可能已过期 (API 返回空 Body)，建议更新喵~"))
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

    def get_artist_name(self, url: str) -> str:
        mode, pid = self._parse_url(url)
        if not pid:
            return ""
        
        # 尝试复用 _get_user_name 逻辑
        if mode in ['USER_ALL', 'USER_ILLUSTS', 'USER_MANGA', 'USER_NOVELS']:
             return self._get_user_name(pid)
        
        # 对于其他模式 (如 Series, Single Work)，尝试获取作者
        # 但这里主要针对 follow 命令，通常是用户页
        return ""

    def download(self, url: str, output_dir: str, **kwargs) -> Tuple[bool, str, Optional[str]]:
        quiet = kwargs.get('quiet', False)
        cfg = config.get_download_config(reload=True)
        self._configure_session(cfg)
        self._load_cookies(cfg)
        
        # 获取数据库实例
        db = kwargs.get('db')

        self._check_cookie_validity()
        if not self.cookie and not quiet:
            tqdm.write(Colors.yellow("Pixiv 爬虫建议使用 Cookie 以获取完整作品 (含 R-18) 喵~"))
        
        mode, pid = self._parse_url(url)
        if not pid:
            return False, "无法解析 Pixiv URL (ID 未找到) 喵...", None

        if not quiet:
            tqdm.write(Colors.pink(f"识别模式: {mode} (ID: {pid})，正在获取列表喵..."))
        
        try:
            author_name, works = self._get_download_targets(mode, pid, quiet=quiet)
            if not quiet:
                tqdm.write(Colors.cyan(f"目标集合: {author_name}"))
        except Exception as e:
            return False, f"获取信息失败: {e}", None

        total_works = len(works['illusts']) + len(works['manga']) + len(works['novels'])
        if not quiet:
            tqdm.write(Colors.cyan(f"共找到 {total_works} 个作品 (插画: {len(works['illusts'])}, 漫画: {len(works['manga'])}, 小说: {len(works['novels'])})"))

        if total_works == 0:
            return True, "没有找到可以下载的作品喵...", None

        # 如果静默模式下发现了新作品，提示一下
        if quiet and total_works > 0:
             tqdm.write(Colors.green(f"发现新作品: {total_works} 个 (插画: {len(works['illusts'])}, 漫画: {len(works['manga'])}, 小说: {len(works['novels'])})"))

        base_dir = output_dir if output_dir else config.get_paths(reload=False)[0]
        author_dir = os.path.join(base_dir, sanitize_filename(author_name))
        os.makedirs(author_dir, exist_ok=True)
        
        results = {'success': 0, 'fail': 0}
        
        if works['novels']:
            self._process_batch(works['novels'], author_dir, "Novel", 
                              lambda nid, d: self._download_novel_safe(nid, d), 
                              results, quiet=quiet)

        illust_manga_ids = works['illusts'] + works['manga']
        if illust_manga_ids:
            self._process_batch(illust_manga_ids, author_dir, "Illust/Manga", 
                              lambda iid, d: self._download_illust_safe(iid, d), 
                              results, quiet=quiet)

        return True, f"爬取完成喵！成功: {results['success']}, 失败: {results['fail']}", author_dir

    def _process_batch(self, items: List[str], save_dir: str, desc: str, func, stats: Dict, quiet: bool = False):
        if not quiet:
            tqdm.write(Colors.yellow(f"--- 开始下载 {len(items)} 部 {desc} ---"))
        
        # 动态调整并发数：如果任务很多，保守一点，避免被封
        workers = self.MAX_WORKERS
        if len(items) > 50 and workers > 3:
            workers = 3
            
        with tqdm(total=len(items), unit="work", desc=f"Downloading {desc}") as pbar:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}
                for item in items:
                    futures[executor.submit(func, item, save_dir)] = item
                    # 提交任务时稍微错开一点时间，避免瞬间并发峰值
                    time.sleep(0.1)
                    
                for future in as_completed(futures):
                    if future.result():
                        stats['success'] += 1
                    else:
                        stats['fail'] += 1
                    pbar.update(1)

    def _request(self, url: str, stream: bool = False, json_response: bool = True) -> Any:
        import random
        
        # 指数退避策略: 基础等待时间 * (2 ^ 重试次数) + 随机抖动
        base_wait = 5 
        
        for attempt in range(self.MAX_RETRIES):
            try:
                res = self.session.get(url, timeout=self.TIMEOUT, stream=stream)
                
                if res.status_code == 200:
                    if json_response:
                        return res.json()
                    return res
                    
                elif res.status_code == 404:
                    return None
                    
                elif res.status_code == 429:
                    # 指数退避
                    wait_time = base_wait * (2 ** attempt) + random.uniform(1, 5)
                    # 限制最大等待时间 (例如 120秒)
                    wait_time = min(wait_time, 120)
                    
                    tqdm.write(Colors.yellow(f"触发限流 (429)，冷却 {wait_time:.1f}秒后重试... ({attempt+1}/{self.MAX_RETRIES})"))
                    time.sleep(wait_time)
                    continue
                    
                else:
                    tqdm.write(Colors.yellow(f"请求异常 (Code: {res.status_code}): {url}"))
                    
            except Exception as e:
                if attempt > 0: 
                    tqdm.write(Colors.yellow(f"请求超时/失败 ({attempt+1}/{self.MAX_RETRIES}): {e} -> {url}"))
                pass
            
            # 普通重试的间隔
            sleep_time = 2 + attempt + random.random()
            time.sleep(sleep_time)
            
        tqdm.write(Colors.red(f"请求彻底失败: {url}"))
        return None

    def _download_novel_safe(self, nid: str, save_dir: str) -> bool:
        db = None
        try:
            db = DatabaseManager(config.DB_FILE)
            return self._download_novel(nid, save_dir, db=db)
        except Exception as e:
            tqdm.write(Colors.red(f"小说 {nid} 下载失败: {e}"))
            return False
        finally:
            if db: db.close()

    def _download_illust_safe(self, iid: str, save_dir: str, temp_root: Optional[str] = None) -> bool:
        db = None
        try:
            db = DatabaseManager(config.DB_FILE)
            return self._download_illust(iid, save_dir, temp_root, db=db)
        except Exception as e:
            tqdm.write(Colors.red(f"插画/漫画 {iid} 下载失败: {e}"))
            return False
        finally:
            if db: db.close()

    def _parse_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        if m := re.search(r'novel/series/(\d+)', url): return 'SERIES', m.group(1)
        if m := re.search(r'novel/show\.php\?id=(\d+)', url): return 'NOVEL_SINGLE', m.group(1)
        if m := re.search(r'artworks/(\d+)', url): return 'ILLUST_SINGLE', m.group(1)
        if m := re.search(r'users/(\d+)', url):
            uid = m.group(1)
            if 'bookmarks/novels' in url: return 'USER_BOOKMARKS_NOVELS', uid
            if 'bookmarks/artworks' in url: return 'USER_BOOKMARKS_ILLUSTS', uid
            if 'illustrations' in url: return 'USER_ILLUSTS', uid
            if 'manga' in url: return 'USER_MANGA', uid
            if 'novels' in url: return 'USER_NOVELS', uid
            return 'USER_ALL', uid
        return None, None

    def _get_download_targets(self, mode: str, pid: str, quiet: bool = False) -> Tuple[str, Dict[str, List[str]]]:
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
            
            if not works['novels'] and (first_id := raw_body.get('firstNovelId')):
                tqdm.write(Colors.yellow("列表获取失败，尝试通过链式遍历获取作品列表喵..."))
                works['novels'] = self._crawl_series_by_traversal(first_id)

        elif mode == 'NOVEL_SINGLE':
            works['novels'] = [pid]
            try:
                data = self._request(f"{self.BASE_URL}/ajax/novel/{pid}")
                if data and (body := data.get('body')):
                    author_name = body.get('userName', f"User_{body.get('userId', 'Unknown')}")
            except:
                pass

        elif mode == 'ILLUST_SINGLE':
            works['illusts'] = [pid] 
            try:
                data = self._request(f"{self.BASE_URL}/ajax/illust/{pid}")
                if data and (body := data.get('body')):
                    author_name = body.get('userName', f"User_{body.get('userId', 'Unknown')}")
            except:
                pass

        elif mode == 'USER_BOOKMARKS_NOVELS':
            author_name = f"{self._get_user_name(pid)}_Bookmarks"
            works['novels'] = self._get_bookmark_works(pid)

        elif mode == 'USER_BOOKMARKS_ILLUSTS':
            author_name = f"{self._get_user_name(pid)}_Bookmarks_Artworks"
            works['illusts'] = self._fetch_paginated_ids(
                f"{self.BASE_URL}/ajax/user/{pid}/illusts/bookmarks",
                lambda b: b.get('works', [])
            )
            
        else:
            author_name = self._get_user_name(pid)
            all_works = self._get_user_works(pid)
            if mode == 'USER_ALL': works = all_works
            elif mode == 'USER_ILLUSTS': works['illusts'] = all_works['illusts']
            elif mode == 'USER_MANGA': works['manga'] = all_works['manga']
            elif mode == 'USER_NOVELS': works['novels'] = all_works['novels']
        
        # 过滤已下载的作品
        db = None
        try:
            db = DatabaseManager(config.DB_FILE)
            for wtype in ['illusts', 'manga', 'novels']:
                if not works[wtype]: continue
                
                original_count = len(works[wtype])
                new_list = []
                for wid in works[wtype]:
                    # 构造 work_id (illust:xxx, novel:xxx)
                    prefix = "novel" if wtype == 'novels' else "illust"
                    full_id = f"{prefix}:{wid}"
                    
                    if not db.get_download_record("pixiv", full_id):
                        new_list.append(wid)
                
                works[wtype] = new_list
                skipped = original_count - len(new_list)
                if skipped > 0 and not quiet:
                    tqdm.write(Colors.pink(f"已跳过 {skipped} 个已下载的 {wtype} 喵~"))
        except Exception as e:
             tqdm.write(Colors.yellow(f"检查下载记录失败: {e}，将尝试下载所有内容"))
        finally:
            if db: db.close()

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
        self.session.headers.update({"Referer": f"{self.BASE_URL}/novel/series/{series_id}"})
        data = self._request(f"{self.BASE_URL}/ajax/novel/series/{series_id}")
        
        if data and (body := data.get('body')):
            return {'title': body.get('title'), 'author': body.get('userName'), 'raw_body': body}
        
        tqdm.write(Colors.yellow("Pixiv API 获取失败 (404/Error)，尝试网页解析模式喵..."))
        res = self._request(f"{self.BASE_URL}/novel/series/{series_id}", json_response=False)
        if res:
            return self._scrape_metadata_from_html(res.text, series_id)
            
        return {}

    def _scrape_metadata_from_html(self, html_content: str, series_id: str) -> Dict:
        title_match = re.search(r'<title>(.*?)(?:/|\||\[).*?</title>', html_content)
        title = title_match.group(1).strip() if title_match else f"Series_{series_id}"
        
        ids = []
        ids.extend(re.findall(r'/novel/show\.php\?id=(\d+)', html_content))
        if not ids:
            ids.extend(re.findall(r'/novel/(\d+)"', html_content))
        
        if not ids:
            if next_match := re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', html_content, re.DOTALL):
                try:
                    data = json.loads(next_match.group(1))
                    contents = data.get('props', {}).get('pageProps', {}).get('seriesContents', [])
                    if contents:
                        ids.extend([str(x['id']) for x in contents if isinstance(x, dict) and 'id' in x])
                except Exception: pass
        
        if not ids:
            if meta_match := re.search(r'<meta\s+[^>]*name="global-data"\s+[^>]*content="([^"]+)"', html_content):
                try:
                    json_str = html.unescape(meta_match.group(1))
                    if match := re.search(r'"seriesContents":\s*(\[[^\]]+\])', json_str):
                        ids.extend(re.findall(r'"id":\s*"?(\d+)"?', match.group(1)))
                except Exception: pass

        ids = list(dict.fromkeys(ids))
        
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
        if data and (name := data.get('body', {}).get('name')):
            return name
            
        tqdm.write(Colors.yellow(f"API 获取用户名失败，尝试解析主页喵..."))
        res = self._request(f"{self.BASE_URL}/users/{user_id}", json_response=False)
        if res:
            text = res.text
            # Try og:title
            if m := re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', text):
                clean = re.sub(r'\s-\s(?:pixiv|插画|漫画).*$', '', m.group(1)).strip()
                if clean: return clean
                
            # Try twitter:title
            if m := re.search(r'<meta\s+name="twitter:title"\s+content="([^"]+)"', text):
                clean = re.sub(r'\s-\s(?:pixiv|插画|漫画).*$', '', m.group(1)).strip()
                if clean: return clean

            # Try title tag with flexible separator
            if m := re.search(r'<title>(.*?)(?:\s-\s(?:pixiv|插画|漫画)|\|| - ).*?</title>', text):
                return m.group(1).strip()
                
        return f"User_{user_id}"

    def _get_user_works(self, user_id: str) -> Dict[str, List[str]]:
        data = self._request(f"{self.BASE_URL}/ajax/user/{user_id}/profile/all")
        
        # Check if API request was successful
        if data and not data.get('error'):
            body = data.get('body', {})
            def _safe_keys(val):
                return list(val.keys()) if isinstance(val, dict) else []

            return {
                'illusts': _safe_keys(body.get('illusts')),
                'manga': _safe_keys(body.get('manga')),
                'novels': _safe_keys(body.get('novels'))
            }
            
        # Fallback: Scrape from HTML
        tqdm.write(Colors.yellow(f"API 获取作品列表失败，尝试解析主页喵..."))
        res = self._request(f"{self.BASE_URL}/users/{user_id}", json_response=False)
        if not res:
            return {'illusts': [], 'manga': [], 'novels': []}
            
        return self._scrape_works_from_html(res.text)

    def _scrape_works_from_html(self, html_content: str) -> Dict[str, List[str]]:
        works = {'illusts': [], 'manga': [], 'novels': []}
        
        # Try global-data
        if meta_match := re.search(r'<meta\s+[^>]*name="global-data"\s+[^>]*content="([^"]+)"', html_content):
            try:
                json_str = html.unescape(meta_match.group(1))
                data = json.loads(json_str)
                
                def _extract_ids(key):
                    if val := data.get(key):
                        return list(val.keys()) if isinstance(val, dict) else []
                    return []
                
                works['illusts'] = _extract_ids('illusts')
                works['manga'] = _extract_ids('manga')
                works['novels'] = _extract_ids('novels')
                
                total = len(works['illusts']) + len(works['manga']) + len(works['novels'])
                if total > 0:
                    tqdm.write(Colors.pink(f"网页解析成功: 找到 {total} 个作品喵！"))
                    return works
            except Exception as e:
                tqdm.write(Colors.red(f"解析 global-data 失败: {e}"))
        
        return works

    def _download_novel(self, nid: str, save_dir: str, db=None) -> bool:
        # Check if file already exists by ID to avoid API call
        if os.path.exists(save_dir):
            target_pattern = f"(pixiv:novel:{nid})"
            # 1. 检查本地文件系统
            for fname in os.listdir(save_dir):
                if target_pattern in fname and fname.endswith(".txt"):
                    fpath = os.path.join(save_dir, fname)
                    if os.path.getsize(fpath) > 0:
                        # tqdm.write(Colors.green(f"已存在跳过: {fname}")) # 减少刷屏
                        return True
                        
        # 2. 检查数据库记录 (防止搬运后再次下载)
        if db:
            record = db.get_download_record("pixiv", f"novel:{nid}")
            if record:
                # 进一步检查文件是否存在（如果被手动删除了，可能需要重新下载，但这里我们假设记录存在即已完成）
                # 或者我们可以根据需求：如果有记录且文件存在->跳过；有记录但文件不存在->重新下载
                # 这里为了性能，先简单判断：有记录就跳过
                return True

        data = self._request(f"{self.BASE_URL}/ajax/novel/{nid}")
        if not data or data.get('error'): return False
        
        body = data.get('body', {})
        if not body: return False

        title = body.get('title', f"novel_{nid}")
        content = body.get('content', '')
        series_title = (body.get('seriesNavData') or {}).get('title', '')
        
        tags = [t.get('tag') for t in (body.get('tags') or {}).get('tags', []) if t.get('tag')]
        author_name = body.get('userName') or "Unknown"
        
        header = f"标题: {title}\n作者: {author_name}\n"
        if tags: header += f"标签: {','.join(tags)}\n"
        if series_title: header += f"系列: {series_title}\n"
            
        full_text = f"{header}\n简介:\n{body.get('description', '')}\n\n{content}"
        
        base_name = sanitize_filename(f"{author_name} - {title} (pixiv:novel:{nid})")
        filename = f"{base_name}.txt"
        file_path = os.path.join(save_dir, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(full_text)
            
        set_file_time(file_path, body.get('createDate') or body.get('uploadDate'))
        
        # 下载完成后，记录到数据库
        if db:
            # 假设 title 就是标题
            db.add_download_record(
                platform="pixiv",
                work_id=f"novel:{nid}",
                title=title,
                author=author_name,
                local_path=file_path
            )

        return True

    def _download_illust(self, iid: str, save_dir: str, temp_root: Optional[str] = None, db=None) -> bool:
        cfg = config.get_download_config(reload=False)
        
        # 检查本地文件是否存在
        # 这里只是粗略检查，因为不知道具体的格式
        if os.path.exists(save_dir):
             target_pattern = f"(pixiv:illust:{iid})"
             for fname in os.listdir(save_dir):
                 if target_pattern in fname and os.path.getsize(os.path.join(save_dir, fname)) > 0:
                     return True
        
        # 检查数据库记录
        if db:
            record = db.get_download_record("pixiv", f"illust:{iid}")
            if record:
                return True

        data = self._request(f"{self.BASE_URL}/ajax/illust/{iid}/pages")
        if not data: return False
        pages = data.get('body', [])
        if not pages: return False

        meta_data = self._request(f"{self.BASE_URL}/ajax/illust/{iid}")
        meta_body = meta_data.get('body', {}) if meta_data else {}
        
        title = meta_body.get('title') or f"illust_{iid}"
        author_name = meta_body.get('userName') or "Unknown"
        base_name = sanitize_filename(f"{author_name} - {title} (pixiv:illust:{iid})")
        
        fmt = str(cfg.get("pixiv_format", "pdf") or "pdf").lower()
        if fmt not in ["cbz", "pdf"]: fmt = "pdf"
        
        output_ext = f".{fmt}"
        output_path = os.path.join(save_dir, f"{base_name}{output_ext}")
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            # tqdm.write(Colors.green(f"已存在跳过: {base_name}{output_ext}"))
            return True

        work_dir = os.path.join(temp_root or save_dir, f"_temp_{base_name}")
        os.makedirs(work_dir, exist_ok=True)
        
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

        downloaded_images.sort()
        
        if len(downloaded_images) < len(tasks):
            missing = len(tasks) - len(downloaded_images)
            tqdm.write(Colors.yellow(f"警告: 有 {missing} 张图片下载失败，文件内容不完整！"))

        if fmt == "cbz":
            success = create_cbz(
                images=downloaded_images,
                output_path=output_path,
                title=meta_body.get('title', ''),
                author=meta_body.get('userName', ''),
                description=meta_body.get('description', ''),
                series=(meta_body.get('seriesNavData') or {}).get('title', ''),
                source_url=f"{self.BASE_URL}/artworks/{iid}",
                tags=[t.get('tag') for t in (meta_body.get('tags') or {}).get('tags', []) if t.get('tag')],
                published_time=meta_body.get('createDate') or meta_body.get('uploadDate')
            )
        else:
            success = create_pdf(
                images=downloaded_images,
                output_path=output_path,
                title=meta_body.get('title', ''),
                author=meta_body.get('userName', ''),
                tags=[t.get('tag') for t in (meta_body.get('tags') or {}).get('tags', []) if t.get('tag')],
                published_time=meta_body.get('createDate') or meta_body.get('uploadDate')
            )
        
        shutil.rmtree(work_dir, ignore_errors=True)

        # 下载完成后，记录到数据库
        if success and db:
            db.add_download_record(
                platform="pixiv",
                work_id=f"illust:{iid}",
                title=title,
                author=author_name,
                local_path=output_path
            )

        return success

    def _download_image(self, url: str, save_path: str) -> bool:
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
        except Exception:
            pass

        existing = 0
        try:
            if os.path.exists(save_path):
                existing = os.path.getsize(save_path)
        except Exception:
            existing = 0

        headers = {}
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"

        try:
            res = self.session.get(url, timeout=self.TIMEOUT, stream=True, headers=headers or None)
        except Exception:
            res = None

        if not res:
            return False

        if res.status_code in (416,):
            try:
                if existing > 0:
                    return True
            except Exception:
                pass
            return False

        if existing > 0 and res.status_code != 206:
            try:
                os.remove(save_path)
            except Exception:
                pass
            existing = 0

        try:
            res.raise_for_status()
        except Exception:
            return False

        mode = 'ab' if existing > 0 and res.status_code == 206 else 'wb'
        try:
            with open(save_path, mode) as f:
                for chunk in res.iter_content(8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception:
            return False
