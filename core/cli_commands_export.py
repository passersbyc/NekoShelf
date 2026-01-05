import shlex
import os
import shutil
import zipfile
from datetime import datetime

from .utils import Colors, parse_id_ranges, parse_query_args


class ExportCommandsMixin:
    def do_export(self, arg):
        """导出书籍: export <选择器> [目标目录] [--zip]

        选择器支持:
        1) ID 范围: export 1-5
        2) 过滤器 : export author:佚名
        3) 关键词 : export all (导出所有)

        选项:
        - --zip: 打包成 zip 文件导出

        示例:
        1) export 1-10 ~/Desktop
        2) export ids:1,3,5 ~/Desktop
        3) export all ~/Desktop/MyLibrary
        4) export author:佚名 ~/Desktop --zip
        """
        args = shlex.split(arg)
        if not args:
            print(f"{Colors.RED}请告诉{Colors.HEADER}萌萌{Colors.RED}要导出哪些书喵！{Colors.RESET}")
            return

        selector = args[0]
        target_dir = "."
        use_zip = False

        rest_args = args[1:]
        if "--zip" in rest_args:
            use_zip = True
            rest_args.remove("--zip")

        if rest_args:
            target_dir = rest_args[0]

        books_to_export = []

        if selector.lower() == "all":
            books_to_export = list(self.db.list_books())
        else:
            q, f = parse_query_args([selector], strict_id_mode=True)
            if q or f:
                books_to_export = list(self.db.advanced_search(q, f))
            else:
                print(Colors.red("无法识别的选择器喵！请使用 ID, all, 或 author:名字"))
                return

        if not books_to_export:
            print(Colors.yellow("没有找到要导出的书喵..."))
            return

        print(Colors.cyan(f"准备导出 {len(books_to_export)} 本书到 {target_dir} ..."))

        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir)
            except Exception:
                print(Colors.red(f"无法创建目录: {target_dir}"))
                return

        success_count = 0

        if use_zip:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"books_export_{timestamp}.zip"
            zip_path = os.path.join(target_dir, zip_filename)

            try:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for book in books_to_export:
                        if os.path.exists(book["file_path"]):
                            arcname = f"{book['id']}_{os.path.basename(book['file_path'])}"
                            zf.write(book["file_path"], arcname)
                            success_count += 1
                        else:
                            print(Colors.pink(f"跳过丢失的文件: {book['title']}"))
                print(Colors.green(f"打包完成喵！已保存为: {zip_path}"))
            except Exception as e:
                print(Colors.red(f"打包失败了喵... {e}"))
        else:
            for book in books_to_export:
                if not os.path.exists(book["file_path"]):
                    print(Colors.pink(f"跳过丢失的文件: {book['title']}"))
                    continue

                filename = os.path.basename(book["file_path"])
                dest_path = os.path.join(target_dir, filename)

                if os.path.exists(dest_path):
                    base, ext = os.path.splitext(filename)
                    dest_path = os.path.join(target_dir, f"{base}_{book['id']}{ext}")

                try:
                    shutil.copy2(book["file_path"], dest_path)
                    success_count += 1
                except Exception as e:
                    print(Colors.red(f"复制失败 {filename}: {e}"))

        print(Colors.green(f"任务结束喵！成功导出 {success_count}/{len(books_to_export)} 本。"))
