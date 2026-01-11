import os
import requests
import re
import urllib.parse
from .base import DownloadPlugin
from ..utils import Colors
from ..config import DOWNLOAD_CONFIG

class CommonPlugin(DownloadPlugin):
    @property
    def name(self) -> str:
        return "Common Downloader"

    def can_handle(self, url: str) -> bool:
        return True  # Fallback plugin

    def download(self, url: str, output_dir: str, **kwargs) -> tuple[bool, str, str]:
        try:
            # Setup headers
            headers = {
                'User-Agent': DOWNLOAD_CONFIG.get("user_agent", 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36')
            }

            print(Colors.cyan(f"正在请求链接: {url} ..."))
            
            # Stream request
            with requests.get(url, stream=True, headers=headers, verify=False, timeout=DOWNLOAD_CONFIG.get("timeout", 10)) as r:
                r.raise_for_status()
                
                # Get filename
                filename = self._get_filename(url, r.headers)
                dest_path = os.path.join(output_dir, filename)
                
                total_size = int(r.headers.get('content-length', 0))
                
                with open(dest_path, 'wb') as f:
                    if total_size == 0:
                        f.write(r.content)
                    else:
                        downloaded = 0
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                self._print_progress(downloaded, total_size)
                print() # Newline

            return True, f"下载成功喵！已保存到: {dest_path}", dest_path

        except Exception as e:
            return False, f"普通下载失败喵: {e}", None

    def _get_filename(self, url, headers):
        filename = None
        cd = headers.get("content-disposition")
        if cd:
            fnames = re.findall(r'filename="?([^";]+)"?', cd)
            if fnames:
                filename = fnames[0]
        
        if not filename:
            path = urllib.parse.urlparse(url).path
            filename = os.path.basename(path)
            
        if not filename:
            filename = "downloaded_file"
            
        return filename

    def _print_progress(self, downloaded, total):
        percent = (downloaded / total) * 100
        print(f"\r下载进度: {percent:.1f}% ({downloaded/1024/1024:.1f}MB)", end="")
