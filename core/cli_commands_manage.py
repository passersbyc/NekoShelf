import shlex
from collections import Counter
from pathlib import Path

from .utils import Colors, parse_id_ranges, parse_query_args, parse_tags_to_list
from .config import UPDATE_CONFIG


class ManageCommandsMixin:
    def complete_delete(self, text, line, begidx, endidx):
        flags = ["--dry-run", "--force", "--yes", "--keep-file"]

        def safe_split(s):
            try:
                return shlex.split(s)
            except Exception:
                return str(s).split()

        before = line[:begidx]
        tokens_before = safe_split(before)
        if tokens_before and tokens_before[0] == "delete":
            args_before = tokens_before[1:]
        else:
            args_before = tokens_before

        tokens_all = safe_split(line)
        args_all = tokens_all[1:] if tokens_all and tokens_all[0] == "delete" else tokens_all
        used_flags = {a for a in args_all if a.startswith("--")}

        if text.startswith("-"):
            return [f for f in flags if f.startswith(text) and f not in used_flags]

        if text == "" and any(a.startswith("--") for a in args_before):
            return [f for f in flags if f not in used_flags]

        if len(args_before) == 0:
            books = []
            try:
                books = self.db.list_books()
            except Exception:
                books = []
            ids = [str(b["id"]) for b in books[:200]]
            cand = ["all"] + ids
            return [c for c in cand if c.startswith(text)]

        if ":" not in text and "=" not in text:
            keys = ["author:", "series:", "tag:", "status:", "type:", "title:"]
            cand = [k for k in keys if k.startswith(text)]
            if "all".startswith(text):
                cand.append("all")
            return cand

        return []

    def _parse_tags(self, raw):
        return parse_tags_to_list(raw)

    def _join_tags(self, tags_list):
        tags_list = tags_list or []
        return ",".join([t for t in tags_list if t])

    def _format_tags_hash(self, tags_raw):
        tags = self._parse_tags(tags_raw)
        if not tags:
            return ""
        return " ".join(f"#{t}" for t in tags)

    def _safe_name(self, s):
        s = "" if s is None else str(s)
        s = s.strip()
        if not s:
            return ""

        forbidden = set('<>:"/\\|?*')
        out = []
        for ch in s:
            if ch in forbidden:
                continue
            oc = ord(ch)
            if oc < 32:
                continue
            out.append(ch)
        return "".join(out).strip()

    def _sync_fields_from_path(self, file_path):
        try:
            lib_root = Path(getattr(self.fm, "library_dir", "")).resolve()
        except Exception:
            lib_root = Path(".").resolve()

        try:
            p = Path(str(file_path)).resolve()
        except Exception:
            return {}

        try:
            rel = p.relative_to(lib_root)
        except Exception:
            return {}

        parts = rel.parts
        if not parts:
            return {}

        out = {"title": p.stem}
        if len(parts) >= 2:
            out["author"] = parts[0]
        if len(parts) >= 3:
            out["series"] = parts[1]
        return out

    def complete_update(self, text, line, begidx, endidx):
        allowed = list(UPDATE_CONFIG.get("allowed_fields") or ["title", "author", "series", "tags", "status"])
        flags = ["--dry-run", "--sync", "--no-move", "--diff", "--limit=", "--show="]

        def safe_split(s):
            try:
                return shlex.split(s)
            except Exception:
                return s.split()

        before = line[:begidx]
        tokens_before = safe_split(before)
        if tokens_before and tokens_before[0] == "update":
            args_before = tokens_before[1:]
        else:
            args_before = tokens_before

        tokens_all = safe_split(line)
        args_all = tokens_all[1:] if tokens_all and tokens_all[0] == "update" else tokens_all
        used_keys = set()
        for t in args_all[1:]:
            if "+=" in t:
                k = t.split("+=", 1)[0]
            elif "-=" in t:
                k = t.split("-=", 1)[0]
            elif "=" in t:
                k = t.split("=", 1)[0]
            else:
                continue
            if k in allowed:
                used_keys.add(k)

        used_flags = set([a for a in args_all[1:] if a.startswith("--")])

        books = []
        try:
            books = self.db.list_books()
        except Exception:
            books = []

        if len(args_before) == 0:
            ids = [str(b["id"]) for b in books[:200]]
            keys = ["ids", "all", "author:", "series:", "tag:", "status:", "type:", "title:"]
            cand = keys + ids
            return [x for x in cand if x.startswith(text)]

        book_id = None
        if args_all:
            try:
                book_id = int(args_all[0])
            except Exception:
                book_id = None

        book = None
        if book_id is not None:
            try:
                book = self.db.get_book(book_id)
            except Exception:
                book = None

        if text.startswith("-"):
            extra = []
            if text in {"--limit", "--show"}:
                extra = [text + "="]
            return [f for f in (flags + extra) if f.startswith(text) and f not in used_flags]

        if ("=" not in text) and ("+=" not in text) and ("-=" not in text):
            cand = []
            for k in allowed:
                if k in used_keys and k != "tags":
                    continue
                if k == "tags":
                    for w in ["tags=", "tags+=", "tags-="]:
                        if w.startswith(text):
                            cand.append(w)
                else:
                    for w in [f"{k}=", f"{k}+=" , f"{k}-="]:
                        if w.startswith(text):
                            cand.append(w)

            if text == "":
                for f in flags:
                    if f not in used_flags:
                        cand.append(f)
            return cand

        op = "="
        if "+=" in text:
            key, prefix = text.split("+=", 1)
            op = "+="
        elif "-=" in text:
            key, prefix = text.split("-=", 1)
            op = "-="
        else:
            key, prefix = text.split("=", 1)
        if key not in allowed:
            return []

        def q(v):
            v = "" if v is None else str(v)
            if v == "":
                return v
            return shlex.quote(v)

        suggestions = []

        if book is not None and prefix == "" and op == "=":
            try:
                cur = book[key]
            except Exception:
                cur = ""
            if cur is not None and str(cur) != "":
                suggestions.append(f"{key}={q(cur)}")

        if key == "status":
            for v in ["0", "1", "连载", "完结"]:
                w = f"{key}={v}"
                if w.startswith(text):
                    suggestions.append(w)
            return suggestions

        if key in {"author", "series"}:
            values = []
            seen = set()
            for b in books:
                try:
                    v = b[key]
                except Exception:
                    v = ""
                v = "" if v is None else str(v)
                if not v:
                    continue
                if v in seen:
                    continue
                seen.add(v)
                values.append(v)

            for v in values[:200]:
                if v.startswith(prefix):
                    suggestions.append(f"{key}={q(v)}")
            return suggestions

        if key == "tags":
            delim = ""
            head = ""
            tail = prefix
            if "," in prefix:
                head, tail = prefix.rsplit(",", 1)
                delim = ","
            elif " " in prefix:
                head, tail = prefix.rsplit(" ", 1)
                delim = " "
            head = head.rstrip()
            tail = tail.lstrip()

            if op == "-=" and book is not None:
                try:
                    cur_raw = book["tags"]
                except Exception:
                    cur_raw = ""
                cur_tags = self._parse_tags(cur_raw)
                for tag in cur_tags:
                    if tag.startswith(tail):
                        tag2 = f"#{tag}"
                        merged = (head + delim if head else "") + tag2
                        suggestions.append(f"tags-={q(merged)}")
                return suggestions

            cnt = Counter()
            for b in books:
                try:
                    raw = b["tags"]
                except Exception:
                    raw = ""
                for part in self._parse_tags(raw):
                    if part:
                        cnt[part] += 1

            for tag, _ in cnt.most_common(200):
                if tag.startswith(tail):
                    tag2 = f"#{tag}"
                    merged = (head + delim if head else "") + tag2
                    if op == "+=":
                        suggestions.append(f"tags+={q(merged)}")
                    else:
                        suggestions.append(f"tags={q(merged)}")
            return suggestions

        if key == "title":
            if book is not None:
                try:
                    t = str(book["title"] or "")
                except Exception:
                    t = ""
                if t and t.startswith(prefix):
                    suggestions.append(f"{key}={q(t)}")
            return suggestions

        return suggestions

    def do_delete(self, arg):
        """删除书籍: delete <选择器> [--dry-run] [--force/--yes] [--keep-file]

        选择器支持:
        1) 单个 ID: delete 12
        2) 多个 ID: delete 1,2,3
        3) ID 范围: delete 10-20
        4) 全部: delete all
        5) 过滤器: delete author:佚名 status:1
                 delete series:魔法系列 tag:变身
                 delete type:txt

        选项:
        - --dry-run: 仅预览将要删除的项目，不执行删除
        - --force/--yes: 跳过 yes 二次确认
        - --keep-file: 只删除数据库记录，不删除磁盘文件

        注意:
        - 默认会删除磁盘文件 + 数据库记录，且需要输入 yes 二次确认喵！
        """

        args = shlex.split((arg or "").strip())
        if not args:
            print(Colors.red('参数不够喵！示例: delete 12'))
            return

        def row_val(r, key, default=""):
            try:
                return r[key]
            except Exception:
                return default

        dry_run = False
        force = False
        keep_file = False

        rest = []
        for t in args:
            if t in {"--dry-run"}:
                dry_run = True
                continue
            if t in {"--force", "--yes"}:
                force = True
                continue
            if t in {"--keep-file"}:
                keep_file = True
                continue
            if t.startswith("--"):
                print(Colors.yellow(f"未知参数已忽略喵: {t}"))
                continue
            rest.append(t)

        if not rest:
            print(Colors.red('参数不够喵！示例: delete 12'))
            return

        selector = rest[0]
        sel_lower = str(selector).strip().lower()

        books = []
        try:
            if sel_lower == "all":
                if len(rest) == 1:
                    books = list(self.db.list_books())
                else:
                    q, f = parse_query_args(rest[1:], strict_id_mode=True)
                    books = list(self.db.advanced_search(q, f))
            else:
                q, f = parse_query_args(rest, strict_id_mode=True)
                if not q and not f:
                    print(Colors.red('没有找到可用的选择器喵！示例: delete 12 或 delete author:佚名'))
                    return
                books = list(self.db.advanced_search(q, f))
        except Exception as e:
            print(Colors.red(f"出错了喵... {e}"))
            return

        if not books:
            print(Colors.yellow("没有找到要删除的书喵~"))
            return

        books.sort(key=lambda b: int(row_val(b, "id", 0) or 0))

        print(Colors.yellow(f"将要删除 {len(books)} 本书喵:"))
        show_n = 50
        for i, book in enumerate(books[:show_n]):
            bid = row_val(book, "id", "?")
            title = row_val(book, "title", "")
            author = row_val(book, "author", "")
            status_str = "完结" if int(row_val(book, "status", 0) or 0) == 1 else "连载"
            s_color = Colors.green(status_str) if status_str == "完结" else Colors.pink(status_str)
            series = row_val(book, "series", "")
            series_str = f" [系列: {Colors.cyan(series)}]" if series else ""
            tags_view = self._format_tags_hash(row_val(book, "tags", ""))
            tags_str = f" {Colors.cyan(tags_view)}" if tags_view else ""
            print(
                f"[{Colors.yellow(str(bid))}] {Colors.BOLD}{title}{Colors.RESET} - "
                f"{Colors.green(author)} ({s_color}){series_str}{tags_str}"
            )
        if len(books) > show_n:
            print(Colors.cyan(f"... 还有 {len(books) - show_n} 本未展示喵"))

        if keep_file:
            print(Colors.cyan("--keep-file 已开启：只删数据库记录，不删磁盘文件喵~"))

        if dry_run:
            print(Colors.green("预览结束喵！没有执行删除。"))
            return

        if not force:
            confirm = input(Colors.pink("输入 yes/y 确认删除: ")).strip().lower()
            if confirm not in {"y", "yes"}:
                print(Colors.cyan("操作取消了喵~"))
                return

        file_deleted = 0
        file_failed = 0
        db_deleted = 0
        db_failed = 0

        for book in books:
            bid = int(row_val(book, "id", 0) or 0)
            fp = row_val(book, "file_path", "")

            if not keep_file:
                try:
                    if fp and self.fm.delete_file(fp):
                        file_deleted += 1
                    else:
                        file_failed += 1
                except Exception:
                    file_failed += 1

            try:
                if self.db.delete_book(bid):
                    db_deleted += 1
                else:
                    db_failed += 1
            except Exception:
                db_failed += 1

        msg = [f"数据库已删除 {db_deleted} 条"]
        if db_failed:
            msg.append(f"失败 {db_failed} 条")
        if not keep_file:
            msg.append(f"文件已删除 {file_deleted} 个")
            if file_failed:
                msg.append(f"文件删除失败 {file_failed} 个")

        print(Colors.green("删除完成喵！" + "，".join(msg)))

    def do_update(self, arg):
        """修改书籍信息: update <选择器> [field=value] ...

        选择器支持:
        1) 单个 ID: update 12 title=...
        2) 多个 ID: update 1,2,3 status=完结
        3) ID 范围: update 10-20 tags+="#新标签"
        4) 全部: update all status=连载 --dry-run
        5) 过滤器: update author:佚名 status:1 tags-="#旧标签"
                 update series:魔法系列 tag:变身
                 update type:txt

        支持字段:
        - title: 标题
        - author: 作者
        - series: 系列
        - tags: 标签(支持逗号/空格/#，输出为 #标签)
        - status: 0/1 或 连载/完结

        选项:
        - --dry-run: 仅预览不修改
        - --diff: 预览时输出字段变更详情
        - --show=N: 预览时展示前 N 条
        - --limit=N: 批量更新只处理前 N 本(按 ID 排序)
        - --sync: 从当前文件路径同步 title/author/series 并写回数据库
        - --no-move: 修改 title/author/series 时不搬家(只改数据库)

        标签操作:
        - tags=...   : 直接覆盖标签
        - tags+=...  : 增加标签
        - tags-=...  : 删除标签

        文本操作:
        - title+=... / title-=...   : 追加/删除子串
        - author+=... / author-=...
        - series+=... / series-=...

        便捷:
        - 输出匹配 ID 列表: update ids <选择器>

        示例:
        1) update 1 title="新标题" author="新作者"
        2) update 1 status=完结 tags="#变身 #换身"
        3) update 1 tags+="#换身" tags-="#精神" --dry-run
        4) update 1 --sync
        5) update series:碧蓝航线ts title="堕04" --dry-run
        """
        args = shlex.split((arg or "").strip())
        if not args:
            print(Colors.red('参数不够喵！示例: update 1 title="新书名"'))
            return

        allowed_fields = set(UPDATE_CONFIG.get("allowed_fields") or ["title", "author", "series", "tags", "status"])
        enable_text_ops = bool(UPDATE_CONFIG.get("enable_text_ops", True))

        def row_val(r, key, default=""):
            try:
                return r[key]
            except Exception:
                return default

        if str(args[0]).strip().lower() in {"ids", "id"}:
            sel = args[1:]
            if not sel:
                print(Colors.red('参数不够喵！示例: update ids author:"佚名"'))
                return

            if "--" in sel:
                cut = sel.index("--")
                selector = sel[:cut]
                updates = sel[cut + 1 :]
            else:
                def _is_update_token(t):
                    if t in {"--dry-run", "--sync", "--no-move", "--diff"}:
                        return True

                    if t.startswith("--limit=") or t.startswith("--show="):
                        return True

                    if "+=" in t:
                        k = t.split("+=", 1)[0]
                        return (k == "tags") or (enable_text_ops and (k in {"title", "author", "series"}))

                    if "-=" in t:
                        k = t.split("-=", 1)[0]
                        return (k == "tags") or (enable_text_ops and (k in {"title", "author", "series"}))

                    if "=" in t:
                        k = t.split("=", 1)[0]
                        return k in allowed_fields

                    return False

                def _is_force_update_token(t):
                    if "+=" in t:
                        return t.split("+=", 1)[0] == "tags"
                    if "-=" in t:
                        return t.split("-=", 1)[0] == "tags"
                    if "=" in t:
                        return t.split("=", 1)[0] in {"status", "tags", "title"}
                    return False

                selector = sel
                updates = []

                split_i = None
                for i, t in enumerate(sel):
                    if i <= 0:
                        continue
                    if not _is_force_update_token(t):
                        continue
                    if all(_is_update_token(x) for x in sel[i:]):
                        split_i = i
                        break

                if split_i is not None:
                    selector = sel[:split_i]
                    updates = sel[split_i:]

            books = []
            try:
                first = str(selector[0]).strip().lower()
                if first == "all":
                    if len(selector) == 1:
                        books = list(self.db.list_books())
                    else:
                        q, f = parse_query_args(selector[1:], strict_id_mode=True)
                        books = list(self.db.advanced_search(q, f))
                else:
                    q, f = parse_query_args(selector, strict_id_mode=True)
                    if not q and not f:
                        print(Colors.red('没有找到可用的选择器喵！示例: update ids author:"佚名"'))
                        return
                    books = list(self.db.advanced_search(q, f))
            except Exception as e:
                print(Colors.red(f"出错了喵... {e}"))
                return

            if not books:
                print(Colors.yellow("没有匹配到书喵~"))
                return

            ids2 = []
            seen = set()
            for b in books:
                try:
                    bid = int(row_val(b, "id", 0) or 0)
                except Exception:
                    bid = 0
                if not bid or bid in seen:
                    continue
                seen.add(bid)
                ids2.append(bid)
            ids2.sort()

            joined = ",".join(str(x) for x in ids2)

            if updates:
                rebuilt = " ".join(shlex.quote(t) for t in updates)
                return self.do_update(f"{joined} {rebuilt}")

            print(Colors.cyan(f"匹配到 {len(ids2)} 本，ID 列表喵:"))
            print(Colors.yellow(joined))
            print(Colors.cyan(f"可直接复制使用: update {joined} tags+='#标签' --dry-run"))
            return

        selector_tokens = []
        rest_tokens = []

        def _is_update_assignment_token(t):
            if t in {"--dry-run", "--sync", "--no-move", "--diff"}:
                return True
            if t.startswith("--limit=") or t.startswith("--show="):
                return True
            if "+=" in t:
                k = t.split("+=", 1)[0]
                return (k == "tags") or (enable_text_ops and (k in {"title", "author", "series"}))
            if "-=" in t:
                k = t.split("-=", 1)[0]
                return (k == "tags") or (enable_text_ops and (k in {"title", "author", "series"}))
            if "=" in t:
                k = t.split("=", 1)[0]
                return k in allowed_fields
            return False

        if "--" in args:
            cut = args.index("--")
            selector_tokens = args[:cut]
            rest_tokens = args[cut + 1 :]
        else:
            hit_rest = False
            for t in args:
                if hit_rest:
                    rest_tokens.append(t)
                    continue
                if _is_update_assignment_token(t):
                    hit_rest = True
                    rest_tokens.append(t)
                    continue
                selector_tokens.append(t)

        if not selector_tokens:
            print(Colors.red('参数不够喵！示例: update 1 title="新书名"'))
            return

        dry_run = False
        sync = False
        no_move = False
        diff = bool(UPDATE_CONFIG.get("default_dry_run_diff", False))
        limit_n = UPDATE_CONFIG.get("default_bulk_limit", None)
        show_n = UPDATE_CONFIG.get("default_dry_run_show", 50)

        field_updates = {}
        tags_set = None
        tags_add = []
        tags_del = []

        text_append = {"title": [], "author": [], "series": []}
        text_remove = {"title": [], "author": [], "series": []}

        i = 0
        while i < len(rest_tokens):
            item = rest_tokens[i]
            if item == "--dry-run":
                dry_run = True
                i += 1
                continue
            if item == "--sync":
                sync = True
                i += 1
                continue
            if item == "--no-move":
                no_move = True
                i += 1
                continue
            if item == "--diff":
                diff = True
                i += 1
                continue
            if item.startswith("--limit="):
                raw = item.split("=", 1)[1]
                try:
                    limit_n = int(str(raw).strip())
                except Exception:
                    print(Colors.yellow(f"--limit 值无效喵: {item}"))
                i += 1
                continue
            if item == "--limit" and (i + 1) < len(rest_tokens):
                raw = rest_tokens[i + 1]
                try:
                    limit_n = int(str(raw).strip())
                except Exception:
                    print(Colors.yellow(f"--limit 值无效喵: {raw}"))
                i += 2
                continue
            if item.startswith("--show="):
                raw = item.split("=", 1)[1]
                try:
                    show_n = int(str(raw).strip())
                except Exception:
                    print(Colors.yellow(f"--show 值无效喵: {item}"))
                i += 1
                continue
            if item == "--show" and (i + 1) < len(rest_tokens):
                raw = rest_tokens[i + 1]
                try:
                    show_n = int(str(raw).strip())
                except Exception:
                    print(Colors.yellow(f"--show 值无效喵: {raw}"))
                i += 2
                continue
            if item.startswith("--"):
                print(Colors.yellow(f"未知参数已忽略喵: {item}"))
                i += 1
                continue

            if "+=" in item:
                key, value = item.split("+=", 1)
                if key == "tags":
                    tags_add.extend(self._parse_tags(value))
                    i += 1
                    continue
                if enable_text_ops and key in {"title", "author", "series"}:
                    text_append[key].append(value)
                    i += 1
                    continue
                print(Colors.yellow(f"不支持的操作喵: {item}"))
                i += 1
                continue

            if "-=" in item:
                key, value = item.split("-=", 1)
                if key == "tags":
                    tags_del.extend(self._parse_tags(value))
                    i += 1
                    continue
                if enable_text_ops and key in {"title", "author", "series"}:
                    text_remove[key].append(value)
                    i += 1
                    continue
                print(Colors.yellow(f"不支持的操作喵: {item}"))
                i += 1
                continue

            if "=" not in item:
                print(Colors.yellow(f"无法识别的格式喵: {item}，请使用 field=value"))
                i += 1
                continue

            key, value = item.split("=", 1)
            if key not in allowed_fields:
                print(Colors.yellow(f"不支持修改字段 '{key}' 喵，已忽略~"))
                i += 1
                continue

            if key == "status":
                st = 1 if str(value).strip() in {"1", "完结", "完本"} else 0
                if st in {0, 1}:
                    value = st
                else:
                    print(Colors.red("status 必须是 0/1 或 连载/完结喵"))
                    i += 1
                    continue

            if key == "tags":
                tags_set = self._parse_tags(value)
            else:
                field_updates[key] = value

            i += 1

        has_text_ops = enable_text_ops and any(text_append[k] or text_remove[k] for k in text_append)
        if not field_updates and tags_set is None and not tags_add and not tags_del and not sync and not dry_run and not has_text_ops:
            print(Colors.yellow("没有有效的修改内容喵~"))
            return

        books = []
        try:
            first = str(selector_tokens[0]).strip().lower()
            if first == "all":
                if len(selector_tokens) == 1:
                    books = list(self.db.list_books())
                else:
                    q, f = parse_query_args(selector_tokens[1:], strict_id_mode=True)
                    books = list(self.db.advanced_search(q, f))
            else:
                q, f = parse_query_args(selector_tokens, strict_id_mode=True)
                if not q and not f:
                    print(Colors.red('没有找到可用的选择器喵！示例: update 12 title=... 或 update author:佚名 status:1'))
                    return
                books = list(self.db.advanced_search(q, f))
        except Exception as e:
            print(Colors.red(f"出错了喵... {e}"))
            return

        if not books:
            print(Colors.yellow("没有找到要修改的书喵~"))
            return

        books.sort(key=lambda b: int(row_val(b, "id", 0) or 0))

        if limit_n is not None:
            try:
                limit_n = int(limit_n)
            except Exception:
                limit_n = None
            if limit_n is not None and limit_n > 0 and len(books) > limit_n:
                books = books[:limit_n]

        def apply_one(book, verbose=False):
            book_id = int(row_val(book, "id", 0) or 0)
            current_path = row_val(book, "file_path", "")

            base_title = row_val(book, "title", "")
            base_author = row_val(book, "author", "")
            base_series = row_val(book, "series", "")

            if sync:
                synced = self._sync_fields_from_path(current_path)
                base_title = synced.get("title", base_title)
                base_author = synced.get("author", base_author)
                base_series = synced.get("series", base_series)

            def _apply_text_ops(raw, adds, dels):
                s = "" if raw is None else str(raw)
                for x in dels or []:
                    x = "" if x is None else str(x)
                    if x:
                        s = s.replace(x, "")
                for x in adds or []:
                    x = "" if x is None else str(x)
                    if x:
                        s = s + x
                return s.strip()

            new_title = field_updates.get("title", base_title)
            new_author = field_updates.get("author", base_author)
            new_series = field_updates.get("series", base_series)

            new_title = _apply_text_ops(new_title, text_append.get("title"), text_remove.get("title"))
            new_author = _apply_text_ops(new_author, text_append.get("author"), text_remove.get("author"))
            new_series = _apply_text_ops(new_series, text_append.get("series"), text_remove.get("series"))

            per_field_updates = dict(field_updates)
            if sync:
                if "title" not in per_field_updates and new_title != row_val(book, "title", ""):
                    per_field_updates["title"] = new_title
                if "author" not in per_field_updates and new_author != row_val(book, "author", ""):
                    per_field_updates["author"] = new_author
                cur_series = "" if row_val(book, "series", "") is None else str(row_val(book, "series", ""))
                new_series_s = "" if new_series is None else str(new_series)
                if "series" not in per_field_updates and new_series_s != cur_series:
                    per_field_updates["series"] = new_series

            if ("title" not in per_field_updates) and (text_append.get("title") or text_remove.get("title")):
                if new_title != row_val(book, "title", ""):
                    per_field_updates["title"] = new_title
            if ("author" not in per_field_updates) and (text_append.get("author") or text_remove.get("author")):
                if new_author != row_val(book, "author", ""):
                    per_field_updates["author"] = new_author
            if ("series" not in per_field_updates) and (text_append.get("series") or text_remove.get("series")):
                cur_series = "" if row_val(book, "series", "") is None else str(row_val(book, "series", ""))
                new_series_s = "" if new_series is None else str(new_series)
                if new_series_s != cur_series:
                    per_field_updates["series"] = new_series

            cur_tags = self._parse_tags(row_val(book, "tags", ""))
            if tags_set is not None:
                cur_tags = list(tags_set)
            if tags_add:
                for t in tags_add:
                    if t not in cur_tags:
                        cur_tags.append(t)
            if tags_del:
                cur_tags = [t for t in cur_tags if t not in set(tags_del)]

            updates = dict(per_field_updates)
            if tags_set is not None or tags_add or tags_del:
                updates["tags"] = self._join_tags(cur_tags)

            need_move = (
                (new_title != row_val(book, "title", ""))
                or (new_author != row_val(book, "author", ""))
                or ((new_series or "") != (row_val(book, "series", "") or ""))
            )

            planned_path = None
            if need_move:
                try:
                    lib_root = Path(getattr(self.fm, "library_dir", ".")).resolve()
                except Exception:
                    lib_root = Path(".").resolve()
                try:
                    cur_p = Path(str(current_path))
                    ext = cur_p.suffix
                except Exception:
                    ext = ""

                safe_author = self._safe_name(new_author) or "佚名"
                safe_title = self._safe_name(new_title) or "未命名"
                dest_dir = lib_root / safe_author
                if new_series:
                    safe_series = self._safe_name(new_series)
                    if safe_series:
                        dest_dir = dest_dir / safe_series
                planned_path = str(dest_dir / f"{safe_title}{ext}")

            if dry_run:
                status_str = "完结" if updates.get("status", row_val(book, "status", 0)) == 1 else "连载"
                s_color = Colors.green(status_str) if status_str == "完结" else Colors.pink(status_str)
                series_str = f" [系列: {Colors.cyan(new_series)}]" if new_series else ""
                tags_view = self._format_tags_hash(updates.get("tags", row_val(book, "tags", "")))
                tags_str = f" {Colors.cyan(tags_view)}" if tags_view else ""
                print(
                    f"[{Colors.yellow(str(book_id))}] {Colors.BOLD}{new_title}{Colors.RESET} - "
                    f"{Colors.green(new_author)} ({s_color}){series_str}{tags_str}"
                )
                if diff:
                    old_title = row_val(book, "title", "")
                    old_author = row_val(book, "author", "")
                    old_series = row_val(book, "series", "")
                    old_status = row_val(book, "status", 0)
                    old_tags = row_val(book, "tags", "")
                    if new_title != old_title:
                        print(Colors.cyan(f"  title: {old_title} -> {new_title}"))
                    if new_author != old_author:
                        print(Colors.cyan(f"  author: {old_author} -> {new_author}"))
                    if (new_series or "") != (old_series or ""):
                        print(Colors.cyan(f"  series: {old_series or ''} -> {new_series or ''}"))
                    new_status = updates.get("status", old_status)
                    if new_status != old_status:
                        print(Colors.cyan(f"  status: {old_status} -> {new_status}"))
                    new_tags_raw = updates.get("tags", old_tags)
                    if str(new_tags_raw or "") != str(old_tags or ""):
                        print(Colors.cyan(f"  tags: {self._format_tags_hash(old_tags)} -> {self._format_tags_hash(new_tags_raw)}"))
                if planned_path and (not no_move):
                    print(Colors.cyan(f"  预计搬家到: {planned_path}"))
                elif planned_path and no_move:
                    print(Colors.yellow("  --no-move 已开启：不会搬家，只更新数据库喵"))
                return True

            moved_path = None
            if need_move and (not no_move):
                try:
                    new_path = self.fm.move_book_file(current_path, new_title, new_author, new_series)
                    updates["file_path"] = new_path
                    moved_path = new_path
                    if verbose:
                        print(Colors.cyan(f"文件已搬家喵: {new_path}"))
                except Exception as e:
                    print(Colors.red(f"[{book_id}] 文件移动失败喵: {e}"))

            if updates and self.db.update_book(book_id, **updates):
                return True
            if not updates:
                return True
            if verbose:
                print(Colors.red("数据库更新失败喵..."))
            return False

        if len(books) == 1:
            one = books[0]
            one_id = int(row_val(one, "id", 0) or 0)
            if dry_run:
                print(Colors.cyan("预览更新喵:"))
                apply_one(one, verbose=True)
                return

            ok = apply_one(one, verbose=True)
            if ok:
                print(Colors.green("书籍信息更新成功喵！"))
                updated_book = self.db.get_book(one_id)
                status_str = "完结" if row_val(updated_book, "status", 0) == 1 else "连载"
                s_color = Colors.green(status_str) if status_str == "完结" else Colors.pink(status_str)
                series_val = row_val(updated_book, "series", "")
                series_str = f" [系列: {Colors.cyan(series_val)}]" if series_val else ""
                tags_view = self._format_tags_hash(row_val(updated_book, "tags", ""))
                tags_str = f" {Colors.cyan(tags_view)}" if tags_view else ""
                print(
                    f"[{Colors.yellow(str(row_val(updated_book, 'id', one_id)))}] {Colors.BOLD}{row_val(updated_book, 'title', '')}{Colors.RESET} - "
                    f"{Colors.green(row_val(updated_book, 'author', ''))} ({s_color}){series_str}{tags_str}"
                )
            else:
                print(Colors.red("更新失败喵..."))
            return

        if dry_run:
            print(Colors.cyan(f"预览批量更新喵：共 {len(books)} 本"))
            show_n = 50 if (show_n is None or show_n <= 0) else int(show_n)
            ok_n = 0
            for b in books[:show_n]:
                if apply_one(b):
                    ok_n += 1
            if len(books) > show_n:
                print(Colors.cyan(f"... 还有 {len(books) - show_n} 本未展示喵"))
            print(Colors.green(f"预览结束喵！展示 {min(len(books), show_n)} 本。"))
            return

        ok = 0
        fail = 0
        for b in books:
            if apply_one(b):
                ok += 1
            else:
                fail += 1
        print(Colors.green(f"批量更新完成喵！成功 {ok}，失败 {fail}。"))
