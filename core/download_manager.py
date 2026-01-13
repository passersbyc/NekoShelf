from typing import Optional
from .plugins.download import DownloadPlugin, CommonPlugin, PixivPlugin, KemonoPlugin

class DownloadManager:
    def __init__(self):
        self.plugins: list[DownloadPlugin] = [
            PixivPlugin(),
            KemonoPlugin(),
            CommonPlugin() # CommonPlugin should be the last one as a fallback
        ]

    def get_plugin(self, url: str) -> Optional[DownloadPlugin]:
        for plugin in self.plugins:
            if plugin.can_handle(url):
                return plugin
        return None

    def download(self, url, download_dir="./downloads", **kwargs):
        r = self.download_with_meta(url, download_dir=download_dir, **kwargs)
        return bool(r.get("success")), str(r.get("message") or ""), r.get("output_path")

    def download_with_meta(self, url, download_dir="./downloads", **kwargs):
        for plugin in self.plugins:
            if plugin.can_handle(url):
                # 将 db 实例传递给插件，以便进行增量更新检查
                # 注意：kwargs 中可能已经包含了 db，如果没有则尝试从上下文获取（如果有的话）
                # 这里假设调用方 (DownloadImportService) 会将 db 放入 kwargs 或者插件不需要 db
                # 但为了安全起见，我们在 DownloadImportService 中调用时注入 db
                
                ok, msg, out = plugin.download(url, download_dir, **kwargs)
                return {
                    "success": bool(ok),
                    "message": msg,
                    "output_path": out,
                    "plugin": getattr(plugin, "name", None),
                }

        return {"success": False, "message": "没有找到合适的下载插件喵...", "output_path": None, "plugin": None}
