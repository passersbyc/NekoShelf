import shlex
import shutil
import unicodedata

from .utils import Colors


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
        """列出藏书: list [关键词] [field:value] ... [--limit N] [--sort 字段] [--asc/--desc] [--path] [--compact]

        选项:
        - --limit N: 限制显示数量
        - --sort 字段: id/title/author/created/status/type/series
        - --asc/--desc: 排序方向
        - --path: 额外显示文件路径
        - --compact: 紧凑显示(隐藏标签列)

        标签显示:
        - 输出样式为 #标签，多个标签用空格分开

        示例:
        list
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
        query_parts = []
        filters = {}
        limit = None
        sort_field = None
        order = None
        show_path = False
        compact = False

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

            key = None
            v = None
            if ":" in token:
                key, v = token.split(":", 1)
            elif "=" in token:
                key, v = token.split("=", 1)

            if key:
                key = key.lower()
                if key in ["author", "series", "title"]:
                    filters[key] = v
                elif key in ["tag", "tags"]:
                    filters["tags"] = v
                elif key in ["status"]:
                    try:
                        filters["status"] = int(v)
                    except Exception:
                        print(Colors.yellow(f"状态要是数字喵 (0或1)，已忽略: {token}"))
                elif key in ["type", "format", "ext"]:
                    filters["file_type"] = str(v).lstrip(".")
                else:
                    query_parts.append(token)
            else:
                query_parts.append(token)

            i += 1

        query = " ".join(query_parts).strip() if query_parts else None

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

        id_w = max(self._disp_width("ID"), max(self._disp_width(str(val(b, "id", ""))) for b in books))
        id_w = max(2, min(id_w, 6))

        status_w = self._disp_width("状态")
        status_w = max(status_w, self._disp_width("连载"))
        status_w = max(4, min(status_w, 6))

        fmt_w = max(self._disp_width("格式"), 4)
        fmt_w = min(fmt_w, 6)

        title_max = max(self._disp_width(str(val(b, "title", "") or "")) for b in books)
        author_max = max(self._disp_width(str(val(b, "author", "") or "")) for b in books)
        series_max = max(self._disp_width(str(val(b, "series", "") or "")) for b in books)

        title_w = max(self._disp_width("标题"), min(title_max, 30))
        author_w = max(self._disp_width("作者"), min(author_max, 18))
        series_w = max(self._disp_width("系列"), min(series_max, 16))

        sep = "   "
        base_total = id_w + title_w + author_w + status_w + fmt_w + series_w + len(sep) * 5
        tags_min = max(self._disp_width("标签"), 10)

        def shrink(col_w, min_w, need):
            if need <= 0:
                return col_w, need
            can = max(0, col_w - min_w)
            take = min(need, can)
            return col_w - take, need - take

        need = max(0, (base_total + (len(sep) + tags_min if show_tags else 0)) - term_width)
        title_w, need = shrink(title_w, 10, need)
        series_w, need = shrink(series_w, 8, need)
        author_w, need = shrink(author_w, 8, need)

        base_total = id_w + title_w + author_w + status_w + fmt_w + series_w + len(sep) * 5
        if show_tags:
            tags_w = max(tags_min, term_width - (base_total + len(sep)))
        else:
            tags_w = 0

        h_id = self._pad_disp("ID", id_w, align="right")
        h_title = self._pad_disp("标题", title_w)
        h_author = self._pad_disp("作者", author_w)
        h_status = self._pad_disp("状态", status_w)
        h_fmt = self._pad_disp("格式", fmt_w)
        h_series = self._pad_disp("系列", series_w)
        h_tags = "标签"

        header_parts = [h_id, h_title, h_author, h_status, h_fmt, h_series]
        if show_tags:
            header_parts.append(h_tags)
        header = sep.join(header_parts)
        print(Colors.cyan(Colors.BOLD + header + Colors.RESET))
        print(Colors.cyan("─" * min(self._disp_width(header), term_width)))

        for book in books:
            bid = self._pad_disp(str(val(book, "id", "")), id_w, align="right")
            title_raw = str(val(book, "title", "") or "")
            author_raw = str(val(book, "author", "") or "")
            series_raw = str(val(book, "series", "") or "")
            tags_raw = str(val(book, "tags", "") or "")
            ftype_raw = str(val(book, "file_type", "") or "")

            title = self._pad_disp(self._truncate_disp(title_raw, title_w), title_w)
            author = self._pad_disp(self._truncate_disp(author_raw, author_w), author_w)

            s_raw = "完结" if val(book, "status", 0) == 1 else "连载"
            status = self._pad_disp(s_raw, status_w)

            ftype = self._pad_disp(self._truncate_disp(ftype_raw, fmt_w), fmt_w)
            series = self._pad_disp(self._truncate_disp(series_raw, series_w), series_w)
            tags_view = self._format_tags_hash(tags_raw)
            tags = self._truncate_disp(tags_view, tags_w) if show_tags else ""

            c_id = Colors.yellow(bid)
            c_title = Colors.BOLD + title + Colors.RESET
            c_author = Colors.green(author)
            c_status = Colors.green(status) if val(book, "status", 0) == 1 else Colors.pink(status)
            c_series = Colors.cyan(series)

            row_parts = [c_id, c_title, c_author, c_status, ftype, c_series]
            if show_tags:
                row_parts.append(tags)
            print(sep.join(row_parts))

            if show_path:
                p_raw = str(val(book, "file_path", "") or "")
                p = self._truncate_disp(p_raw, max(10, term_width - 4))
                print(Colors.cyan(f"  ↳ {p}"))

    def do_search(self, arg):
        """搜索书籍: search [关键词] [field:value] ...
        
        支持的过滤器:
        author:作者名   - 搜索特定作者
        series:系列名   - 搜索特定系列
        tag:标签       - 搜索特定标签
        status:1/0     - 1=完结, 0=连载
        type:格式      - 如 txt, pdf

        示例: 
        search 魔法 author:佚名
        search status:1 tag:变身

        标签显示:
        - 输出样式为 #标签，多个标签用空格分开
        
        * 关键词支持模糊搜索喵！(输入 "魔圆" 可以搜到 "魔法少女小圆")
        """
        if not arg:
            print(Colors.red("请输入搜索内容喵！"))
            return

        def parse_status(v):
            s = "" if v is None else str(v).strip().lower()
            if s in {"1", "完结", "已完结", "end", "done", "completed"}:
                return 1
            if s in {"0", "连载", "连载中", "未完结", "ongoing"}:
                return 0
            try:
                return int(s)
            except Exception:
                return None

        args = shlex.split(arg)
        query_parts = []
        filters = {}

        for item in args:
            key = None
            val = None

            if ':' in item:
                key, val = item.split(':', 1)
            elif '=' in item:
                key, val = item.split('=', 1)

            if key:
                key = key.lower()
                if key in ['author', 'series', 'title']:
                    filters[key] = val
                elif key in ['tag', 'tags']:
                    filters['tags'] = val
                elif key in ['status']:
                    st = parse_status(val)
                    if st in {0, 1}:
                        filters['status'] = st
                    else:
                        print(Colors.yellow(f"状态要是 0/1 或 连载/完结 喵，已忽略: {item}"))
                elif key in ['type', 'format', 'ext']:
                    filters['file_type'] = val.lstrip('.')
                else:
                    query_parts.append(item)
            else:
                query_parts.append(item)

        query = " ".join(query_parts) if query_parts else None
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

    def complete_search(self, text, line, begidx, endidx):
        def safe_split(s):
            try:
                return shlex.split(s)
            except Exception:
                return str(s).split()

        before = line[:begidx]
        tokens_before = safe_split(before)
        tokens_all = safe_split(line)

        args_before = tokens_before[1:] if tokens_before and tokens_before[0] == "search" else tokens_before
        args_all = tokens_all[1:] if tokens_all and tokens_all[0] == "search" else tokens_all

        def q(v):
            v = "" if v is None else str(v)
            v = v.strip()
            if v == "":
                return v
            return shlex.quote(v)

        books = []
        try:
            books = list(self.db.list_books() or [])
        except Exception:
            books = []

        def parse_tags(raw):
            s = "" if raw is None else str(raw)
            s = s.replace("，", ",").replace("+", ",").replace("#", " ")
            parts = []
            for chunk in s.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                for p in chunk.split():
                    p = p.strip()
                    if p:
                        parts.append(p)
            out = []
            seen = set()
            for t in parts:
                if t in seen:
                    continue
                seen.add(t)
                out.append(t)
            return out

        if ":" not in text and "=" not in text:
            keys = ["author:", "series:", "tag:", "status:", "type:", "title:"]
            cand = [k for k in keys if k.startswith(text)]
            return cand

        sep = None
        if ":" in text:
            sep = ":"
        elif "=" in text:
            sep = "="

        if not sep:
            return []

        key, prefix = text.split(sep, 1)
        key = str(key).strip().lower()
        prefix = "" if prefix is None else str(prefix)

        if key in {"status"}:
            vals = ["0", "1", "连载", "完结"]
            out = []
            for v in vals:
                if v.startswith(prefix):
                    out.append(f"{key}{sep}{v}")
            return out

        if key in {"type", "format", "ext"}:
            seen = set()
            types = []
            for b in books:
                try:
                    ft = str(b["file_type"] or "")
                except Exception:
                    ft = ""
                ft = ft.strip().lstrip(".")
                if not ft or ft in seen:
                    continue
                seen.add(ft)
                types.append(ft)
            types.sort()
            return [f"{key}{sep}{q(v)}" for v in types if v.startswith(prefix)][:200]

        if key in {"author", "series", "title"}:
            seen = set()
            vals = []
            for b in books:
                try:
                    v = str(b[key] or "")
                except Exception:
                    v = ""
                v = v.strip()
                if not v or v in seen:
                    continue
                seen.add(v)
                vals.append(v)
            vals.sort()
            return [f"{key}{sep}{q(v)}" for v in vals if v.startswith(prefix)][:200]

        if key in {"tag", "tags"}:
            cnt = {}
            for b in books:
                try:
                    raw = b["tags"]
                except Exception:
                    raw = ""
                for t in parse_tags(raw):
                    if not t:
                        continue
                    cnt[t] = cnt.get(t, 0) + 1
            tags = sorted(cnt.items(), key=lambda x: (-x[1], x[0]))
            out = []
            for t, _ in tags:
                if t.startswith(prefix):
                    out.append(f"{key}{sep}{q(t)}")
                if len(out) >= 200:
                    break
            return out

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
