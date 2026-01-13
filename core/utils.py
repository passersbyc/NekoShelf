import logging
import os
from logging.handlers import RotatingFileHandler

import functools


_LOGGER = None


def get_logger():
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    logger = logging.getLogger("neko")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        try:
            log_dir = os.path.join(os.getcwd(), "logs")
            os.makedirs(log_dir, exist_ok=True)
            fp = os.path.join(log_dir, "neko_shelf.log")
            h = RotatingFileHandler(fp, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
            h.setFormatter(fmt)
            logger.addHandler(h)
        except Exception:
            pass

    _LOGGER = logger
    return logger


class Colors:
    HEADER = '\033[95m' # Pink/Magenta
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    @staticmethod
    def pink(text): return f"{Colors.HEADER}{text}{Colors.RESET}"
    
    @staticmethod
    def blue(text): return f"{Colors.BLUE}{text}{Colors.RESET}"
    
    @staticmethod
    def cyan(text): return f"{Colors.CYAN}{text}{Colors.RESET}"
    
    @staticmethod
    def green(text): return f"{Colors.GREEN}{text}{Colors.RESET}"
    
    @staticmethod
    def yellow(text): return f"{Colors.YELLOW}{text}{Colors.RESET}"
    
    @staticmethod
    def red(text): return f"{Colors.RED}{text}{Colors.RESET}"

    @staticmethod
    def dim(text): return f"\033[2m{text}{Colors.RESET}"


def fullwidth_to_halfwidth(text: str) -> str:
    s = "" if text is None else str(text)
    if not s:
        return ""
    out = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
            continue
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
            continue
        out.append(ch)
    return "".join(out)


@functools.lru_cache(maxsize=4096)
def normalize_title(text: str, keep_chars: str = "-_", collapse_spaces: bool = True) -> str:
    s = fullwidth_to_halfwidth(text)
    s = s.strip()
    if not s:
        return ""

    keep = set(keep_chars or "")
    buf = []
    last_space = False
    for ch in s:
        code = ord(ch)
        if code < 32:
            continue
        if ch.isspace():
            if collapse_spaces:
                if last_space:
                    continue
                buf.append(" ")
                last_space = True
            else:
                buf.append(ch)
                last_space = False
            continue
        last_space = False
        if ch in keep or ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"):
            buf.append(ch)
            continue
        buf.append(ch)

    out = "".join(buf).strip()
    return out


def parse_id_ranges(token):
    """
    解析 ID 列表字符串，支持逗号分隔和连字符范围。
    例如: "1,2,3", "1-5", "1, 3-5"
    返回: list[int] (已去重)
    """
    ids = []
    parts = [p.strip() for p in str(token).split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            try:
                left, right = p.split("-", 1)
                left = left.strip()
                right = right.strip()
                if left.isdigit() and right.isdigit():
                    a = int(left)
                    b = int(right)
                    if a <= b:
                        ids.extend(range(a, b + 1))
                    else:
                        ids.extend(range(b, a + 1))
                    continue
            except Exception:
                pass
        
        if p.isdigit():
            ids.append(int(p))
            
    out = []
    seen = set()
    for x in ids:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def parse_status(v):
    """解析状态: 1/完结/done -> 1, 0/连载/ongoing -> 0"""
    s = "" if v is None else str(v).strip().lower()
    if s in {"1", "完结", "已完结", "end", "done", "completed"}:
        return 1
    if s in {"0", "连载", "连载中", "未完结", "ongoing"}:
        return 0
    try:
        return int(s)
    except Exception:
        return None


def parse_tags_to_list(raw):
    """解析标签字符串为列表，支持逗号、空格、#分隔"""
    if not raw:
        return []
    s = str(raw).replace("，", ",").replace("+", ",").replace("#", " ")
    parts = []
    for chunk in s.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts.extend([p.strip() for p in chunk.split() if p.strip()])
    out = []
    seen = set()
    for p in parts:
        p2 = p.lstrip("#").strip()
        if not p2:
            continue
        if p2 in seen:
            continue
        seen.add(p2)
        out.append(p2)
    return out


def apply_common_filter(key, val, filters):
    """
    应用通用过滤器 (author, series, tags, status, type, ids, title).
    如果 key 是通用字段，更新 filters 并返回 True，否则返回 False。
    """
    if not key:
        return False
    k = str(key).strip().lower()
    v = "" if val is None else str(val)

    if k in ['author', 'series', 'title']:
        filters[k] = v
        return True
    elif k in ['tag', 'tags']:
        filters['tags'] = v
        return True
    elif k in ['id', 'ids']:
        ids = parse_id_ranges(v)
        if ids:
            cur = filters.get('ids', [])
            cur.extend(ids)
            filters['ids'] = list(set(cur))
        return True
    elif k == 'status':
        st = parse_status(v)
        if st is not None:
            filters['status'] = st
        return True
    elif k in ['type', 'format', 'ext', 'file_type']:
        filters['file_type'] = v.lstrip('.')
        return True
    return False


def parse_query_args(args, strict_id_mode=False):
    """
    解析命令行参数列表为查询字符串和过滤器字典。
    
    args: 参数列表 (list of strings)
    strict_id_mode: 
      - True (Delete/Update/Export): 只要能解析出 ID，就视为 ID 过滤器。
      - False (Search/List): 只有包含 ',' 或 '-' 的才视为 ID 范围，单个数字视为关键词。
      
    返回: (query_string, filters_dict)
    """
    query_parts = []
    filters = {}
    
    for item in args:
        key = None
        val = None
        
        # 尝试解析 key:val 或 key=val
        # 注意: update 命令可能会用到 +=, -=, 这些不由这里处理，这里只处理查询/选择器
        if ":" in item:
            key, val = item.split(":", 1)
        elif "=" in item and "+=" not in item and "-=" not in item:
            key, val = item.split("=", 1)
            
        if key:
            # 尝试应用通用过滤器
            if not apply_common_filter(key, val, filters):
                # 未知 key，视为查询关键词的一部分 (或者这里应该报错？Search通常宽松处理)
                query_parts.append(item)
        else:
            # 尝试解析为隐式 ID
            ids = parse_id_ranges(item)
            is_id_filter = False
            
            if ids:
                if strict_id_mode:
                    is_id_filter = True
                else:
                    # Loose mode: 只有看起来像列表/范围的才算 ID 过滤器
                    if ',' in item or '-' in item:
                        is_id_filter = True
            
            if is_id_filter:
                cur = filters.get('ids', [])
                cur.extend(ids)
                filters['ids'] = list(set(cur))
            else:
                query_parts.append(item)
                
    query = " ".join(query_parts).strip() if query_parts else None
    return query, filters


def simple_complete(text, options):
    """简单的列表补全"""
    if not text:
        return options[:]
    return [s for s in options if s.startswith(text)]


def path_complete(text):
    """简单的文件路径补全"""
    import os
    import glob
    
    # 展开用户路径
    expanded = os.path.expanduser(text)
    
    # 如果以目录分隔符结尾，列出该目录下的内容
    if text.endswith(os.sep):
        search_dir = expanded
        prefix = text
        pattern = ""
    else:
        search_dir = os.path.dirname(expanded)
        prefix = os.path.dirname(text)
        if prefix:
            prefix += os.sep
        pattern = os.path.basename(expanded)
        
    if not search_dir:
        search_dir = "."
        
    if not os.path.isdir(search_dir):
        return []
        
    candidates = []
    try:
        for name in os.listdir(search_dir):
            if name.startswith(pattern):
                # 区分目录和文件
                full_path = os.path.join(search_dir, name)
                if os.path.isdir(full_path):
                    candidates.append(prefix + name + os.sep)
                else:
                    candidates.append(prefix + name + " ")
    except Exception:
        pass
        
    return candidates
