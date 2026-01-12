import shlex
from ..utils import Colors, simple_complete
from ..download_service import DownloadImportService


class DownloadCommandsMixin:
    def do_download(self, arg):
        """下载书籍: download <URL> [--dir=目录] [--series=系列] [--save-content] [--txt] [--image]

        功能:
        从指定 URL 下载书籍，或者从支持的网站 (Pixiv, Kemono) 批量爬取作品。
        下载完成后，会自动将其导入到书库中，并清理临时文件。
        
        支持站点:
        - Pixiv: 输入作者主页链接 (e.g. https://www.pixiv.net/users/12345)
          * 自动爬取该作者的所有小说和漫画/插画。
          * 漫画会自动合并为 CBZ 格式 (含元数据)。
          * 首次使用会提示输入 Cookie (建议在 config.py 中配置)。
          * 支持多线程下载、断点重试和进度条显示。
          * 自动按 [作者名/标题.txt] 结构导入书库。

        - Kemono: 输入作者主页链接 (e.g. https://kemono.su/patreon/user/12345)
          * 自动爬取该作者的所有帖子。
          * 文件自动命名为 "Author - Title (kemono:service:user:post)" 格式，方便精准识别。
          * 默认模式: 仅下载附件 (Attachments, 如 zip/rar/pdf)，忽略正文和内嵌图片。
          * --image 模式: 仅下载内嵌图片并打包为 PDF (默认) 或 CBZ。
          * --txt 模式: 仅下载正文内容保存为 TXT。
          * 使用 --save-content 可在默认模式下强制同时保存正文内容。

        - 通用下载: 直接下载文件链接。
        
        选项:
        - --dir: 指定临时下载目录 (可选，默认使用系统临时目录)
        - --series: 指定系列名称 (用于归档，仅对单文件下载有效)
        - --save-content: (仅限 Kemono) 在下载附件的同时，强制保存帖子正文内容为 TXT
        - --txt: (仅限 Kemono) 只下载正文内容
        - --image: (仅限 Kemono) 只下载内嵌图片并打包
        - --dup-mode: 重复处理模式 skip/overwrite/rename/ask/import
        - --skip-dup/--overwrite-dup/--rename-dup/--ask-dup: 重复处理快捷开关
        
        示例:
        1) download https://www.pixiv.net/users/123456
        2) download https://kemono.su/patreon/user/12345 --image
        3) download https://kemono.su/patreon/user/12345 --txt
        """
        args = shlex.split(arg or "")
        if not args:
            print(Colors.red("请提供下载链接喵~"))
            return

        url = args[0]
        user_specified_dir = None
        series_name = None
        save_content = False
        dl_mode = "attachment" # default, txt, image
        dup_mode = None

        # 简单的参数解析
        for a in args[1:]:
            if a.startswith("--dir="):
                user_specified_dir = a.split("=", 1)[1]
            elif a.startswith("--series="):
                series_name = a.split("=", 1)[1]
            elif a == "--save-content":
                save_content = True
            elif a == "--txt":
                dl_mode = "txt"
            elif a == "--image":
                dl_mode = "image"
            elif a == "--skip-dup":
                dup_mode = "skip"
            elif a == "--overwrite-dup":
                dup_mode = "overwrite"
            elif a == "--rename-dup":
                dup_mode = "rename"
            elif a == "--ask-dup":
                dup_mode = "ask"
            elif a.startswith("--dup-mode="):
                dup_mode = a.split("=", 1)[1].strip()
            elif a.startswith("--dup="):
                dup_mode = a.split("=", 1)[1].strip()

        if not dup_mode:
            low = str(url or "").lower()
            if "kemono." in low:
                dup_mode = "ask"
            else:
                dup_mode = "skip"

        # 更新配置
        # from .config import DOWNLOAD_CONFIG
        # if save_content:
        #     DOWNLOAD_CONFIG["kemono_save_content"] = True

        svc = DownloadImportService(self.db, self.fm)
        if user_specified_dir:
            print(Colors.cyan(f"使用指定目录: {user_specified_dir}"))

        try:
            out = svc.download_and_import(
                url=url,
                download_dir=user_specified_dir,
                series_name=series_name,
                save_content=save_content,
                kemono_dl_mode=dl_mode,
                dry_run=False,
                dup_mode=dup_mode,
            )
        except Exception as e:
            print(Colors.red(f"下载流程出错: {e}"))
            return

        if not out.get("success"):
            print(Colors.red(out.get("message") or "下载失败喵..."))
            return

        print(Colors.green(out.get("message") or "下载完成喵~"))
        print(Colors.pink(f"已归档: {out.get('imported', 0)}，跳过重复: {out.get('skipped', 0)}"))


    def complete_download(self, text, line, begidx, endidx):
        opts = [
            "--dir=",
            "--series=",
            "--save-content",
            "--txt",
            "--image",
            "--dup-mode=",
            "--dup=",
            "--skip-dup",
            "--overwrite-dup",
            "--rename-dup",
            "--ask-dup",
        ]
        return simple_complete(text, opts)
