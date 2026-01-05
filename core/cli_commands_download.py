import shlex
import os
import urllib.request
import urllib.parse

from .utils import Colors


class DownloadCommandsMixin:
    def do_download(self, arg):
        """从网络下载书籍: download <URL> [文件名] [选项]

        说明:
        - 下载完成后会自动调用 import 进行导入
        - 支持所有 import 命令的选项 (如 --dry-run)

        示例:
        1) 自动重命名并导入:
           download http://site.com/1.txt 魔法书_作者_标签.txt

        2) 下载后手动指定信息:
           download http://site.com/1.txt 魔法书 "作者" "标签"

        3) 简单下载 (尝试从URL获取文件名):
           download http://site.com/file.pdf
        """
        args = shlex.split(arg)
        if not args:
            print(Colors.red("请提供下载链接喵！"))
            return

        url = args[0]
        others = args[1:]

        print(Colors.cyan("正在连接到网络世界的彼端..."))
        print(Colors.pink(f"目标: {url}"))

        filename = "unknown_book.txt"
        custom_filename = False

        if others and "." in others[0]:
            filename = others[0]
            custom_filename = True
        else:
            path = urllib.parse.urlparse(url).path
            if path:
                filename = os.path.basename(path)

            if not filename or "." not in filename:
                filename = "downloaded_file.txt"

            filename = urllib.parse.unquote(filename)

        try:

            def report(block_num, block_size, total_size):
                if total_size > 0:
                    percent = min(100, int(block_num * block_size * 100 / total_size))
                    bar_len = 20
                    filled = int(bar_len * percent / 100)
                    bar = "▓" * filled + "░" * (bar_len - filled)
                    print(f"\r{Colors.yellow('下载中:')} {bar} {percent}%喵~", end="")

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MoeManager/1.0)"})
            local_path = filename

            with urllib.request.urlopen(req) as response, open(local_path, "wb") as out_file:
                total_size = int(response.getheader("Content-Length") or 0)
                downloaded = 0
                block_size = 8192
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    downloaded += len(buffer)
                    out_file.write(buffer)
                    if total_size > 0:
                        report(downloaded // block_size, block_size, total_size)
                    else:
                        spin = ["|", "/", "-", "\\"][downloaded // block_size % 4]
                        print(f"\r{Colors.yellow('下载中:')} {spin} {downloaded // 1024}KB 喵~", end="")

            print(f"\n{Colors.green('下载完成喵！')} 已保存为: {local_path}")
            print(Colors.cyan("开始自动归档流程..."))

            import_args = [f'"{local_path}"']

            if custom_filename:
                if len(others) > 1:
                    import_args.extend([f'"{a}"' for a in others[1:]])
            else:
                import_args.extend([f'"{a}"' for a in others])

            import_cmd_str = " ".join(import_args)
            self.do_import(import_cmd_str)

        except Exception as e:
            print(Colors.red(f"\n下载失败了喵... {e}"))
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception:
                    pass

