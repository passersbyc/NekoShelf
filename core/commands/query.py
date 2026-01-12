import shlex
import shutil
import unicodedata

from ..utils import Colors, parse_id_ranges, parse_query_args, simple_complete


class QueryCommandsMixin:
    def _disp_width(self, s):
        s = "" if s is None else str(s)
        w = 0
        for ch in s:
            if unicodedata.combining(ch):
                continue
            if unicodedata.east_asian_width(ch) in {"F", "W"}:
                w += 2
            else:
                w += 1
        return w

    def _truncate_disp(self, s, max_width):
        s = "" if s is None else str(s)
        if max_width <= 0:
            return ""
        if self._disp_width(s) <= max_width:
            return s
        if max_width == 1:
            return "…"
        target = max_width - 1
        out = ""
        w = 0
        for ch in s:
            if unicodedata.combining(ch):
                continue
            cw = 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
            if w + cw > target:
                break
            out += ch
            w += cw
        return out + "…"

    def _pad_disp(self, s, width, align="left"):
        s = "" if s is None else str(s)
        pad = width - self._disp_width(s)
        if pad <= 0:
            return s
        if align == "right":
            return " " * pad + s
        return s + " " * pad

    def _safe_get(self, row, key, default=""):
        try:
            return row[key]
        except Exception:
            try:
                return getattr(row, key)
            except Exception:
                return default

    def _format_tags_hash(self, tags_raw):
        s = "" if tags_raw is None else str(tags_raw)
        s = s.replace("，", ",").replace("+", ",").strip()
        if not s:
            return ""
        parts = [p.strip() for p in s.split(",")]
        parts = [p.lstrip("#").strip() for p in parts if p and p.strip()]
        if not parts:
            return ""
        return " ".join(f"#{p}" for p in parts)

    def do_list(self, arg):
        """列出藏书: list [关键词] [field:value] ... [--limit N] [--sort 字段] [--asc/--desc]

        选择器支持:
        1) ID 范围: list 1-10
        2) 过滤器: list author:佚名 status:1
                 list series:魔法系列
        3) 关键词: list 魔法

        选项:
        - --limit N: 限制显示数量
        - --sort 字段: id/title/author/created/status/type/series
        - --asc/--desc: 排序方向
        - --path: 额外显示文件路径
        - --compact: 紧凑显示(隐藏标签列)

        支持的过滤器:
        - ids:1,3-5      - 搜索特定ID范围
        - author:作者名   - 搜索特定作者
        - series:系列名   - 搜索特定系列
        - tag:标签       - 搜索特定标签
        - status:1/0     - 1=完结, 0=连载
        - type:格式      - 如 txt, pdf

        示例:
        list
        list 1-10
        list 变身 --limit 20
        list author:佚名 status:1 --sort title
        list series:碧蓝航线ts --path
        """

        def val(row, key, default=""):
            try:
                return row[key]
            except Exception:
                try:
                    return getattr(row, key)
                except Exception:
                    return default

        raw = (arg or "").strip()
        args = shlex.split(raw) if raw else []
        limit = None
        sort_field = None
        order = None
        show_path = False
        compact = False

        rest_args = []
        i = 0
        while i < len(args):
            token = args[i]

            if token in {"--limit", "-n"}:
                if i + 1 >= len(args):
                    print(Colors.red("参数缺失喵: --limit 需要一个数字"))
                    return
                try:
                    limit = int(args[i + 1])
                except Exception:
                    print(Colors.red("参数格式不对喵: --limit 必须是数字"))
                    return
                i += 2
                continue

            if token == "--sort":
                if i + 1 >= len(args):
                    print(Colors.red("参数缺失喵: --sort 需要一个字段"))
                    return
                sort_field = str(args[i + 1]).strip().lower()
                i += 2
                continue

            if token == "--asc":
                order = "asc"
                i += 1
                continue
            if token == "--desc":
                order = "desc"
                i += 1
                continue

            if token == "--path":
                show_path = True
                i += 1
                continue

            if token in {"--compact", "--no-tags"}:
                compact = True
                i += 1
                continue

            if token.startswith("--"):
                print(Colors.yellow(f"未知参数已忽略喵: {token}"))
                i += 1
                continue

            rest_args.append(token)
            i += 1

        query, filters = parse_query_args(rest_args, strict_id_mode=False)

        if query or filters:
            books = self.db.advanced_search(query, filters)
            if not books:
                print(Colors.yellow("找不到符合条件的书喵..."))
                return
        else:
            books = self.db.list_books()
            if not books:
                print(Colors.yellow("藏书阁是空的喵..."))
                return

        def norm_s(x):
            return str(x or "").strip().lower()

        if sort_field:
            key_map = {
                "id": lambda b: int(val(b, "id", 0) or 0),
                "title": lambda b: norm_s(val(b, "title", "")),
                "author": lambda b: norm_s(val(b, "author", "")),
                "series": lambda b: norm_s(val(b, "series", "")),
                "status": lambda b: int(val(b, "status", 0) or 0),
                "type": lambda b: norm_s(val(b, "file_type", "")),
                "created": lambda b: str(val(b, "created_at", "")),
            }
            if sort_field not in key_map:
                print(Colors.yellow(f"不支持的排序字段喵: {sort_field}，已按 created 排序"))
                sort_field = "created"

            if order is None:
                order = "asc" if sort_field in {"title", "author", "series", "type"} else "desc"

            books = sorted(books, key=key_map[sort_field], reverse=(order == "desc"))
        else:
            books = sorted(books, key=lambda b: str(val(b, "created_at", "")), reverse=True)

        if limit is not None:
            if limit <= 0:
                print(Colors.yellow("--limit 必须大于 0 喵"))
                return
            books = books[:limit]

        show_tags = not compact
        term_width = shutil.get_terminal_size((120, 20)).columns

        def get_col_max(key, header, min_w, max_cap):
            w = self._disp_width(header)
            for b in books:
                if key == "status":
                    v = "完结" if val(b, "status", 0) == 1 else "连载"
                else:
                    v = str(val(b, key, "") or "")
                w = max(w, self._disp_width(v))
            return max(min_w, min(w, max_cap))

        id_w = get_col_max("id", "ID", 2, 6)

        status_w = max(self._disp_width("状态"), self._disp_width("连载"))
        fmt_w = get_col_max("file_type", "格式", 4, 8)

        avail = term_width

        title_cap = max(30, int(avail * 0.40))
        author_cap = max(15, int(avail * 0.20))
        series_cap = max(15, int(avail * 0.20))

        title_w = get_col_max("title", "标题", 10, title_cap)
        author_w = get_col_max("author", "作者", 8, author_cap)
        series_w = get_col_max("series", "系列", 8, series_cap)

        sep = " │ "
        sep_w = self._disp_width(sep)

        base_cols = [id_w, title_w, author_w, status_w, fmt_w, series_w]
        total_sep_w = sep_w * (len(base_cols) + (1 if show_tags else 0) - 1)

        tags_min = 10
        tags_w = 0

        total_need = sum(base_cols) + total_sep_w + (tags_min if show_tags else 0)

        def shrink(col_w, min_limit, need_to_cut):
            if need_to_cut <= 0:
                return col_w, need_to_cut
            can_cut = max(0, col_w - min_limit)
            cut = min(need_to_cut, can_cut)
            return col_w - cut, need_to_cut - cut

        overflow = total_need - term_width

        if overflow > 0:
            series_w, overflow = shrink(series_w, 8, overflow)
            author_w, overflow = shrink(author_w, 8, overflow)
            title_w, overflow = shrink(title_w, 10, overflow)

        current_used = id_w + title_w + author_w + status_w + fmt_w + series_w + total_sep_w
        if show_tags:
            tags_w = max(tags_min, term_width - current_used)

        h_id = self._pad_disp("ID", id_w, align="right")
        h_title = self._pad_disp("标题", title_w)
        h_author = self._pad_disp("作者", author_w)
        h_status = self._pad_disp("状态", status_w)
        h_fmt = self._pad_disp("格式", fmt_w)
        h_series = self._pad_disp("系列", series_w)

        header_parts = [h_id, h_title, h_author, h_status, h_fmt, h_series]
        if show_tags:
            header_parts.append("标签")

        header_str = sep.join(header_parts)
        print(Colors.cyan(Colors.BOLD + header_str + Colors.RESET))

        line_len = min(self._disp_width(header_str), term_width)
        print(Colors.cyan("─" * line_len))

        for book in books:
            bid = self._pad_disp(str(val(book, "id", "")), id_w, align="right")

            t_val = str(val(book, "title", "") or "")
            a_val = str(val(book, "author", "") or "")
            s_val = str(val(book, "series", "") or "")
            tags_val = str(val(book, "tags", "") or "")
            f_val = str(val(book, "file_type", "") or "")
            st_val = "完结" if val(book, "status", 0) == 1 else "连载"

            title = self._pad_disp(self._truncate_disp(t_val, title_w), title_w)
            author = self._pad_disp(self._truncate_disp(a_val, author_w), author_w)
            series = self._pad_disp(self._truncate_disp(s_val, series_w), series_w)
            ftype = self._pad_disp(self._truncate_disp(f_val, fmt_w), fmt_w)
            status = self._pad_disp(st_val, status_w)

            tags_view = self._format_tags_hash(tags_val)
            tags = self._truncate_disp(tags_view, tags_w) if show_tags else ""

            c_id = Colors.yellow(bid)
            c_title = Colors.BOLD + title + Colors.RESET
            c_author = Colors.green(author)
            c_status = Colors.green(status) if st_val == "完结" else Colors.pink(status)
            c_series = Colors.cyan(series)
            c_fmt = ftype

            row_parts = [c_id, c_title, c_author, c_status, c_fmt, c_series]
            if show_tags:
                row_parts.append(tags)

            print(sep.join(row_parts))

            if show_path:
                p_raw = str(val(book, "file_path", "") or "")
                p = self._truncate_disp(p_raw, max(10, term_width - 4))
                print(Colors.cyan(f"  ↳ {p}"))

    def do_authors(self, arg):
        """列出或编辑作者: authors [关键词] [options]

        功能:
        1. 显示所有作者及其详细信息（收录状态、最新作品、联系方式）。
        2. 支持按名字搜索。

        提示:
        推荐使用 update 命令修改作者信息: update author <ID> full=1 ...

        旧版选项 (仍可用):
        - --set-full <ID> <0/1>: 设置收录状态 (1=全集, 0=散录)
        - --set-date <ID> <日期>: 设置最新作品日期 (如 2024-01-01)
        - --set-contact <ID> <内容>: 设置联系方式

        示例:
        authors
        authors 鲁迅
        authors --set-full 1 1         (设置 ID=1 的作者为全集)
        """
        args = shlex.split(arg or "")

        if args and args[0].startswith("--set-"):
            if len(args) < 3:
                print(Colors.red("参数不足喵! 用法: authors --set-xxx <ID> <Value>"))
                return

            action = args[0]
            try:
                aid = int(args[1])
            except:
                print(Colors.red("ID 必须是数字喵!"))
                return

            val_str = args[2]

            author = self.db.get_author(aid)
            if not author:
                print(Colors.red(f"找不到 ID={aid} 的作者喵..."))
                return

            success = False
            if action == "--set-full":
                try:
                    v = int(val_str)
                    if v not in (0, 1):
                        raise ValueError
                    success = self.db.update_author(aid, is_full=v)
                    print(Colors.green(f"已设置 {author['name']} 的收录状态为: {'全集' if v else '散录'}"))
                except:
                    print(Colors.red("状态只能是 0 或 1 喵!"))
                    return

            elif action == "--set-date":
                success = self.db.update_author(aid, last_work_date=val_str)
                print(Colors.green(f"已更新 {author['name']} 的新作日期: {val_str}"))

            elif action == "--set-contact":
                success = self.db.update_author(aid, contact=val_str)
                print(Colors.green(f"已更新 {author['name']} 的联系方式"))

            else:
                print(Colors.red(f"未知操作: {action}"))
                return

            if not success:
                print(Colors.red("更新失败喵..."))
            return

        all_authors = self.db.list_authors()
        if not all_authors:
            print(Colors.yellow("还没有记录任何作者喵..."))
            return

        val = self._safe_get

        keyword = ""
        if args:
            keyword = args[0].strip().lower()
            authors = [a for a in all_authors if keyword in str(a['name']).lower()]
            if not authors:
                print(Colors.yellow(f"找不到名字包含 '{keyword}' 的作者喵..."))
                return
        else:
            authors = all_authors

        term_width = shutil.get_terminal_size((80, 20)).columns

        id_w = max([len(str(a['id'])) for a in authors] + [2])
        count_w = max([len(str(a['book_count'])) for a in authors] + [4])
        full_w = 4
        update_w = 10

        max_name_w = 0
        for a in authors:
            max_name_w = max(max_name_w, self._disp_width(a['name']))

        sep = " │ "
        sep_w = 3

        fixed_w = id_w + full_w + count_w + update_w + (sep_w * 5)

        avail = term_width - fixed_w
        if avail < 20:
            name_w = 10
            contact_w = max(5, avail - 10)
        else:
            name_w = min(max_name_w, int(avail * 0.4))
            name_w = max(name_w, 8)
            contact_w = avail - name_w

        h_id = self._pad_disp("ID", id_w, align="right")
        h_name = self._pad_disp("作者名", name_w)
        h_full = self._pad_disp("收录", full_w)
        h_count = self._pad_disp("藏书", count_w, align="right")
        h_update = self._pad_disp("更新", update_w)
        h_contact = self._pad_disp("联系方式", contact_w)

        header_str = f"{h_id}{sep}{h_name}{sep}{h_full}{sep}{h_count}{sep}{h_update}{sep}{h_contact}"
        print(Colors.cyan(Colors.BOLD + header_str + Colors.RESET))
        print(Colors.cyan("─" * min(self._disp_width(header_str), term_width)))

        for a in authors:
            aid = self._pad_disp(str(a['id']), id_w, align="right")

            raw_name = str(a['name'])
            disp_name = self._truncate_disp(raw_name, name_w)
            aname = self._pad_disp(disp_name, name_w)

            is_full = val(a, "is_full", 0)
            full_str = "全集" if is_full == 1 else "散录"
            full_disp = self._pad_disp(full_str, full_w)

            acount = self._pad_disp(str(a['book_count']), count_w, align="right")

            import_val = str(val(a, "last_import_date", "") or "-")
            if len(import_val) > 10:
                import_val = import_val[:10]
            update_disp = self._pad_disp(self._truncate_disp(import_val, update_w), update_w)

            contact_val = str(val(a, "contact", "") or "")
            contact_disp = self._pad_disp(self._truncate_disp(contact_val, contact_w), contact_w)

            c_full = Colors.green(full_disp) if is_full == 1 else Colors.pink(full_disp)

            print(f"{Colors.yellow(aid)}{sep}{Colors.green(aname)}{sep}{c_full}{sep}{Colors.cyan(acount)}{sep}{update_disp}{sep}{contact_disp}")

    def complete_authors(self, text, line, begidx, endidx):
        if text.startswith("--"):
            opts = ["--set-full", "--set-date", "--set-contact"]
            return simple_complete(text, opts)
        try:
            authors = self.db.list_authors()
            names = [str(a['name']) for a in authors]
            return simple_complete(text, names)
        except:
            return []

    def do_search(self, arg):
        """搜索书籍: search [关键词] [field:value] ...

        选择器支持:
        1) ID 范围: search 1-10
        2) 过滤器: search author:佚名 status:1
                 search series:魔法系列 tag:变身
        3) 关键词: search 魔法 (模糊搜索)

        选项:
        - --ids: 仅输出匹配的 ID 列表 (方便复制)

        支持的过滤器:
        - ids:1,3-5      - 搜索特定ID范围
        - author:作者名   - 搜索特定作者
        - series:系列名   - 搜索特定系列
        - tag:标签       - 搜索特定标签
        - status:1/0     - 1=完结, 0=连载
        - type:格式      - 如 txt, pdf

        示例:
        search 10-20
        search ids:1,3,5 tag:魔法
        search 魔法 author:佚名
        search status:1 tag:变身
        search 魔法 --ids
        """
        if not arg:
            print(Colors.red("请输入搜索内容喵！"))
            return

        args = shlex.split(arg)

        show_ids_only = False
        if "--ids" in args:
            show_ids_only = True
            args.remove("--ids")
            if not args:
                print(Colors.red("请输入搜索内容喵！"))
                return

        query, filters = parse_query_args(args, strict_id_mode=False)

        books = self.db.advanced_search(query, filters)

        if not books:
            print(Colors.yellow("找不到符合条件的书喵..."))
            return

        def title_key(b):
            try:
                return str(b["title"] or "")
            except Exception:
                return ""

        books = sorted(list(books), key=title_key, reverse=False)

        if show_ids_only:
            ids = sorted([str(b["id"]) for b in books], key=lambda x: int(x))
            joined = ",".join(ids)
            print(Colors.cyan(f"匹配到 {len(books)} 本，ID 列表喵:"))
            print(Colors.yellow(joined))
            return

        print(Colors.green(f"找到 {len(books)} 本书喵:"))
        for book in books:
            status_str = "完结" if book['status'] == 1 else "连载"
            s_color = Colors.green(status_str) if book['status'] == 1 else Colors.pink(status_str)
            series_str = f" [系列: {Colors.cyan(book['series'])}]" if book['series'] else ""
            tags_view = self._format_tags_hash(book['tags'])
            tags_str = f" {Colors.cyan(tags_view)}" if tags_view else ""
            print(
                f"[{Colors.yellow(str(book['id']))}] {Colors.BOLD}{book['title']}{Colors.RESET} - "
                f"{Colors.green(book['author'])} ({s_color}){series_str}{tags_str}"
            )

    def do_open(self, arg):
        """打开书籍或文件: open <ID>

        功能:
        使用系统默认程序打开指定 ID 的书籍文件。
        """
        import os
        import sys
        if not arg:
            print(Colors.red("请指定书籍 ID 喵~"))
            return

        try:
            bid = int(arg.strip())
            book = self.db.get_book(bid)
            if not book:
                print(Colors.red(f"找不到 ID 为 {bid} 的书喵..."))
                return

            fp = book['file_path']
            if not fp or not os.path.exists(fp):
                print(Colors.red(f"文件不存在喵: {fp}"))
                return

            print(Colors.green(f"正在打开: {fp}"))
            if os.name == 'nt':
                os.startfile(fp)
            else:
                import subprocess

                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.call([opener, fp])

        except ValueError:
            print(Colors.red("ID 必须是数字喵！"))
        except Exception as e:
            print(Colors.red(f"打开失败喵: {e}"))

    def complete_search(self, text, line, begidx, endidx):
        opts = [
            "--ids",
            "--title",
            "--author",
            "--tag",
            "--series",
            "--status",
            "author:",
            "series:",
            "tag:",
            "status:",
            "title:",
        ]
        return simple_complete(text, opts)

    def complete_list(self, text, line, begidx, endidx):
        opts = [
            "--limit",
            "--sort",
            "--all",
            "--desc",
            "--asc",
            "author:",
            "series:",
            "tag:",
            "status:",
            "title:",
            "limit:",
            "sort:",
        ]
        return simple_complete(text, opts)

    def complete_open(self, text, line, begidx, endidx):
        try:
            books = self.db.list_books() or []
            ids = [str(b['id']) for b in books]
            return simple_complete(text, ids)
        except:
            return []

    def complete_stats(self, text, line, begidx, endidx):
        return []

    def do_stats(self, arg):
        """查看统计信息: stats"""
        stats = self.db.get_stats()
        print(Colors.pink("\n📊 藏书阁统计报告 📊"))
        print(f"总藏书量: {Colors.yellow(str(stats['total']))} 本")

        print(Colors.cyan("\n📁 格式分布:"))
        for ftype, count in stats['types'].items():
            print(f"  - {ftype}: {Colors.green(str(count))}")

        print(Colors.cyan("\n✍️ 热门作者:"))
        for author, count in stats['authors']:
            print(f"  - {author}: {Colors.green(str(count))} 本")

        if stats['series']:
            print(Colors.cyan("\n📚 热门系列:"))
            for series, count in stats['series']:
                print(f"  - {series}: {Colors.green(str(count))} 本")
        print("")


__all__ = ["QueryCommandsMixin"]
