import shlex
import os
import urllib.request
import urllib.parse

from .utils import Colors, simple_complete


class DownloadCommandsMixin:
    def do_download(self, arg):
        """下载书籍: download <URL> [--dir=目录] [--series=系列]

        功能:
        从指定 URL 下载书籍 (支持 HTTP/HTTPS)。
        
        选项:
        - --dir: 指定下载目录 (默认: ./downloads)
        - --series: 指定系列名称 (用于归档)

        示例:
        download https://example.com/book.txt
        download https://example.com/book.epub --dir=~/Books
        """
        args = shlex.split(arg or "")
        if not args:
            print(Colors.red("请提供下载链接喵~"))
            return

        url = args[0]
        download_dir = "./downloads"
        series_name = None

        # 简单的参数解析
        for a in args[1:]:
            if a.startswith("--dir="):
                download_dir = a.split("=", 1)[1]
            elif a.startswith("--series="):
                series_name = a.split("=", 1)[1]

        if not os.path.exists(download_dir):
            try:
                os.makedirs(download_dir)
            except Exception as e:
                print(Colors.red(f"无法创建目录: {e}"))
                return

        print(Colors.cyan(f"开始下载: {url} ..."))
        
        try:
            # 尝试从 URL 提取文件名
            path = urllib.parse.urlparse(url).path
            filename = os.path.basename(path)
            if not filename:
                filename = "downloaded_book.txt"
                
            dest_path = os.path.join(download_dir, filename)
            
            # 简单的下载实现 (实际项目中可能需要更复杂的下载器)
            # 这里仅作为演示，不处理复杂的 headers 或 cookies
            urllib.request.urlretrieve(url, dest_path)
            
            print(Colors.green(f"下载成功喵！已保存到: {dest_path}"))
            
            # 如果指定了系列，可以在这里做额外处理，例如移动到系列文件夹
            if series_name:
                print(Colors.pink(f"标记为系列: {series_name} (需配合 import 命令导入)"))

        except Exception as e:
            print(Colors.red(f"下载失败了喵... {e}"))

    def complete_download(self, text, line, begidx, endidx):
        opts = ["--dir=", "--series="]
        return simple_complete(text, opts)

