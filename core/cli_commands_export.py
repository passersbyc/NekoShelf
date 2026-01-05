import shlex
import os
import shutil
import zipfile
from datetime import datetime

from .utils import Colors, parse_id_ranges, parse_query_args, simple_complete


class ExportCommandsMixin:
    def do_export(self, arg):
        """导出书籍或信息: export <ID/选择器> [--format=fmt] [--output=dir]

        功能:
        将书籍信息或文件导出。

        选项:
        - --format: 导出格式
          * zip: 打包源文件 (默认)
          * json: 导出元数据为 JSON
          * csv: 导出元数据为 CSV
          * copy: 复制源文件到指定目录
        - --output: 输出目录 (默认为 ./exports)

        示例:
        export 1,2,3 --format=zip
        export author:佚名 --format=json
        """
        args = shlex.split(arg or "")
        
        # 提取选项
        format_type = "zip"
        output_dir = "./exports"
        
        # 提取 --format 和 --output
        clean_args = []
        for a in args:
            if a.startswith("--format="):
                format_type = a.split("=", 1)[1].lower()
            elif a.startswith("--output="):
                output_dir = a.split("=", 1)[1]
            else:
                clean_args.append(a)
                
        if not clean_args:
            print(Colors.red("请指定要导出的书籍喵~"))
            return

        query_str, filters = parse_query_args(clean_args, strict_id_mode=True)
        books = self.db.search_books(filters=filters, query=query_str)
        
        if not books:
            print(Colors.yellow("找不到要导出的书籍喵..."))
            return
            
        count = len(books)
        print(Colors.cyan(f"准备导出 {count} 本书 (格式: {format_type})..."))
        
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                print(Colors.red(f"无法创建输出目录: {e}"))
                return
                
        # 实现导出逻辑 (简化版)
        success = 0
        try:
            if format_type == "json":
                import json
                out_file = os.path.join(output_dir, f"export_{int(datetime.now().timestamp())}.json")
                data = [dict(b) for b in books] # Convert Row to dict
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(Colors.green(f"已导出 JSON 到: {out_file}"))
                success = count
                
            elif format_type == "csv":
                import csv
                out_file = os.path.join(output_dir, f"export_{int(datetime.now().timestamp())}.csv")
                if books:
                    keys = books[0].keys()
                    with open(out_file, "w", encoding="utf-8", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=keys)
                        writer.writeheader()
                        for b in books:
                            writer.writerow(dict(b))
                print(Colors.green(f"已导出 CSV 到: {out_file}"))
                success = count
                
            elif format_type in ["zip", "copy"]:
                for b in books:
                    fp = b['file_path']
                    if not fp or not os.path.exists(fp):
                        print(Colors.yellow(f"文件丢失，跳过: {b['title']}"))
                        continue
                        
                    fname = os.path.basename(fp)
                    
                    if format_type == "copy":
                        dst = os.path.join(output_dir, fname)
                        try:
                            shutil.copy2(fp, dst)
                            success += 1
                        except Exception as e:
                            print(Colors.red(f"复制失败 {fname}: {e}"))
                            
                    elif format_type == "zip":
                        # 这里简单处理，实际上可能需要创建一个大的 zip 或每个书一个 zip
                        # 为简化，创建一个 zip 包含所有
                        pass 

                if format_type == "zip":
                    zip_name = os.path.join(output_dir, f"books_export_{int(datetime.now().timestamp())}.zip")
                    with zipfile.ZipFile(zip_name, 'w') as zf:
                        for b in books:
                            fp = b['file_path']
                            if fp and os.path.exists(fp):
                                zf.write(fp, os.path.basename(fp))
                                success += 1
                    print(Colors.green(f"已打包到: {zip_name}"))
            
            else:
                print(Colors.red(f"不支持的格式: {format_type}"))
                return

        except Exception as e:
            print(Colors.red(f"导出过程出错: {e}"))
            
        print(Colors.green(f"导出完成喵！成功处理 {success} 本。"))

    def complete_export(self, text, line, begidx, endidx):
        # 如果正在输入 --format=xxx
        if text.startswith("--format="):
            formats = ["zip", "json", "csv", "copy"]
            prefix = "--format="
            return [prefix + f for f in formats if (prefix + f).startswith(text)]
            
        opts = ["--format=", "--output="]
        try:
            books = self.db.list_books() or []
            ids = [str(b['id']) for b in books]
            return simple_complete(text, opts + ids)
        except:
            return simple_complete(text, opts)
