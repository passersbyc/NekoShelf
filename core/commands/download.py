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
          * 建议配置 Cookie（优先使用环境变量 NEKOSHELF_PIXIV_COOKIE）。
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
            print(Colors.red(f"下载失败喵: {e}"))
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

    def do_follow(self, arg):
        """关注作者: follow <URL> [别名]
        
        功能:
        将作者主页加入追更列表。后续使用 pull 命令可自动检查更新。
        
        示例:
        follow https://www.pixiv.net/users/12345
        follow https://kemono.su/patreon/user/12345 MyFavArtist
        """
        args = shlex.split(arg or "")
        if not args:
            print(Colors.red("请提供作者主页链接喵~"))
            return
            
        url = args[0]
        alias = args[1] if len(args) > 1 else None
        
        # 简单验证
        svc = DownloadImportService(self.db, self.fm)
        plugin = svc.manager.get_plugin(url)
        if not plugin:
             print(Colors.yellow("警告: 该链接可能不受支持，但已尝试添加喵。"))
        
        # 检查是否已关注
        if self.db.is_subscribed(url):
            print(Colors.yellow("该链接已在关注列表中喵~"))
            return

        # 尝试自动获取作者名
        if not alias and plugin:
            print(Colors.pink("正在尝试获取作者名喵..."))
            try:
                name = plugin.get_artist_name(url)
                if name and "Unknown" not in name and "User_" not in name:
                    alias = name
            except Exception as e:
                pass

        if self.db.add_subscription(url, alias):
            print(Colors.green(f"已关注: {url}" + (f" ({alias})" if alias else "")))
        else:
            if alias:
                self.db.update_subscription_alias(url, alias)
                print(Colors.green(f"已更新关注作者名: {alias}"))
            else:
                print(Colors.yellow("该作者已在关注列表中喵~"))

    def do_unfollow(self, arg):
        """取消关注: unfollow <URL>
        
        功能:
        将作者从追更列表中移除。
        """
        if not arg:
            print(Colors.red("请提供要取消关注的URL喵~"))
            return
            
        url = arg.strip()
        if self.db.remove_subscription(url):
            print(Colors.green(f"已取消关注: {url}"))
        else:
            print(Colors.yellow("未找到该订阅记录喵。"))

    def do_subs(self, arg):
        """查看关注列表: subs
        
        功能:
        列出所有正在追更的作者。
        """
        subs = self.db.get_subscriptions()
        if not subs:
            print(Colors.yellow("当前没有关注任何作者喵~ 使用 follow <URL> 添加。"))
            return
            
        print(Colors.cyan(f"正在追更 {len(subs)} 位作者:\n"))
        
        header = f"{'ID':<4} {'上次检查':<18} {'作者/别名':<20} {'URL'}"
        print(f"{Colors.BOLD}{header}{Colors.RESET}")
        print("-" * 80)
        
        for sub in subs:
            # Format Last Check
            last = sub['last_check']
            if not last:
                last_str = "从未"
            else:
                last_str = str(last).replace('T', ' ')[:16]
            
            # Format Alias
            alias = sub['alias'] or ""
            if len(alias) > 18:
                alias = alias[:15] + "..."
            elif not alias:
                alias = "-"
                
            print(f"{sub['id']:<4} {last_str:<18} {alias:<20} {sub['url']}")

    def do_pull(self, arg):
        """检查更新: pull
        
        功能:
        自动检查所有关注作者的新作品并下载。
        
        特性:
        - 并行处理: 多线程同时检查多位作者，大幅提升速度。
        - 智能去重: 自动比对本地数据库记录，跳过已下载的作品。
        - 静默模式: 自动隐藏重复跳过的日志，仅显示重要更新信息。
        
        注意:
        默认使用 'skip' 模式跳过已存在的文件。
        """
        subs = self.db.get_subscriptions()
        if not subs:
            print(Colors.yellow("没有关注的作者喵~"))
            return
            
        print(Colors.cyan(f"开始检查 {len(subs)} 位作者的更新喵 (顺序检查，并行下载)...\n"))
        
        from core.database import DatabaseManager
        
        count = 0
        total_downloaded = 0
        
        for sub in subs:
            url = sub['url']
            name = sub['alias'] or url
            
            # print(Colors.dim(f"正在检查: {name}..."))
            
            try:
                # 默认使用 skip 模式，避免重复询问
                svc = DownloadImportService(self.db, self.fm)
                out = svc.download_and_import(
                    url,
                    kemono_dl_mode="attachment",
                    dup_mode="skip",
                    quiet=True
                )
                
                # 更新检查时间
                self.db.update_subscription_last_check(url)
                
                if out:
                    # 优先使用 'imported' 作为下载数量
                    dl = out.get('imported', 0)
                    if dl > 0:
                        print(Colors.green(f"✅ {name}: 更新了 {dl} 个文件喵！"))
                        count += 1
                        total_downloaded += dl
                    elif out.get('skipped', 0) > 0:
                         print(Colors.dim(f"💤 {name}: 暂无新内容 (跳过 {out.get('skipped')} 个)"))
                    else:
                        print(Colors.dim(f"💤 {name}: 暂无新内容"))
                else:
                    print(Colors.dim(f"💤 {name}: 暂无新内容"))
            
            except Exception as e:
                print(Colors.red(f"❌ {name}: 更新失败 ({e})"))

        print(Colors.green(f"\n检查完毕！有更新的作者: {count} 位，共下载 {total_downloaded} 个文件喵。"))
