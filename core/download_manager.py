from .plugins.download import DownloadPlugin, CommonPlugin, PixivPlugin, KemonoPlugin

class DownloadManager:
    def __init__(self):
        self.plugins: list[DownloadPlugin] = [
            PixivPlugin(),
            KemonoPlugin(),
            CommonPlugin() # CommonPlugin should be the last one as a fallback
        ]

    def download(self, url, download_dir="./downloads", **kwargs):
        r = self.download_with_meta(url, download_dir=download_dir, **kwargs)
        return bool(r.get("success")), str(r.get("message") or ""), r.get("output_path")

    def download_with_meta(self, url, download_dir="./downloads", **kwargs):
        for plugin in self.plugins:
            if plugin.can_handle(url):
                ok, msg, out = plugin.download(url, download_dir, **kwargs)
                return {
                    "success": bool(ok),
                    "message": msg,
                    "output_path": out,
                    "plugin": getattr(plugin, "name", None),
                }

        return {"success": False, "message": "没有找到合适的下载插件喵...", "output_path": None, "plugin": None}
