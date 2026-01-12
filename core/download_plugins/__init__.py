import sys

from core.plugins.download import CommonPlugin, DownloadPlugin, KemonoPlugin, PixivPlugin

m = sys.modules[__name__]
m.DownloadPlugin = DownloadPlugin
m.CommonPlugin = CommonPlugin
m.KemonoPlugin = KemonoPlugin
m.PixivPlugin = PixivPlugin

__all__ = ["DownloadPlugin", "CommonPlugin", "KemonoPlugin", "PixivPlugin"]
