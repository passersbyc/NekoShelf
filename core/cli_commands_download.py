import shlex
import os
import tempfile
import shutil
from .utils import Colors, simple_complete
from .download_manager import DownloadManager


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
          * 文件自动命名为 "Author - Title (ID)" 格式，方便书库精准识别。
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

        # 更新配置
        # from .config import DOWNLOAD_CONFIG
        # if save_content:
        #     DOWNLOAD_CONFIG["kemono_save_content"] = True

        manager = DownloadManager()

        # 定义下载和导入的内部逻辑
        def process_download(target_dir, is_temp=False):
            # 将 save_content 传递给 download 方法
            success, msg, output_path = manager.download(url, target_dir, series_name=series_name, save_content=save_content, kemono_dl_mode=dl_mode)
            
            if not success:
                print(Colors.red(msg))
                return

            print(Colors.green(msg))
            if output_path:
                print(Colors.pink("\n正在自动导入到书库喵..."))
                if hasattr(self, "do_import"):
                    quoted_path = shlex.quote(output_path)
                    author_name = os.path.basename(output_path.rstrip(os.sep))
                    quoted_author = shlex.quote(author_name)
                    
                    # 构造导入命令
                    # --delete-source: 导入后删除源文件 (如果是临时目录，这一步可以加速清理)
                    # 添加 --dup-mode=skip 以避免在批量下载时对已存在文件进行询问
                    cmd = f"{quoted_path} --recursive --no-parent-as-series --author={quoted_author} --dup-mode=skip"
                    
                    # 检查是否在 Library 目录内
                    from .config import LIBRARY_DIR
                    is_in_library = False
                    try:
                        lib_abs = os.path.abspath(LIBRARY_DIR)
                        out_abs = os.path.abspath(output_path)
                        if os.path.commonpath([out_abs, lib_abs]) == lib_abs:
                            is_in_library = True
                    except:
                        pass

                    if is_temp and not is_in_library:
                         cmd += " --delete-source"
                    elif is_in_library:
                         cmd += " --keep-source"
                    
                    self.do_import(cmd)
                else:
                    print(Colors.yellow("无法自动导入: 未找到导入功能喵..."))

        if user_specified_dir:
            # 用户指定目录，不视为临时目录（不强制删除，除非用户自己加参数，但这里我们只做基本导入）
            # 既然用户指定了目录，可能希望保留文件？或者只是指定缓存位置。
            # 既然用户说“不需要downloads文件夹”，默认行为应该是临时。
            # 如果指定了 --dir，我们就不自动清理目录本身，但可以尝试导入。
            print(Colors.cyan(f"使用指定目录: {user_specified_dir}"))
            process_download(user_specified_dir, is_temp=False)
        else:
            # 使用临时目录 - 但对于 Pixiv 插件，它会自动使用 LIBRARY_DIR
            # 所以我们传递一个假的临时目录，或者修改 process_download 逻辑
            # 由于 DownloadManager.download 会将 target_dir 传递给插件
            # PixivPlugin 忽略了 output_dir (target_dir) 并使用 config.LIBRARY_DIR
            # 所以这里传什么其实不重要，但是为了保持兼容性，我们还是创建一个
            
            # 修正: 不需要创建实际的临时目录，因为 PixivPlugin 直接写库
            # 但是 CommonPlugin 仍然需要临时目录
            # 所以我们还是保留临时目录创建，反正 PixivPlugin 不用它
            
            try:
                # 使用项目目录下的 temp_downloads 作为临时空间，方便查看和管理
                project_temp = os.path.join(os.getcwd(), "temp_downloads")
                os.makedirs(project_temp, exist_ok=True)
                
                # 使用 tempfile 在指定目录下创建临时目录
                with tempfile.TemporaryDirectory(prefix="neko_dl_", dir=project_temp) as temp_dir:
                    print(Colors.pink(f"创建临时空间: {temp_dir}"))
                    process_download(temp_dir, is_temp=True)
                # 退出 with 块后，temp_dir 会被自动清理
                print(Colors.pink("临时文件已清理喵~"))
                
                # 尝试删除 temp_downloads (如果为空)
                try:
                    os.rmdir(project_temp)
                except OSError:
                    pass
            except Exception as e:
                print(Colors.red(f"下载流程出错: {e}"))


    def complete_download(self, text, line, begidx, endidx):
        opts = ["--dir=", "--series=", "--save-content"]
        return simple_complete(text, opts)

