import shlex
import os
import shutil
import zipfile
from datetime import datetime

from .utils import Colors


class ExportCommandsMixin:
    def do_export(self, arg):
        """导出书籍: export <选择器> [目标目录] [--zip]
        
        选择器支持:
        1. ID: export 1
        2. 多个ID: export 1,2,3
        3. 所有: export all
        4. 过滤器: export author:佚名
                  export series:魔法系列
                  export tag:变身
        
        选项:
        --zip: 打包成zip文件导出 (默认导出为文件夹)
        
        示例:
        export 5 ~/Desktop
        export all ~/Desktop/MyLibrary
        export author:佚名 ~/Desktop --zip
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
            books_to_export = self.db.list_books()
        elif "," in selector or selector.isdigit():
            ids = [int(x) for x in selector.split(",") if x.isdigit()]
            for bid in ids:
                book = self.db.get_book(bid)
                if book:
                    books_to_export.append(book)
                else:
                    print(Colors.yellow(f"找不到 ID 为 {bid} 的书，跳过喵..."))
        elif ":" in selector or "=" in selector:
            key, val = selector.split(":", 1) if ":" in selector else selector.split("=", 1)
            filters = {}
            if key in ["author", "series", "tag", "tags", "status"]:
                if key == "tag":
                    key = "tags"
                if key == "status":
                    try:
                        val = int(val)
                    except Exception:
                        pass
                filters[key] = val
                books_to_export = self.db.advanced_search(filters=filters)
            else:
                print(Colors.red(f"不支持的过滤器: {key}，请使用 author, series, tag, status 喵~"))
                return
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
