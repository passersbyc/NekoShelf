import os
import re
import difflib
import shlex
import shutil
import datetime

from ..import_engine import ImportEngine
from ..config import VERSION
from ..utils import Colors, simple_complete, path_complete, get_logger


class SystemCommandsMixin:
    def do_version(self, arg):
        """显示当前版本信息"""
        print(f"{Colors.GREEN}NekoShelf v{VERSION}{Colors.RESET}")
        print(f"{Colors.CYAN}萌萌的本地化漫画小说自动管理系统{Colors.RESET}")

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
                            "功能",
                            "支持站点",
                            "通用下载",
                            "默认(安全模式)",
                            "修复模式",
                            "范围参数",
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

                        stripped = re.sub(
                            r"^(\s*)(\d+\))",
                            lambda m: m.group(1) + paint(Colors.YELLOW, m.group(2), bold=True),
                            stripped,
                        )
                        stripped = re.sub(
                            r"^(\s*)(-)(\s+)",
                            lambda m: m.group(1) + paint(Colors.CYAN, m.group(2), bold=True) + m.group(3),
                            stripped,
                        )
                        stripped = re.sub(
                            r"^(\s*)(\*)(\s+)",
                            lambda m: m.group(1) + paint(Colors.CYAN, m.group(2), bold=True) + m.group(3),
                            stripped,
                        )

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
        print(f"  {cmd('download')} {Colors.yellow('下载/爬虫')}  {dim('(支持Pixiv/通用下载/自动归档)')}")
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
        print(f"  {cmd('reset')}    {Colors.yellow('重置系统')}  {dim('(清空所有数据/慎用)')}")
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

    def do_reset(self, arg):
        """重置系统 (清空所有数据): reset [--yes]

        警告: 此操作将删除数据库中的所有书籍记录、作者记录，
        并清空 Library 目录下的所有文件！无法撤销！
        """
        args = arg.split()
        force = "--yes" in args or "-y" in args

        print(Colors.red(f"\n{Colors.BOLD}⚠️  危险操作警告 ⚠️{Colors.RESET}"))
        print(Colors.red("即将清空所有数据，包括："))
        print(Colors.red("1. 数据库中的所有书籍和作者记录"))
        print(Colors.red("2. 书库目录下的所有文件 (实体书)"))
        print(Colors.red("此操作不可恢复！"))

        if not force:
            confirm = input(Colors.yellow("\n你确定要这么做吗？请输入 'yes' 确认: ")).strip()
            if confirm.lower() != "yes":
                print(Colors.green("操作已取消喵~"))
                return

        print(Colors.cyan("\n正在重置数据库..."))
        if self.db.clear_all():
            print(Colors.green("数据库已清空喵！"))
        else:
            print(Colors.red("数据库清空失败喵..."))

        print(Colors.cyan("正在清空书库文件..."))
        if self.fm.clear_library():
            print(Colors.green("书库文件已清空喵！"))
        else:
            print(Colors.red("书库清空失败喵..."))

        print(Colors.green("\n✨ 系统已重置为初始状态喵！"))

    def do_clean(self, arg="", silent=False):
        """数据库完整性检查与修复: clean [--fix] [--yes] [范围]

        默认(安全模式):
        - 扫描实际文件(以文件为准)，生成差异报告，不做任何修改

        修复模式:
        - 使用 --fix 显式开启
        - 自动备份数据库
        - 使用事务保证原子性
        - 自动删除多余记录 / 补录缺失记录 / 更新不一致的元数据
        - 修复后自动复检

        范围参数:
        - --dir=PATH
        - --type=pdf
        - --since=YYYY-MM-DD / --until=YYYY-MM-DD
        - --resume-from=PATH

        选项:
        - --fix / --apply
        - --yes / -y
        - --dry-run
        """
        if silent:
            return

        def safe_split(s):
            try:
                return shlex.split((s or "").strip()) if (s or "").strip() else []
            except Exception:
                return str(s or "").split()

        tokens = safe_split(arg)
        yes = ("--yes" in tokens) or ("-y" in tokens)
        fix = ("--fix" in tokens) or ("--apply" in tokens) or ("--repair" in tokens)

        dir_filter = ""
        type_filter = ""
        since_s = ""
        until_s = ""
        resume_from = ""
        for t in tokens:
            if t.startswith("--dir="):
                dir_filter = t.split("=", 1)[1].strip()
            elif t.startswith("--type="):
                type_filter = t.split("=", 1)[1].strip().lstrip(".")
            elif t.startswith("--ext="):
                type_filter = t.split("=", 1)[1].strip().lstrip(".")
            elif t.startswith("--since="):
                since_s = t.split("=", 1)[1].strip()
            elif t.startswith("--until="):
                until_s = t.split("=", 1)[1].strip()
            elif t.startswith("--resume-from="):
                resume_from = t.split("=", 1)[1].strip()

        logger = get_logger()

        try:
            lib_root_obj = getattr(self.fm, "library_dir", "library")
            lib_root = os.path.abspath(str(lib_root_obj))
        except Exception:
            lib_root = os.path.abspath("library")

        scope_root = lib_root
        if dir_filter:
            try:
                expanded = os.path.expanduser(os.path.expandvars(dir_filter))
            except Exception:
                expanded = dir_filter
            if not os.path.isabs(expanded):
                scope_root = os.path.abspath(os.path.join(lib_root, expanded))
            else:
                scope_root = os.path.abspath(expanded)

        if not os.path.exists(scope_root):
            print(Colors.red(f"找不到目录喵: {scope_root}"))
            return

        supported_exts = set(getattr(self, "_IMPORT_EXTS", {".txt", ".pdf", ".doc", ".docx", ".epub", ".cbz", ".zip"}))
        supported_exts = {("." + str(e).lstrip(".")) if e else e for e in supported_exts}
        type_ext = ("." + type_filter.lower().lstrip(".")) if type_filter else ""

        def parse_dt(s, end=False):
            s = (s or "").strip()
            if not s:
                return None
            try:
                if len(s) == 10 and "T" not in s and ":" not in s:
                    d = datetime.datetime.fromisoformat(s)
                    if end:
                        d = d + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)
                    return d
                return datetime.datetime.fromisoformat(s)
            except Exception:
                return None

        since_dt = parse_dt(since_s, end=False)
        until_dt = parse_dt(until_s, end=True)
        since_ts = since_dt.timestamp() if since_dt else None
        until_ts = until_dt.timestamp() if until_dt else None

        def abs_norm(p):
            try:
                return os.path.normpath(os.path.abspath(str(p)))
            except Exception:
                return os.path.normpath(str(p))

        def under_root(root, p):
            root = abs_norm(root)
            p = abs_norm(p)
            try:
                return os.path.commonpath([root, p]) == root
            except Exception:
                return False

        def iter_files(root_path):
            if os.path.isfile(root_path):
                yield root_path
                return
            for r, _, files2 in os.walk(root_path):
                for name in files2:
                    yield os.path.join(r, name)

        eng = ImportEngine(self.db, self.fm, import_exts=supported_exts)
        hash_cache = {}

        def file_hash(fp):
            k = abs_norm(fp)
            if k in hash_cache:
                return hash_cache[k]
            h = eng.file_hash(k)
            hash_cache[k] = h
            return h

        file_infos = {}
        file_lookup = {}
        illegal_files = []

        try:
            cwd = os.path.abspath(os.getcwd())
        except Exception:
            cwd = ""

        scanned = 0
        for fp in iter_files(scope_root):
            scanned += 1
            base = os.path.basename(fp)
            if base.startswith("."):
                illegal_files.append(fp)
                continue
            ext = os.path.splitext(base)[1].lower()
            if ext not in supported_exts:
                illegal_files.append(fp)
                continue
            if type_ext and ext != type_ext:
                continue
            try:
                st = os.stat(fp)
            except PermissionError as e:
                print(Colors.red(f"权限不足，无法读取文件喵: {fp} ({e})"))
                continue
            except OSError as e:
                print(Colors.red(f"读取文件失败喵: {fp} ({e})"))
                continue

            mtime = float(st.st_mtime)
            if since_ts is not None and mtime < since_ts:
                continue
            if until_ts is not None and mtime > until_ts:
                continue

            ap = abs_norm(fp)
            info = {"path": ap, "size": int(st.st_size), "mtime": float(st.st_mtime), "ext": ext}
            file_infos[ap] = info

            cands = set()
            cands.add(ap)
            cands.add(os.path.normpath(fp))
            try:
                if cwd:
                    rel_cwd = os.path.relpath(ap, cwd)
                    cands.add(rel_cwd)
                    cands.add(os.path.normpath(rel_cwd))
            except Exception:
                pass
            for c in cands:
                if c and c not in file_lookup:
                    file_lookup[c] = ap

            if scanned % 500 == 0:
                print(Colors.cyan(f"已扫描 {scanned} 个文件喵..."))

        if resume_from:
            rf = abs_norm(resume_from)
            if rf in file_infos:
                started = False
                new_infos = {}
                for k in sorted(file_infos.keys()):
                    if (not started) and k == rf:
                        started = True
                    if started:
                        new_infos[k] = file_infos[k]
                file_infos = new_infos

        try:
            books_all = list(self.db.list_books() or [])
        except Exception:
            books_all = []

        books = []
        for b in books_all:
            try:
                fp = b["file_path"]
            except Exception:
                fp = ""
            if not fp:
                continue
            ap = abs_norm(fp)
            if under_root(scope_root, ap):
                books.append(b)

            if os.path.exists(fp):
                ap2 = abs_norm(fp)
                if ap2 not in file_infos:
                    try:
                        st = os.stat(fp)
                        file_infos[ap2] = {"path": ap2, "size": int(st.st_size), "mtime": float(st.st_mtime), "ext": os.path.splitext(fp)[1].lower()}
                    except Exception:
                        pass
                if fp and fp not in file_lookup:
                    file_lookup[fp] = ap2
                np2 = os.path.normpath(fp)
                if np2 and np2 not in file_lookup:
                    file_lookup[np2] = ap2
                try:
                    if cwd:
                        rel_cwd = os.path.relpath(ap2, cwd)
                        if rel_cwd not in file_lookup:
                            file_lookup[rel_cwd] = ap2
                        rel2 = os.path.normpath(rel_cwd)
                        if rel2 not in file_lookup:
                            file_lookup[rel2] = ap2
                except Exception:
                    pass

        db_by_file = {}
        db_by_id = {}
        for b in books:
            try:
                bid = int(b["id"])
            except Exception:
                continue
            db_by_id[bid] = b
            try:
                fp = b["file_path"]
            except Exception:
                fp = ""
            if not fp:
                continue
            canon = file_lookup.get(fp) or file_lookup.get(os.path.normpath(fp)) or file_lookup.get(abs_norm(fp))
            if not canon:
                canon = abs_norm(fp)
            db_by_file.setdefault(canon, []).append(b)

        missing_files_records = []
        relink_records = []
        duplicates_records = []
        missing_db_records = []
        meta_mismatches = []

        size_index = {}
        for ap, info in file_infos.items():
            size_index.setdefault(int(info.get("size") or 0), []).append(ap)

        for ap, b_list in db_by_file.items():
            if len(b_list) > 1:
                ids = []
                for b in b_list:
                    try:
                        ids.append(int(b["id"]))
                    except Exception:
                        pass
                if ids:
                    duplicates_records.append({"path": ap, "ids": sorted(ids)})

        for bid, b in db_by_id.items():
            fp = ""
            try:
                fp = b["file_path"]
            except Exception:
                fp = ""
            if not fp:
                continue

            if os.path.exists(fp):
                canon = file_lookup.get(fp) or file_lookup.get(os.path.normpath(fp)) or file_lookup.get(abs_norm(fp))
                if not canon:
                    canon = abs_norm(fp)
                info = file_infos.get(canon)
                if not info:
                    continue

                db_size = None
                db_mtime = None
                db_hash = ""
                try:
                    if "file_size" in b.keys():
                        db_size = b["file_size"]
                except Exception:
                    db_size = None
                try:
                    if "file_mtime" in b.keys():
                        db_mtime = b["file_mtime"]
                except Exception:
                    db_mtime = None
                try:
                    db_hash = (b["file_hash"] if "file_hash" in b.keys() else "") or ""
                except Exception:
                    db_hash = ""

                need_size = (db_size is None) or (int(db_size) != int(info.get("size") or 0))
                need_mtime = (db_mtime is None) or (abs(float(db_mtime) - float(info.get("mtime") or 0.0)) > 1.0)
                need_hash = False
                new_hash = ""
                if db_hash:
                    new_hash = file_hash(canon)
                    if new_hash and new_hash != db_hash:
                        need_hash = True
                else:
                    new_hash = file_hash(canon)
                    if new_hash:
                        need_hash = True

                if need_size or need_mtime or need_hash:
                    meta_mismatches.append(
                        {
                            "id": bid,
                            "path": canon,
                            "need_hash": need_hash,
                            "new_hash": new_hash,
                            "size": int(info.get("size") or 0),
                            "mtime": float(info.get("mtime") or 0.0),
                        }
                    )
                continue

            fh = ""
            try:
                fh = (b["file_hash"] if "file_hash" in b.keys() else "") or ""
            except Exception:
                fh = ""
            fsz = None
            try:
                if "file_size" in b.keys():
                    fsz = b["file_size"]
            except Exception:
                fsz = None

            if fh:
                candidates = []
                if fsz is not None:
                    candidates = list(size_index.get(int(fsz), []))
                if not candidates:
                    candidates = list(file_infos.keys())
                found = ""
                for cand in candidates[:500]:
                    if file_hash(cand) == fh:
                        found = cand
                        break
                if found:
                    relink_records.append({"id": bid, "old": fp, "new": found, "hash": fh})
                else:
                    missing_files_records.append({"id": bid, "path": fp})
            else:
                missing_files_records.append({"id": bid, "path": fp})

        for ap in sorted(file_infos.keys()):
            if ap not in db_by_file:
                missing_db_records.append({"path": ap})

        print(Colors.cyan("\n📦 完整性报告(以实际文件为准)"))
        print(Colors.cyan(f"  范围: {scope_root}"))
        if type_ext:
            print(Colors.cyan(f"  类型: {type_ext.lstrip('.')}"))
        if since_dt:
            print(Colors.cyan(f"  起始: {since_dt.strftime('%Y-%m-%d %H:%M:%S')}"))
        if until_dt:
            print(Colors.cyan(f"  截止: {until_dt.strftime('%Y-%m-%d %H:%M:%S')}"))

        print(Colors.yellow("\n问题汇总:"))
        print(f"  - 数据库多余记录(文件缺失): {len(missing_files_records)}")
        print(f"  - 数据库缺失记录(文件未入库): {len(missing_db_records)}")
        print(f"  - 可自动纠正路径(靠 hash 找回): {len(relink_records)}")
        print(f"  - 指向同一文件的重复记录: {len(duplicates_records)}")
        print(f"  - 元数据不一致(大小/时间/hash): {len(meta_mismatches)}")
        if illegal_files:
            print(f"  - 非法/忽略文件: {len(illegal_files)}")

        def show(label, items, fmt):
            if not items:
                return
            print(Colors.yellow(f"\n{label} (展示前 10 条):"))
            for x in items[:10]:
                print(fmt(x))
            if len(items) > 10:
                print(Colors.cyan(f"  ... 还有 {len(items) - 10} 条"))

        show("数据库多余记录", missing_files_records, lambda x: f"  - [{x['id']}] {x['path']}")
        show("数据库缺失记录", missing_db_records, lambda x: f"  - {x['path']}")
        show("可纠正路径", relink_records, lambda x: f"  - [{x['id']}] {x['old']} -> {x['new']}")
        show("重复记录", duplicates_records, lambda x: f"  - {x['path']}  ids={','.join(str(i) for i in x['ids'])}")
        show("元数据不一致", meta_mismatches, lambda x: f"  - [{x['id']}] {x['path']}")

        if (not fix) or ("--dry-run" in tokens):
            if not fix:
                total_issues = (
                    len(missing_files_records)
                    + len(missing_db_records)
                    + len(relink_records)
                    + len(duplicates_records)
                    + len(meta_mismatches)
                )
                if total_issues > 0:
                    print(Colors.cyan("\n建议: clean --fix --yes 进行自动修复喵"))
                else:
                    if illegal_files:
                        print(Colors.green("\n数据库状态完美喵！(虽然有一些未收录的文件/非法文件)"))
                    else:
                        print(Colors.green("\n太棒了喵！书库非常完美，没有任何问题喵~"))
            return

        if not yes:
            print(Colors.red("\n⚠️  修复模式会修改数据库喵！"))
            ans = input(Colors.cyan("确认继续吗？请输入 yes: ")).strip().lower()
            if ans != "yes":
                print(Colors.green("操作已取消喵。"))
                return

        db_path = ""
        try:
            db_path = str(getattr(self.db, "db_path", "") or "")
        except Exception:
            db_path = ""
        if not db_path:
            print(Colors.red("找不到数据库路径喵..."))
            return

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{db_path}.bak_{ts}"
        try:
            shutil.copy2(db_path, backup_path)
        except Exception as e:
            print(Colors.red(f"数据库备份失败喵: {e}"))
            return

        try:
            logger.info("clean_backup db=%s backup=%s", db_path, backup_path)
        except Exception:
            pass

        conn = getattr(self.db, "conn", None)
        if conn is None:
            print(Colors.red("数据库连接不可用喵..."))
            return

        def infer_from_library_path(ap):
            author = "佚名"
            series = ""
            try:
                if under_root(lib_root, ap):
                    rel = os.path.relpath(ap, lib_root)
                    parts = [p for p in rel.split(os.sep) if p and p not in {".", ".."}]
                    if len(parts) >= 2:
                        author = parts[0].strip() or author
                    if len(parts) >= 3:
                        series = os.sep.join(parts[1:-1]).strip(os.sep)
            except Exception:
                pass
            return author, series

        try:
            self.db._suspend_commit = True
        except Exception:
            pass

        last_fp = ""
        try:
            conn.execute("BEGIN")

            del_dup = 0
            keep_ids = set()
            for item in duplicates_records:
                ids = list(item.get("ids") or [])
                if ids:
                    keep_ids.add(max(ids))
            for item in duplicates_records:
                ids = list(item.get("ids") or [])
                if len(ids) <= 1:
                    continue
                keep = max(ids)
                for bid in ids:
                    if bid == keep:
                        continue
                    last_fp = str(item.get("path") or "")
                    if self.db.delete_book(int(bid)):
                        del_dup += 1
                        try:
                            logger.info("clean_delete_duplicate book_id=%s keep_id=%s", bid, keep)
                        except Exception:
                            pass

            del_orphan = 0
            for item in missing_files_records:
                bid = int(item["id"])
                if bid in keep_ids:
                    continue
                last_fp = str(item.get("path") or "")
                if self.db.delete_book(bid):
                    del_orphan += 1
                    try:
                        logger.info("clean_delete_orphan book_id=%s", bid)
                    except Exception:
                        pass

            relinked = 0
            for item in relink_records:
                bid = int(item["id"])
                newp = str(item["new"])
                last_fp = newp
                if self.db.update_book(bid, file_path=newp):
                    relinked += 1
                    try:
                        logger.info("clean_relink book_id=%s new_path=%s", bid, newp)
                    except Exception:
                        pass

            updated_meta = 0
            for item in meta_mismatches:
                bid = int(item["id"])
                fp = str(item["path"])
                last_fp = fp
                upd = {"file_size": int(item.get("size") or 0), "file_mtime": float(item.get("mtime") or 0.0)}
                if item.get("need_hash") and item.get("new_hash"):
                    upd["file_hash"] = str(item.get("new_hash"))
                if self.db.update_book(bid, **upd):
                    updated_meta += 1
                    try:
                        logger.info("clean_update_meta book_id=%s path=%s", bid, fp)
                    except Exception:
                        pass

            added = 0
            now_s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            reserved = set()
            for item in relink_records:
                try:
                    reserved.add(str(item.get("new") or ""))
                except Exception:
                    pass
            for p in list(db_by_file.keys()):
                try:
                    if p and os.path.exists(p):
                        reserved.add(str(p))
                except Exception:
                    pass
            for item in missing_db_records:
                fp = str(item["path"])
                if fp in reserved:
                    continue
                last_fp = fp
                meta = eng.parse_metadata_from_filename(fp) or {}
                title = (meta.get("title") or os.path.splitext(os.path.basename(fp))[0]).strip()
                author = (meta.get("author") or "").strip()
                series = (meta.get("series") or "").strip()
                if not author or author == "佚名":
                    a2, s2 = infer_from_library_path(fp)
                    if (not author) or author == "佚名":
                        author = a2
                    if not series:
                        series = s2
                if not author:
                    author = "佚名"
                if not title:
                    title = "未命名"
                ext2 = os.path.splitext(fp)[1].lower().lstrip(".")
                fh2 = file_hash(fp)
                self.db.add_book(title, author, "", 0, series, fp, ext2, file_hash=fh2, import_date=now_s)
                added += 1
                try:
                    logger.info("clean_add_missing file=%s title=%s author=%s", fp, title, author)
                except Exception:
                    pass

            conn.commit()
            print(Colors.green(f"\n修复完成喵！删除多余记录: {del_orphan}，合并重复: {del_dup}，纠正路径: {relinked}，补录: {added}，更新元数据: {updated_meta}"))

        except KeyboardInterrupt:
            try:
                conn.rollback()
            except Exception:
                pass
            print(Colors.red("\n操作被中断喵，已回滚本次更改。"))
            if last_fp:
                print(Colors.cyan(f"可用 --resume-from={shlex.quote(last_fp)} 继续喵"))
            try:
                logger.info("clean_interrupted last=%s", last_fp)
            except Exception:
                pass
            return
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(Colors.red(f"\n修复失败，已回滚喵: {e}"))
            try:
                logger.info("clean_failed error=%s", str(e))
            except Exception:
                pass
            return

        finally:
            try:
                self.db._suspend_commit = False
            except Exception:
                pass

        print(Colors.cyan("\n开始复检喵..."))
        try:
            verify_tokens = [x for x in tokens if x not in {"--fix", "--apply", "--repair"}]
            verify_tokens.append("--dry-run")
            verify_arg = " ".join(shlex.quote(x) for x in verify_tokens)
            self.do_clean(verify_arg, silent=False)
        except Exception:
            pass

    def do_clean_legacy(self, arg="", silent=False):
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

                def merge_dir_content(src, dst):
                    import shutil
                    import time

                    if not os.path.exists(dst):
                        os.makedirs(dst)

                    for item in os.listdir(src):
                        s = os.path.join(src, item)
                        d = os.path.join(dst, item)

                        if os.path.isdir(s):
                            if os.path.exists(d) and os.path.isdir(d):
                                merge_dir_content(s, d)
                                try:
                                    os.rmdir(s)
                                except Exception:
                                    pass
                            elif os.path.exists(d):
                                ts = int(time.time() * 1000)
                                d_new = f"{d}_{ts}"
                                shutil.move(s, d_new)
                                try:
                                    s_prefix = s + os.sep
                                    d_prefix = d_new + os.sep
                                    self.db.conn.execute(
                                        "UPDATE books SET file_path = REPLACE(file_path, ?, ?) WHERE file_path LIKE ?",
                                        (s_prefix, d_prefix, s_prefix + "%"),
                                    )
                                except Exception:
                                    pass
                            else:
                                shutil.move(s, d)
                        else:
                            final_dst = d
                            if os.path.exists(d):
                                base, ext = os.path.splitext(item)
                                ts = int(time.time() * 1000)
                                final_dst = os.path.join(dst, f"{base}_{ts}{ext}")
                                shutil.move(s, final_dst)
                                try:
                                    self.db.conn.execute(
                                        "UPDATE books SET file_path = ? WHERE file_path = ?",
                                        (final_dst, s),
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
            all_books = sorted(self.db.list_books(), key=lambda x: x['id'])

            if not all_books:
                print(Colors.yellow("书架是空的，无需优化喵。"))
                return

            count = len(all_books)
            print(Colors.green(f"找到 {count} 本书，准备重排 ID..."))

            cursor = self.db.conn.cursor()
            cursor.execute("BEGIN TRANSACTION")

            try:
                books_data = []
                for b in all_books:
                    books_data.append(
                        {
                            'title': b['title'],
                            'author': b['author'],
                            'tags': b['tags'],
                            'status': b['status'],
                            'series': b['series'],
                            'file_path': b['file_path'],
                            'file_hash': b['file_hash'],
                            'file_type': b['file_type'],
                            'created_at': b['created_at'],
                        }
                    )

                cursor.execute("DELETE FROM books")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='books'")

                insert_sql = '''
                    INSERT INTO books (title, author, tags, status, series, file_path, file_hash, file_type, created_at)
                    VALUES (:title, :author, :tags, :status, :series, :file_path, :file_hash, :file_type, :created_at)
                '''
                cursor.executemany(insert_sql, books_data)

                self.db.conn.commit()
                print(Colors.green("ID 重排完成喵！"))

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
        opts = [
            "--dry-run",
            "--fix",
            "--apply",
            "--yes",
            "--dir=",
            "--type=",
            "--ext=",
            "--since=",
            "--until=",
            "--resume-from=",
        ]
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


__all__ = ["SystemCommandsMixin"]
