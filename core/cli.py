import cmd
import os
import re

try:
    import readline  # noqa: F401
except Exception:
    readline = None

from .database import DatabaseManager
from .file_manager import FileManager
from .utils import Colors
from .config import DB_FILE, LIBRARY_DIR, VERSION
from .cli_commands_library import LibraryCommandsMixin
from .cli_commands_query import QueryCommandsMixin
from .cli_commands_manage import ManageCommandsMixin
from .cli_commands_system import SystemCommandsMixin


class MoeCLI(
    LibraryCommandsMixin,
    QueryCommandsMixin,
    ManageCommandsMixin,
    SystemCommandsMixin,
    cmd.Cmd,
):
    intro = ""
    prompt = f'{Colors.HEADER}(萌萌){Colors.RESET} {Colors.CYAN}>{Colors.RESET} '

    def _history_file(self):
        try:
            v = os.environ.get("MOE_CLI_HISTORY_FILE")
        except Exception:
            v = None
        v = (v or "").strip()
        if v:
            try:
                return os.path.expanduser(os.path.expandvars(v))
            except Exception:
                return v
        return os.path.join(os.path.expanduser("~"), ".moe_cli_history")

    def _load_history(self):
        if readline is None:
            return

        fp = self._history_file()
        try:
            readline.read_history_file(fp)
        except FileNotFoundError:
            pass
        except Exception:
            pass

        try:
            readline.set_history_length(10000)
        except Exception:
            pass

    def _save_history(self):
        if readline is None:
            return

        fp = self._history_file()
        try:
            parent = os.path.dirname(fp)
            if parent:
                os.makedirs(parent, exist_ok=True)
        except Exception:
            pass

        try:
            readline.write_history_file(fp)
        except Exception:
            pass

    def _readline_safe_prompt(self, s):
        if readline is None:
            return s

        start = "\001"
        end = "\002"
        try:
            return re.sub(r"\x1b\[[0-9;]*m", lambda m: start + m.group(0) + end, s)
        except Exception:
            return s

    def _build_intro(self):
        lib_abs = str(os.path.abspath(str(LIBRARY_DIR)))
        db_abs = str(os.path.abspath(str(DB_FILE)))
        hist_abs = self._history_file()

        stats = None
        try:
            stats = self.db.get_stats()
        except Exception:
            stats = None

        total = 0
        types_line = ""
        top_authors = []
        top_series = []

        if isinstance(stats, dict):
            try:
                total = int(stats.get("total") or 0)
            except Exception:
                total = 0

            try:
                t = stats.get("types") or {}
                pairs = []
                for k, v in (t.items() if hasattr(t, "items") else []):
                    try:
                        pairs.append((str(k), int(v)))
                    except Exception:
                        pairs.append((str(k), 0))
                pairs.sort(key=lambda x: x[1], reverse=True)
                if pairs:
                    types_line = "  ".join([f"{k}:{Colors.green(str(v))}" for k, v in pairs[:6]])
            except Exception:
                types_line = ""

            try:
                top_authors = list(stats.get("authors") or [])
            except Exception:
                top_authors = []

            try:
                top_series = list(stats.get("series") or [])
            except Exception:
                top_series = []

        recent = []
        try:
            recent = list(self.db.list_books() or [])[:5]
        except Exception:
            recent = []

        lines = []
        lines.append(f"{Colors.HEADER}{Colors.BOLD}╔══════════════════════════════════════════════════════╗{Colors.RESET}")
        lines.append(f"{Colors.HEADER}{Colors.BOLD}║{Colors.RESET}   /\\_/\\    {Colors.BOLD}萌萌的本地化漫画小说自动管理系统 v{VERSION}{Colors.RESET}     {Colors.HEADER}{Colors.BOLD}║{Colors.RESET}")
        lines.append(f"{Colors.HEADER}{Colors.BOLD}║{Colors.RESET}  ( o.o )    {Colors.CYAN}help {Colors.RESET} 查看命令   {Colors.CYAN}exit{Colors.RESET} 退出               {Colors.HEADER}{Colors.BOLD}║{Colors.RESET}")
        lines.append(f"{Colors.HEADER}{Colors.BOLD}║{Colors.RESET}   > ^ <     {Colors.YELLOW}本地书库{Colors.RESET}: {Colors.green(str(total))} 本                         {Colors.HEADER}{Colors.BOLD}║{Colors.RESET}")
        lines.append(f"{Colors.HEADER}{Colors.BOLD}╚══════════════════════════════════════════════════════╝{Colors.RESET}")
        lines.append("")

        lines.append(f"{Colors.CYAN}{Colors.BOLD}📦 路径信息{Colors.RESET}")
        lines.append(f"  - 藏书目录: {Colors.green(lib_abs)}")
        lines.append(f"  - 数据库:   {Colors.green(db_abs)}")
        if readline is not None:
            lines.append(f"  - 历史文件: {Colors.green(hist_abs)}")
        lines.append("")

        lines.append(f"{Colors.CYAN}{Colors.BOLD}🧭 命令导航{Colors.RESET}")
        lines.append(f"  {Colors.BLUE}{Colors.BOLD}【导入】{Colors.RESET}  {Colors.GREEN}import{Colors.RESET}  ·  {Colors.GREEN}download{Colors.RESET}")
        lines.append(f"  {Colors.BLUE}{Colors.BOLD}【查询】{Colors.RESET}  {Colors.GREEN}list{Colors.RESET}   ·  {Colors.GREEN}search{Colors.RESET}   ·  {Colors.GREEN}stats{Colors.RESET}")
        lines.append(f"  {Colors.BLUE}{Colors.BOLD}【管理】{Colors.RESET}  {Colors.GREEN}update{Colors.RESET}  ·  {Colors.GREEN}delete{Colors.RESET}  ·  {Colors.GREEN}export{Colors.RESET}")
        lines.append(f"  {Colors.BLUE}{Colors.BOLD}【维护】{Colors.RESET}  {Colors.GREEN}clean{Colors.RESET}   ·  {Colors.GREEN}clear{Colors.RESET}   ·  {Colors.GREEN}exit{Colors.RESET}")
        lines.append("")

        lines.append(f"{Colors.CYAN}{Colors.BOLD}🚀 常用命令（两列）{Colors.RESET}")
        pairs = [
            ("import", "<路径/文件夹>", "导入并归档"),
            ("search", "<关键字/过滤器>", "搜索（author:/series:/tag:）"),
            ("download", "<URL>", "下载并自动归档"),
            ("update", "<选择器> 字段=值", "批量修改信息"),
            ("list", "", "列出书架"),
            ("delete", "<选择器>", "删除记录/文件"),
            ("export", "<选择器>", "导出/打包"),
            ("clean", "[--sync]", "清理并可同步"),
        ]

        def cell(cmd, args, desc):
            cmd2 = f"{cmd:<8}"
            args2 = f"{args:<16}"
            return f"{Colors.GREEN}{cmd2}{Colors.RESET} {Colors.YELLOW}{args2}{Colors.RESET} {desc}"

        for i in range(0, len(pairs), 2):
            left = cell(*pairs[i])
            right = cell(*pairs[i + 1]) if i + 1 < len(pairs) else ""
            lines.append(f"  {left}    {right}".rstrip())
        lines.append("")

        lines.append(f"{Colors.CYAN}{Colors.BOLD}🧪 示例{Colors.RESET}")
        lines.append(f"  {Colors.YELLOW}import{Colors.RESET} \"/path/to/book.txt\"")
        lines.append(f"  {Colors.YELLOW}search{Colors.RESET} author:佚名 status:1")
        lines.append(f"  {Colors.YELLOW}update{Colors.RESET} series:激烈变身 tags+='#变身 #换身' --dry-run")
        lines.append("")

        if recent:
            lines.append(f"{Colors.CYAN}{Colors.BOLD}📌 最近新增（5）{Colors.RESET}")
            for b in recent[:5]:
                try:
                    bid = str(b["id"])
                except Exception:
                    bid = "?"
                try:
                    title = str(b["title"] or "")
                except Exception:
                    title = ""
                try:
                    author = str(b["author"] or "")
                except Exception:
                    author = ""
                try:
                    st = int(b["status"] or 0)
                except Exception:
                    st = 0
                st_s = Colors.green("完结") if st == 1 else Colors.pink("连载")
                lines.append(f"  [{Colors.yellow(bid)}] {Colors.BOLD}{title}{Colors.RESET} - {Colors.green(author)} ({st_s})")
            lines.append("")

        if types_line:
            lines.append(f"{Colors.CYAN}{Colors.BOLD}📊 格式分布{Colors.RESET}")
            lines.append(f"  {types_line}")
            lines.append("")

        if top_authors:
            lines.append(f"{Colors.CYAN}{Colors.BOLD}✍️ 热门作者（Top5）{Colors.RESET}")
            for a, c in top_authors[:5]:
                lines.append(f"  - {a}: {Colors.green(str(c))} 本")
            lines.append("")

        if top_series:
            lines.append(f"{Colors.CYAN}{Colors.BOLD}📚 热门系列（Top5）{Colors.RESET}")
            for s, c in top_series[:5]:
                if s is None or str(s).strip() == "":
                    continue
                lines.append(f"  - {s}: {Colors.green(str(c))} 本")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def __init__(self):
        super().__init__()
        self.db = DatabaseManager(DB_FILE)
        self.fm = FileManager(LIBRARY_DIR)
        self.intro = self._build_intro()
        self.prompt = self._readline_safe_prompt(self.prompt)

    def preloop(self):
        self._load_history()
        return super().preloop()

    def postloop(self):
        try:
            return super().postloop()
        finally:
            self._save_history()
