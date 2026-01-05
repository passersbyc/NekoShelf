import os
import re
import difflib
import shlex
import shutil

from .utils import Colors, simple_complete, path_complete


class SystemCommandsMixin:
    def _cmd_names(self):
        return sorted(
            {
                n[3:]
                for n in dir(self)
                if n.startswith("do_") and len(n) > 3 and n[3:].isidentifier()
            }
        )

    def _safe_split(self, s):
        try:
            return shlex.split(s)
        except Exception:
            return str(s).split()

    def do_help(self, arg):
        """显示帮助信息: help [命令]"""
        if arg:
            name = (str(arg).strip().split() or [""])[0]
            if name:
                method = getattr(self, f"do_{name}", None)
                doc = getattr(method, "__doc__", None) if method else None
                if doc:
                    cmd_names = set(self._cmd_names())

                    def paint(color, text, bold=False):
                        if text == "":
                            return text
                        if bold:
                            return f"{Colors.BOLD}{color}{text}{Colors.RESET}"
                        return f"{color}{text}{Colors.RESET}"

                    def paint_cmd(m):
                        w = m.group(0)
                        return paint(Colors.GREEN, w, bold=True)

                    def paint_opt(m):
                        return paint(Colors.YELLOW, m.group(0), bold=False)

                    def paint_placeholder(m):
                        inner = m.group(1)
                        if inner == "命令":
                            inner2 = paint(Colors.HEADER, inner, bold=True)
                            return f"{Colors.CYAN}<{Colors.RESET}{inner2}{Colors.CYAN}>{Colors.RESET}"
                        return paint(Colors.CYAN, f"<{inner}>")

                    def paint_quoted(m):
                        return paint(Colors.HEADER, m.group(0))

                    def colorize_line(line):
                        raw = line.rstrip("\n")
                        if not raw.strip():
                            return raw

                        stripped = raw.lstrip()
                        indent = raw[: len(raw) - len(stripped)]

                        head_keys = (
                            "导入文件",
                            "导出书籍",
                            "从网络下载书籍",
                            "常用",
                            "扩展用法",
                            "支持格式",
                            "命名格式",
                            "模式",
                            "示例",
                            "选择器支持",
                            "选项",
                            "注意",
                            "便捷",
                        )
                        if any(stripped.startswith(k) for k in head_keys):
                            if ":" in stripped or "：" in stripped:
                                sep = ":" if ":" in stripped else "："
                                left, right = stripped.split(sep, 1)
                                left2 = paint(Colors.BLUE, left + sep, bold=True)
                                stripped = left2 + " " + right.lstrip()
                            else:
                                stripped = paint(Colors.BLUE, stripped, bold=True)

                        stripped = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', paint_quoted, stripped)
                        stripped = re.sub(r"<([^>]+)>", paint_placeholder, stripped)
                        stripped = re.sub(r"--[A-Za-z0-9][A-Za-z0-9-]*", paint_opt, stripped)

                        for w in sorted(cmd_names, key=len, reverse=True):
                            stripped = re.sub(rf"\b{re.escape(w)}\b", paint_cmd, stripped)

                        stripped = re.sub(r"^(\s*)(\d+\))", lambda m: m.group(1) + paint(Colors.YELLOW, m.group(2), bold=True), stripped)
                        stripped = re.sub(r"^(\s*)(-)(\s+)", lambda m: m.group(1) + paint(Colors.CYAN, m.group(2), bold=True) + m.group(3), stripped)
                        stripped = re.sub(r"^(\s*)(\*)(\s+)", lambda m: m.group(1) + paint(Colors.CYAN, m.group(2), bold=True) + m.group(3), stripped)

                        return indent + stripped

                    text = doc.strip("\n")
                    print(paint(Colors.BLUE, f"\n📘 {name} 帮助", bold=True))
                    for ln in text.splitlines():
                        print(colorize_line(ln))
                    print("")
                    return

                cmd_names = self._cmd_names()
                close = difflib.get_close_matches(name, cmd_names, n=5, cutoff=0.4)
                print(Colors.red(f"找不到命令: {name} 喵..."))
                if close:
                    print(Colors.cyan("你是不是想输入:"))
                    print("  " + "  ".join(Colors.green(c) for c in close))
                    hint = close[0]
                    if hint == "help":
                        print(Colors.cyan("试试: help"))
                    else:
                        print(Colors.cyan(f"试试: help {hint}"))
                else:
                    print(Colors.cyan("输入 help 查看命令列表喵~"))
                return

            super().do_help(arg)
            return

        def cmd(name, width=10):
            return Colors.green(f"{name:<{width}}")

        def section(title):
            return f"{Colors.BLUE}{Colors.BOLD}{title}{Colors.RESET}"

        def dim(text):
            return f"{Colors.CYAN}{text}{Colors.RESET}"

        print(f"\n{Colors.BOLD}{Colors.CYAN}📖 {Colors.HEADER}萌萌{Colors.CYAN}的使用指南 📖{Colors.RESET}")
        print(dim("命令列表喵："))
        print(Colors.cyan("─" * 44))

        print(f"\n{section('📚 藏书管理')}")
        print(f"  {cmd('import')}  {Colors.yellow('导入书籍')}  {dim('(多种命名格式/文件夹/预览/删源文件)')}")
        print(f"  {cmd('download')} {Colors.yellow('下载书籍')}  {dim('(从网络链接并自动归档)')}")
        print(f"  {cmd('export')}   {Colors.yellow('导出书籍')}  {dim('(支持批量/筛选/zip)')}")
        print(f"  {cmd('list')}     {Colors.yellow('列出所有藏书')}")
        print(f"  {cmd('authors')}  {Colors.yellow('列出所有作者')}  {dim('(支持搜索/藏书统计)')}")
        print(f"  {cmd('search')}   {Colors.yellow('搜索书籍')}  {dim('(支持模糊搜索 & 高级过滤)')}")
        print(f"  {cmd('delete')}   {Colors.yellow('删除书籍')}  {dim('(文件和记录)')}")
        print(f"  {cmd('update')}   {Colors.yellow('修改书籍信息')}  {dim('(支持批量/筛选/ids/自动移动)')}")

        print(f"\n{section('🔧 系统维护')}")
        print(f"  {cmd('stats')}    {Colors.yellow('查看统计信息')}")
        print(f"  {cmd('clean')}    {Colors.yellow('清理并可同步藏书目录')}  {dim('(补录/纠正路径/删非法)')}")
        print(f"  {cmd('optimize')} {Colors.yellow('优化数据库')}  {dim('(重排ID/填补空缺/压缩体积)')}")
        print(f"  {cmd('clear')}    {Colors.yellow('清空屏幕')}  {dim('(焕然一新喵)')}")
        print(f"  {cmd('help')}     {Colors.yellow('显示这个帮助菜单')}")
        print(f"  {cmd('exit')}     {Colors.yellow('退出系统')}")

        print(Colors.cyan("─" * 44))
        tip = (
            f"{Colors.YELLOW}💡 提示:{Colors.RESET} "
            f"{Colors.CYAN}输入{Colors.RESET} "
            f"{Colors.BOLD}{Colors.GREEN}help{Colors.RESET} "
            f"{Colors.CYAN}<{Colors.HEADER}命令{Colors.CYAN}>{Colors.RESET} "
            f"{Colors.CYAN}查看详细用法喵~{Colors.RESET}"
        )
        print(tip)
        print(
            f"{Colors.CYAN}例如:{Colors.RESET} "
            f"{Colors.BOLD}{Colors.GREEN}help{Colors.RESET} {Colors.HEADER}import{Colors.RESET}"
            f"{Colors.CYAN}  或  {Colors.RESET}"
            f"{Colors.BOLD}{Colors.GREEN}help{Colors.RESET} {Colors.HEADER}export{Colors.RESET}"
        )
        print(
            f"{Colors.YELLOW}💡 小技巧:{Colors.RESET} "
            f"{Colors.CYAN}按{Colors.RESET} {Colors.BOLD}{Colors.GREEN}Tab{Colors.RESET} "
            f"{Colors.CYAN}可自动补全 ID/字段/选项喵~{Colors.RESET}"
        )
        print(
            f"{Colors.YELLOW}💡 小技巧:{Colors.RESET} "
            f"{Colors.CYAN}路径含空格时用引号包住，例如:{Colors.RESET} "
            f"{Colors.BOLD}{Colors.GREEN}import{Colors.RESET} {Colors.HEADER}\"/path/with space/a.txt\"{Colors.RESET}"
        )
        print(
            f"{Colors.YELLOW}💡 小技巧:{Colors.RESET} "
            f"{Colors.CYAN}也可以直接粘贴路径来导入，例如:{Colors.RESET} "
            f"{Colors.HEADER}/path/to/book.txt{Colors.RESET}"
        )
        print("")

    def complete_help(self, text, line, begidx, endidx):
        return [c for c in self._cmd_names() if c.startswith(text)]

    def emptyline(self):
        return

    def default(self, line):
        raw = (line or "").strip()
        if not raw:
            return

        if hasattr(self, "do_import"):
            try:
                expanded = os.path.expanduser(os.path.expandvars(raw))
            except Exception:
                expanded = raw

            try:
                if expanded and os.path.exists(expanded):
                    self.do_import(expanded)
                    return
            except Exception:
                pass

            tokens2 = self._safe_split(raw)
            if tokens2:
                first = tokens2[0]
                try:
                    first2 = os.path.expanduser(os.path.expandvars(first))
                except Exception:
                    first2 = first
                try:
                    if first2 and os.path.exists(first2):
                        tokens2[0] = first2
                        rebuilt = " ".join(shlex.quote(t) for t in tokens2)
                        self.do_import(rebuilt)
                        return
                except Exception:
                    pass

        tokens = self._safe_split(raw)
        if not tokens:
            return
        name = tokens[0]
        cmd_names = self._cmd_names()
        close = difflib.get_close_matches(name, cmd_names, n=5, cutoff=0.4)
        print(Colors.red(f"未知命令: {name} 喵..."))
        if close:
            print(Colors.cyan("你是不是想输入:"))
            print("  " + "  ".join(Colors.green(c) for c in close))
            hint = close[0]
            if hint == "help":
                print(Colors.cyan("试试: help"))
            else:
                print(Colors.cyan(f"试试: help {hint}"))
        else:
            print(Colors.cyan("输入 help 查看命令列表喵~"))

    def do_EOF(self, arg):
        """退出系统: Ctrl-D"""
        return True

    def do_clear(self, arg):
        """清空屏幕: clear"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(self.intro)

    def do_clean(self, arg="", silent=False):
        """清理无效记录: clean [--sync] [--dry-run] [--yes]

        默认行为(不带参数):
        1) 移除文件不存在的记录
        2) 移除标题以 . 开头的非法书籍记录
        3) 合并指向同一文件的重复记录（保留 ID 最大的）

        同步模式(clean --sync):
        - 扫描 library/ 下的文件，补录数据库缺失的记录
        - 补齐 file_hash，并尝试用 hash 找回搬家/改名的文件
        - 非法文件(不支持后缀或以 . 开头)会自动删除(可用 --keep-illegal 保留)

        选项:
        - --sync / --scan : 同步藏书目录到数据库
        - --dry-run       : 仅预览，不做任何写入/删除
        - --yes / -y      : 跳过确认，直接执行
        - --keep-illegal  : 同步时保留非法文件(默认会自动删除)

        示例:
        1) clean                  (仅清理数据库无效记录)
        2) clean --sync           (同步目录 + 清理数据库，需确认)
        3) clean --sync --yes     (同步 + 清理，不询问)
        4) clean --sync --dry-run (仅查看同步会做什么)
        """
        tokens = []
        try:
            tokens = shlex.split((arg or "").strip()) if (arg or "").strip() else []
        except Exception:
            tokens = []

        token0 = str(tokens[0]).strip().lower() if tokens else ""
        sync_lib = ("--sync" in tokens) or ("--scan" in tokens) or (token0 in {"sync", "scan"})
        dry_run = "--dry-run" in tokens
        yes = ("--yes" in tokens) or ("--force" in tokens) or ("-y" in tokens)
        illegal_mode = "always"
        if "--delete-illegal" in tokens:
            illegal_mode = "always"
        if "--keep-illegal" in tokens:
            illegal_mode = "keep"

        if silent:
            sync_lib = False



        tag_prefixes = ("【小说+漫画】", "【小说】", "【漫画】")

        def strip_tag_prefix(name):
            s = "" if name is None else str(name)
            for p in tag_prefixes:
                if s.startswith(p):
                    return s[len(p) :].lstrip()
            return s

        books = list(self.db.list_books() or [])
        if (not books) and (not sync_lib):
            if not silent:
                print(Colors.yellow("藏书阁是空的，不需要清理喵~"))
            return

        if not silent:
            print(Colors.cyan("正在扫描书架喵..."))

        removed_count = 0
        dedup_count = 0
        illegal_title_count = 0

        valid_books = []
        for book in books:
            # 0. 检查非法标题 (以 . 开头)
            try:
                title = str(book['title'] or "").strip()
            except Exception:
                title = ""
            if title.startswith('.'):
                if not silent:
                    print(Colors.yellow(f"发现非法标题书籍: [{book['id']}] {title}"))
                
                if dry_run:
                    illegal_title_count += 1
                else:
                    if self.db.delete_book(book['id']):
                        if not silent:
                            print(Colors.green("  -> 已清除非法记录"))
                        illegal_title_count += 1
                    else:
                        if not silent:
                            print(Colors.red("  -> 清除失败喵..."))
                continue

            file_path = book['file_path']
            if not os.path.exists(file_path):
                if not silent:
                    print(
                        Colors.yellow(
                            f"发现丢失的书籍: [{book['id']}] {book['title']} (路径: {file_path})"
                        )
                    )
                if dry_run:
                    removed_count += 1
                else:
                    if self.db.delete_book(book['id']):
                        if not silent:
                            print(Colors.green("  -> 已清除无效记录"))
                        removed_count += 1
                    else:
                        if not silent:
                            print(Colors.red("  -> 清除失败喵..."))
            else:
                valid_books.append(book)

        path_map = {}
        for book in valid_books:
            norm_path = os.path.normpath(book['file_path'])
            if norm_path not in path_map:
                path_map[norm_path] = []
            path_map[norm_path].append(book)

        author_fix_count = 0
        for book in valid_books:
            try:
                old_author = book['author'] or "佚名"
                new_author = strip_tag_prefix(old_author)
                if new_author != old_author:
                    if dry_run:
                        if not silent:
                            print(Colors.cyan(f"预览修正作者: [{book['id']}] {old_author} -> {new_author}"))
                        author_fix_count += 1
                    else:
                        self.db.update_book(book['id'], author=new_author)
                        if not silent:
                            print(Colors.green(f"已修正作者: [{book['id']}] {old_author} -> {new_author}"))
                        author_fix_count += 1
            except Exception:
                pass

        for path, duplicates in path_map.items():
            if len(duplicates) > 1:
                duplicates.sort(key=lambda x: x['id'], reverse=True)
                keep_book = duplicates[0]
                remove_books = duplicates[1:]

                if not silent:
                    print(Colors.yellow(f"发现重复记录: {path}"))
                    print(
                        Colors.cyan(
                            f"  -> 保留最新记录: [{keep_book['id']}] {keep_book['title']}"
                        )
                    )

                for dup in remove_books:
                    if dry_run:
                        dedup_count += 1
                    else:
                        if self.db.delete_book(dup['id']):
                            if not silent:
                                print(
                                    Colors.green(
                                        f"  -> 合并并移除旧记录: [{dup['id']}] {dup['title']}"
                                    )
                                )
                            dedup_count += 1

        if removed_count > 0 or dedup_count > 0 or illegal_title_count > 0 or author_fix_count > 0:
            msg = []
            if removed_count > 0:
                msg.append(f"移除了 {removed_count} 条无效记录")
            if illegal_title_count > 0:
                msg.append(f"清理了 {illegal_title_count} 本非法标题书籍")
            if dedup_count > 0:
                msg.append(f"合并了 {dedup_count} 条重复记录")
            if author_fix_count > 0:
                msg.append(f"修正了 {author_fix_count} 个作者名")
            if not silent:
                if dry_run:
                    print(Colors.green(f"清理预览: {'，'.join(msg)}喵！"))
                else:
                    print(Colors.green(f"自动清理: {'，'.join(msg)}喵！"))
        elif not silent:
            print(Colors.green("书架非常整洁，没有发现问题喵！"))

        if not sync_lib:
            return

        def abs_norm(p):
            try:
                return os.path.normpath(os.path.abspath(str(p)))
            except Exception:
                return os.path.normpath(str(p))

        try:
            lib_root_obj = getattr(self.fm, "library_dir", "library")
            lib_root = str(lib_root_obj)
        except Exception:
            lib_root = "library"

        if not os.path.isdir(lib_root):
            if not silent:
                print(Colors.red(f"找不到藏书目录喵: {lib_root}"))
            return

        def infer_meta_from_path(fp):
            author = "佚名"
            series = ""
            title0 = os.path.splitext(os.path.basename(fp))[0]
            title1, removed = self._strip_trailing_brackets(title0)
            title = title1 or title0
            st = self._infer_status_from_text(removed, default=None)
            status = 0 if st is None else int(st)
            tags = ""
            try:
                rel = os.path.relpath(fp, lib_root)
                parts = [p for p in rel.split(os.sep) if p and p not in {".", ".."}]
                if len(parts) >= 2:
                    author = strip_tag_prefix(parts[0]) or author
                if len(parts) >= 3:
                    series = os.sep.join(parts[1:-1]).strip(os.sep)
            except Exception:
                pass
            return title, author, series, tags, status

        if not silent:
            print(Colors.cyan("开始同步藏书目录到数据库喵..."))

        def plan_sync():
            book_by_id = {}
            path_set = set()
            for b in books:
                try:
                    bid = int(b["id"])
                except Exception:
                    continue
                book_by_id[bid] = b
                try:
                    p = b["file_path"]
                except Exception:
                    p = ""
                if p:
                    path_set.add(os.path.normpath(str(p)))
                    path_set.add(abs_norm(p))

            supported_exts = set(getattr(self, "_IMPORT_EXTS", {".txt", ".pdf", ".doc", ".docx", ".epub"}))
            hash_cache = {}

            hash_updates = []
            for bid, b in book_by_id.items():
                fp = ""
                try:
                    fp = b["file_path"]
                except Exception:
                    fp = ""
                if not fp or (not os.path.exists(fp)):
                    continue
                fh0 = ""
                try:
                    fh0 = b["file_hash"] if "file_hash" in b.keys() else ""
                except Exception:
                    fh0 = ""
                if fh0 and str(fh0).strip():
                    continue

                ap = abs_norm(fp)
                if ap in hash_cache:
                    fh = hash_cache.get(ap) or ""
                else:
                    fh = self._file_hash(fp)
                    hash_cache[ap] = fh
                if fh:
                    hash_updates.append((bid, fh))

            relinks = []
            adds = []
            illegal_files = []

            for root, _, files in os.walk(lib_root):
                for name in files:
                    fp = os.path.join(root, name)
                    try:
                        if os.path.islink(fp):
                            continue
                    except Exception:
                        pass

                    if name.startswith('.'):
                        illegal_files.append(fp)
                        continue

                    ext = os.path.splitext(name)[1].lower()
                    if ext not in supported_exts:
                        illegal_files.append(fp)
                        continue

                    fp_norm = os.path.normpath(fp)
                    fp_abs = abs_norm(fp)
                    if (fp_norm in path_set) or (fp_abs in path_set):
                        continue

                    if fp_abs in hash_cache:
                        fh = hash_cache.get(fp_abs) or ""
                    else:
                        fh = self._file_hash(fp)
                        hash_cache[fp_abs] = fh

                    if fh:
                        try:
                            cands = self.db.find_books_by_file_hash(fh, limit=5)
                        except Exception:
                            cands = []
                        if cands:
                            keep = cands[0]
                            kid = None
                            try:
                                kid = int(keep["id"])
                            except Exception:
                                kid = None
                            if kid is not None:
                                old_fp = ""
                                try:
                                    old_fp = keep["file_path"]
                                except Exception:
                                    old_fp = ""
                                if (not old_fp) or (not os.path.exists(old_fp)) or (os.path.normpath(str(old_fp)) != fp_norm):
                                    relinks.append((kid, fp_norm, ext.lstrip("."), fh))
                                    path_set.add(fp_norm)
                                    path_set.add(fp_abs)
                                    continue

                    title, author, series, tags, status = infer_meta_from_path(fp)
                    adds.append((title, author, tags, status, series, fp_norm, ext.lstrip("."), fh))
                    path_set.add(fp_norm)
                    path_set.add(fp_abs)

            return {
                "hash_updates": hash_updates,
                "relinks": relinks,
                "adds": adds,
                "illegal_files": illegal_files,
            }

        plan = plan_sync()
        hash_updates = plan["hash_updates"]
        relinks = plan["relinks"]
        adds = plan["adds"]
        illegal_files = plan["illegal_files"]

        if illegal_files and (not silent):
            print(Colors.yellow(f"发现 {len(illegal_files)} 个非法文件(不支持后缀或以 . 开头)喵~"))
            show_n = 30
            for x in illegal_files[:show_n]:
                print(Colors.yellow(f"  - {x}"))
            if len(illegal_files) > show_n:
                print(Colors.cyan(f"... 还有 {len(illegal_files) - show_n} 个未展示喵"))

        if adds and (not silent):
            print(Colors.cyan(f"准备补录 {len(adds)} 本书喵:"))
            show_n = 30
            for i, (title, author, tags, status, series, fp_norm, file_type, fh) in enumerate(adds[:show_n]):
                st_s = Colors.green("完结") if int(status or 0) == 1 else Colors.pink("连载")
                series_s = f"  {Colors.cyan('[' + str(series) + ']')}" if str(series or "").strip() else ""
                print(
                    f"  + {Colors.YELLOW}{str(file_type)}{Colors.RESET} "
                    f"[{Colors.yellow(str(i + 1))}] {Colors.BOLD}{title}{Colors.RESET} - {Colors.green(author)} ({st_s}){series_s}"
                )
            if len(adds) > show_n:
                print(Colors.cyan(f"... 还有 {len(adds) - show_n} 本未展示喵"))

        supported_exts2 = set(getattr(self, "_IMPORT_EXTS", {".txt", ".pdf", ".doc", ".docx", ".epub"}))

        def classify_author_dir(dir_path):
            has_doc = False
            has_pdf = False
            for root, _, files in os.walk(dir_path):
                for fname in files:
                    fp = os.path.join(root, fname)
                    try:
                        if os.path.islink(fp):
                            continue
                    except Exception:
                        pass
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in supported_exts2:
                        continue
                    if ext == ".pdf":
                        has_pdf = True
                    else:
                        has_doc = True
                    if has_doc and has_pdf:
                        return "【小说+漫画】"
            if has_doc:
                return "【小说】"
            if has_pdf:
                return "【漫画】"
            return ""

        author_renames = []
        try:
            for name in sorted(os.listdir(lib_root)):
                p = os.path.join(lib_root, name)
                if not os.path.isdir(p):
                    continue
                try:
                    if os.path.islink(p):
                        continue
                except Exception:
                    pass
                base = strip_tag_prefix(name).strip()
                if not base:
                    continue
                tag = classify_author_dir(p)
                new_name = f"{tag}{base}"
                if new_name == str(name):
                    continue
                author_renames.append((str(name), new_name))
        except Exception:
            author_renames = []

        if author_renames and (not silent):
            print(Colors.cyan(f"将为 {len(author_renames)} 个作者文件夹添加分类前缀喵:"))
            show_n = 30
            for old_name, new_name in author_renames[:show_n]:
                print(Colors.cyan(f"  - {old_name} -> {new_name}"))
            if len(author_renames) > show_n:
                print(Colors.cyan(f"... 还有 {len(author_renames) - show_n} 个未展示喵"))

        extra = []
        if hash_updates:
            extra.append(f"补齐 hash {len(hash_updates)} 条")
        if relinks:
            extra.append(f"纠正路径 {len(relinks)} 条")
        if adds:
            extra.append(f"补录 {len(adds)} 条")
        if author_renames:
            extra.append(f"标记作者 {len(author_renames)} 个")

        if dry_run:
            if not silent:
                print(Colors.green("同步预览完成喵！" + ("（" + "，".join(extra) + "）" if extra else "")))
            return

        if (not hash_updates) and (not relinks) and (not adds) and (not illegal_files):
            if not silent:
                print(Colors.green("同步完成喵！没有需要更新的内容~"))
            return

        if (not yes) and (not silent):
            ans = input(Colors.pink("预览如上，继续执行同步吗喵？(yes/no): ")).strip().lower()
            if ans not in {"y", "yes"}:
                print(Colors.cyan("操作取消了喵~"))
                return

        hash_filled = 0
        for bid, fh in hash_updates:
            try:
                if self.db.update_book(int(bid), file_hash=fh):
                    hash_filled += 1
            except Exception:
                pass

        relinked = 0
        for kid, fp_norm, file_type, fh in relinks:
            try:
                if self.db.update_book(int(kid), file_path=fp_norm, file_type=file_type, file_hash=fh):
                    relinked += 1
            except Exception:
                pass

        added = 0
        added_rows = []
        for title, author, tags, status, series, fp_norm, file_type, fh in adds:
            try:
                new_id = self.db.add_book(title, author, tags, status, series, fp_norm, file_type, file_hash=fh)
                added += 1
                added_rows.append((new_id, title, author, status, series, file_type))
            except Exception:
                pass

        if added_rows and (not silent):
            print(Colors.green(f"补录完成喵！共补录 {len(added_rows)} 本:"))
            show_n = 30
            for new_id, title, author, status, series, file_type in added_rows[:show_n]:
                st_s = Colors.green("完结") if int(status or 0) == 1 else Colors.pink("连载")
                series_s = f"  {Colors.cyan('[' + str(series) + ']')}" if str(series or "").strip() else ""
                print(
                    f"  + {Colors.YELLOW}{str(file_type)}{Colors.RESET} "
                    f"[{Colors.yellow(str(new_id))}] {Colors.BOLD}{title}{Colors.RESET} - {Colors.green(author)} ({st_s}){series_s}"
                )
            if len(added_rows) > show_n:
                print(Colors.cyan(f"... 还有 {len(added_rows) - show_n} 本未展示喵"))

        illegal_deleted = 0
        illegal_kept = 0
        if illegal_files and (not silent):
            if illegal_mode == "keep":
                illegal_kept = len(illegal_files)
            else:
                choice = None
                for x in illegal_files:
                    do_del = False
                    if illegal_mode == "always":
                        do_del = True
                    else:
                        if choice == "all":
                            do_del = True
                        elif choice == "none":
                            do_del = False
                        else:
                            ans = input(Colors.pink(f"删除非法文件吗喵？(yes/no/all/none): {x} ")).strip().lower()
                            if ans in {"y", "yes"}:
                                do_del = True
                            elif ans in {"a", "all"}:
                                do_del = True
                                choice = "all"
                            elif ans in {"n", "no"}:
                                do_del = False
                            elif ans in {"none"}:
                                do_del = False
                                choice = "none"
                            else:
                                do_del = False

                    if do_del:
                        try:
                            lib_abs = abs_norm(lib_root)
                            x_abs = abs_norm(x)
                            if os.path.commonpath([x_abs, lib_abs]) != lib_abs:
                                print(Colors.red(f"为安全起见，跳过删除(不在藏书目录内)喵: {x}"))
                                illegal_kept += 1
                                continue
                        except Exception:
                            pass
                        try:
                            if self.fm.delete_file(x):
                                illegal_deleted += 1
                            else:
                                illegal_kept += 1
                        except Exception:
                            illegal_kept += 1
                    else:
                        illegal_kept += 1

        renamed = 0
        if author_renames:
            for old_name, new_name in author_renames:
                old_dir = os.path.normpath(os.path.join(lib_root, old_name))
                new_dir = os.path.normpath(os.path.join(lib_root, new_name))

                try:
                    lib_abs = abs_norm(lib_root)
                    old_abs = abs_norm(old_dir)
                    new_abs = abs_norm(new_dir)
                    if os.path.commonpath([old_abs, lib_abs]) != lib_abs:
                        continue
                    if os.path.commonpath([new_abs, lib_abs]) != lib_abs:
                        continue
                except Exception:
                    continue

                if not os.path.isdir(old_dir):
                    continue
                
                # 定义合并函数
                def merge_dir_content(src, dst):
                    import shutil
                    import time
                    
                    if not os.path.exists(dst):
                        os.makedirs(dst)
                        
                    for item in os.listdir(src):
                        s = os.path.join(src, item)
                        d = os.path.join(dst, item)
                        
                        if os.path.isdir(s):
                            # 递归合并子目录
                            if os.path.exists(d) and os.path.isdir(d):
                                merge_dir_content(s, d)
                                try:
                                    os.rmdir(s)
                                except Exception:
                                    pass
                            elif os.path.exists(d):
                                # 目标是文件，冲突 -> 重命名源目录移动
                                ts = int(time.time() * 1000)
                                d_new = f"{d}_{ts}"
                                shutil.move(s, d_new)
                                # 更新该目录下所有书籍的 DB 记录
                                try:
                                    s_prefix = s + os.sep
                                    d_prefix = d_new + os.sep
                                    self.db.conn.execute(
                                        "UPDATE books SET file_path = REPLACE(file_path, ?, ?) WHERE file_path LIKE ?",
                                        (s_prefix, d_prefix, s_prefix + "%")
                                    )
                                except Exception:
                                    pass
                            else:
                                # 目标不存在，直接移动
                                shutil.move(s, d)
                        else:
                            # 文件
                            final_dst = d
                            if os.path.exists(d):
                                # 冲突 -> 重命名
                                base, ext = os.path.splitext(item)
                                ts = int(time.time() * 1000)
                                final_dst = os.path.join(dst, f"{base}_{ts}{ext}")
                                shutil.move(s, final_dst)
                                # 单独更新 DB
                                try:
                                    self.db.conn.execute(
                                        "UPDATE books SET file_path = ? WHERE file_path = ?",
                                        (final_dst, s)
                                    )
                                except Exception:
                                    pass
                            else:
                                shutil.move(s, d)

                if os.path.exists(new_dir):
                    if not silent:
                        print(Colors.yellow(f"目标作者目录已存在，正在合并喵: {new_dir}"))
                    
                    try:
                        merge_dir_content(old_dir, new_dir)
                        # 尝试删除旧目录 (使用 rmtree 确保彻底删除)
                        try:
                            shutil.rmtree(old_dir)
                        except Exception as e:
                            if not silent:
                                print(Colors.red(f"删除旧目录失败喵: {e}"))
                        renamed += 1
                    except Exception as e:
                        if not silent:
                            print(Colors.red(f"合并目录失败喵: {e}"))
                        continue
                else:
                    try:
                        os.rename(old_dir, new_dir)
                        renamed += 1
                    except Exception:
                        if not silent:
                            print(Colors.red(f"作者目录改名失败喵: {old_dir} -> {new_dir}"))
                        continue

                try:
                    prefix_old = os.path.normpath(os.path.join(lib_root, old_name)) + os.sep
                    prefix_new = os.path.normpath(os.path.join(lib_root, new_name)) + os.sep
                    cur = self.db.conn.cursor()
                    cur.execute(
                        "UPDATE books SET file_path = REPLACE(file_path, ?, ?) WHERE file_path LIKE ?",
                        (prefix_old, prefix_new, prefix_old + "%"),
                    )
                    self.db.conn.commit()
                except Exception:
                    pass

        if not silent:
            extra2 = []
            if hash_filled:
                extra2.append(f"补齐 hash {hash_filled} 条")
            if relinked:
                extra2.append(f"纠正路径 {relinked} 条")
            if added:
                extra2.append(f"补录 {added} 条")
            if illegal_deleted:
                extra2.append(f"删除非法 {illegal_deleted} 个")
            if illegal_kept and (illegal_mode == "keep"):
                extra2.append(f"保留非法 {illegal_kept} 个")
            if renamed:
                extra2.append(f"标记作者 {renamed} 个")
            print(Colors.green("同步完成喵！" + ("（" + "，".join(extra2) + "）" if extra2 else "")))


    def do_optimize(self, arg):
        """优化数据库: optimize [--yes]

        功能:
        1) 重新排列书籍 ID，填补空缺，使其连续 (1, 2, 3...)
        2) 重置自增序列
        3) 压缩数据库文件 (VACUUM)

        注意:
        - 仅当您不依赖特定 ID 引用书籍时使用
        - 此操作不可逆，建议先备份数据库

        选项:
        - --yes / -y: 跳过确认
        """
        args = shlex.split(arg or "")
        yes = ("--yes" in args) or ("-y" in args)

        if not yes:
            print(Colors.red("⚠️  警告: 此操作将重新编号所有书籍 ID！"))
            print(Colors.yellow("原来的 ID 将会改变，请确保没有外部引用依赖特定 ID。"))
            confirm = input(Colors.cyan("确认要继续吗喵？(y/N): ")).strip().lower()
            if confirm != "y":
                print(Colors.green("操作已取消喵。"))
                return

        print(Colors.cyan("正在整理书架，请稍候喵..."))

        try:
            # 1. 获取所有书籍，按 ID 排序以保持相对顺序
            all_books = sorted(self.db.list_books(), key=lambda x: x['id'])
            
            if not all_books:
                print(Colors.yellow("书架是空的，无需优化喵。"))
                return

            count = len(all_books)
            print(Colors.green(f"找到 {count} 本书，准备重排 ID..."))

            # 2. 事务处理
            cursor = self.db.conn.cursor()
            cursor.execute("BEGIN TRANSACTION")

            try:
                # 备份数据到内存
                books_data = []
                for b in all_books:
                    books_data.append({
                        'title': b['title'],
                        'author': b['author'],
                        'tags': b['tags'],
                        'status': b['status'],
                        'series': b['series'],
                        'file_path': b['file_path'],
                        'file_hash': b['file_hash'],
                        'file_type': b['file_type'],
                        'created_at': b['created_at']
                    })

                # 清空表
                cursor.execute("DELETE FROM books")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='books'")

                # 重新插入
                insert_sql = '''
                    INSERT INTO books (title, author, tags, status, series, file_path, file_hash, file_type, created_at)
                    VALUES (:title, :author, :tags, :status, :series, :file_path, :file_hash, :file_type, :created_at)
                '''
                cursor.executemany(insert_sql, books_data)
                
                self.db.conn.commit()
                print(Colors.green("ID 重排完成喵！"))
                
                # 3. VACUUM
                print(Colors.cyan("正在压缩数据库体积..."))
                self.db.conn.execute("VACUUM")
                print(Colors.green("优化全部完成！书架变得整整齐齐啦喵~ ✨"))

            except Exception as e:
                self.db.conn.rollback()
                print(Colors.red(f"优化失败，已回滚更改: {e}"))
                import traceback
                traceback.print_exc()

        except Exception as e:
            print(Colors.red(f"发生错误: {e}"))

    def complete_clean(self, text, line, begidx, endidx):
        opts = ["--sync", "--dry-run", "--yes", "--keep-illegal", "--delete-illegal"]
        return simple_complete(text, opts)

    def complete_optimize(self, text, line, begidx, endidx):
        opts = ["--yes"]
        return simple_complete(text, opts)

    def complete_help(self, text, line, begidx, endidx):
        cmds = [c[3:] for c in self.get_names() if c.startswith("do_")]
        return simple_complete(text, cmds)

    def preloop(self):
        self.do_clean(silent=True)

    def postloop(self):
        print(Colors.pink("\n萌萌去休息了喵~ 拜拜！"))
        self.db.close()

    def do_exit(self, arg):
        """退出系统: exit"""
        return True
