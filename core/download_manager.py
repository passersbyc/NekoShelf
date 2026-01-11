from .download_plugins.base import DownloadPlugin
from .download_plugins.common import CommonPlugin
from .download_plugins.pixiv import PixivPlugin

class DownloadManager:
    def __init__(self):
        self.plugins: list[DownloadPlugin] = [
            PixivPlugin(),
            CommonPlugin() # CommonPlugin should be the last one as a fallback
        ]

    def download(self, url, download_dir="./downloads", **kwargs):
        """
        Dispatch the download task to the appropriate plugin.
        """
        for plugin in self.plugins:
            if plugin.can_handle(url):
                return plugin.download(url, download_dir, **kwargs)
        
        return False, "没有找到合适的下载插件喵...", None
