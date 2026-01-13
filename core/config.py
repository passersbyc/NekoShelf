"""NekoShelf 配置

本文件既是“配置项声明”，也是“配置加载入口”。

路径配置
- LIBRARY_PATH: 书库存储路径（默认: library）。支持绝对路径/相对路径。
  * 相对路径以当前工作目录为基准（一般是运行 main.py 的目录）。
- DB_PATH: SQLite 数据库路径（默认: library.db）。支持绝对路径/相对路径。

Cookie 配置（敏感信息）
- 推荐通过环境变量配置：
  * NEKOSHELF_PIXIV_COOKIE
  * NEKOSHELF_KEMONO_COOKIE
- Cookie 值既可以是明文，也可以是加密字符串（前缀 enc:）。
  * 若使用 enc:，解密密钥通过环境变量 NEKOSHELF_SECRET_KEY 提供，不写入仓库。

加密/解密说明
- 需要安装依赖 cryptography（已在 pyproject.toml 中声明）。
- 生成加密串示例（在项目根目录执行）：
  python3 -c "from core.config import encrypt_secret; print(encrypt_secret('YOUR_COOKIE'))"
  然后把输出粘贴到环境变量 NEKOSHELF_PIXIV_COOKIE / NEKOSHELF_KEMONO_COOKIE（带 enc: 前缀）里。
"""

import base64
import hashlib
import importlib
import os
import sys
from typing import Any, Dict


VERSION = "1.1"


LIBRARY_PATH = os.environ.get("NEKOSHELF_LIBRARY_PATH", "library")
DB_PATH = os.environ.get("NEKOSHELF_DB_PATH", "library.db")


PIXIV_COOKIE = os.environ.get("NEKOSHELF_PIXIV_COOKIE", "")
KEMONO_COOKIE = os.environ.get("NEKOSHELF_KEMONO_COOKIE", "")


def _resolve_path(p: str) -> str:
    s = "" if p is None else str(p).strip()
    if not s:
        return ""
    try:
        s = os.path.expanduser(os.path.expandvars(s))
    except Exception:
        pass
    if not os.path.isabs(s):
        try:
            s = os.path.join(os.getcwd(), s)
        except Exception:
            pass
    try:
        return os.path.normpath(os.path.abspath(s))
    except Exception:
        return s


def _get_secret_key() -> str:
    try:
        return str(os.environ.get("NEKOSHELF_SECRET_KEY", "") or "")
    except Exception:
        return ""


def _fernet(secret_key: str):
    try:
        mod = importlib.import_module("cryptography.fernet")
        Fernet = getattr(mod, "Fernet")
    except Exception as e:
        raise RuntimeError("缺少依赖 cryptography，无法解密 enc: 配置") from e

    if not secret_key:
        raise RuntimeError("NEKOSHELF_SECRET_KEY 为空，无法解密 enc: 配置")

    key_bytes = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_secret(plaintext: str) -> str:
    s = "" if plaintext is None else str(plaintext)
    if not s:
        return ""
    f = _fernet(_get_secret_key())
    token = f.encrypt(s.encode("utf-8")).decode("utf-8")
    return "enc:" + token


def decrypt_secret(value: str) -> str:
    s = "" if value is None else str(value)
    s = s.strip()
    if not s:
        return ""
    if not s.startswith("enc:"):
        return s

    token = s[len("enc:") :].strip()
    f = _fernet(_get_secret_key())
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception as e:
        raise RuntimeError("Cookie 解密失败：请检查 NEKOSHELF_SECRET_KEY 与 enc: 内容") from e


def load(reload: bool = False) -> Dict[str, Any]:
    mod = sys.modules.get(__name__)
    if reload and mod is not None:
        mod = importlib.reload(mod)

    library_dir = _resolve_path(getattr(mod, "LIBRARY_PATH", "library"))
    db_file = _resolve_path(getattr(mod, "DB_PATH", "library.db"))

    if not library_dir:
        raise ValueError("LIBRARY_PATH 不能为空")
    if not db_file:
        raise ValueError("DB_PATH 不能为空")

    pixiv_cookie_raw = getattr(mod, "PIXIV_COOKIE", "")
    kemono_cookie_raw = getattr(mod, "KEMONO_COOKIE", "")

    download_cfg = dict(getattr(mod, "DOWNLOAD_CONFIG", {}) or {})
    download_cfg["pixiv_cookie"] = decrypt_secret(pixiv_cookie_raw)
    download_cfg["kemono_cookie"] = decrypt_secret(kemono_cookie_raw)

    return {
        "version": getattr(mod, "VERSION", ""),
        "library_dir": library_dir,
        "db_file": db_file,
        "import_config": dict(getattr(mod, "IMPORT_CONFIG", {}) or {}),
        "download_config": download_cfg,
        "update_config": dict(getattr(mod, "UPDATE_CONFIG", {}) or {}),
    }


def get_paths(reload: bool = False) -> tuple[str, str]:
    cfg = load(reload=reload)
    return str(cfg["library_dir"]), str(cfg["db_file"])


def get_download_config(reload: bool = False) -> Dict[str, Any]:
    return dict(load(reload=reload)["download_config"])


LIBRARY_DIR = _resolve_path(LIBRARY_PATH)
DB_FILE = _resolve_path(DB_PATH)

# 导入(import)行为配置：平时只要粘贴路径即可，默认行为由这里统一管理
# 可选值说明：
# - delete_mode: keep/ask/always
# - dup_mode: ask/skip/import
# - parent_as_series_mode: ask/always/never
IMPORT_CONFIG = {
    "recursive": False,  # 导入文件夹时是否递归扫描子目录
    "dry_run": False,  # 是否仅预览(不落库、不搬运、不删除)
    "delete_mode": "ask",  # 导入后是否删除源文件：keep/ask/always
    "dup_mode": "skip",  # 遇到重复记录时如何处理：ask/skip/import
    "parent_as_series_mode": "ask",  # 导入文件夹时文件夹名作为系列名：ask/always/never
    "naming_rules": {
        "title_fullwidth_to_halfwidth": True,
        "title_collapse_spaces": True,
        "title_keep_chars": "-_",
        "filename_pattern": "{title}",
    },
    "defaults": {
        "title": "",  # 默认标题(一般留空，让程序从文件名解析)
        "author": "",  # 默认作者(留空则从文件名/目录/文本头推断，缺失时为“佚名”)
        "tags": "",  # 默认标签(逗号分隔)
        "status": None,  # 默认状态：None=自动识别，0=连载中，1=已完结
        "series": "",  # 默认系列名(留空则自动推断/按 parent_as_series_mode 决定)
    },
}

# 爬虫配置
DOWNLOAD_CONFIG = {
    # 全局下载配置
    "max_retries": 3,
    "timeout": 10,
    "max_workers": 5,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    
    # Pixiv 专属配置
    "pixiv_format": "pdf", # 漫画/插画下载格式: pdf (默认) 或 cbz
    "pixiv_cookie": "", # Pixiv Cookie (由环境变量 NEKOSHELF_PIXIV_COOKIE 解密后注入)

    # Kemono 专属配置
    "kemono_base_url": "https://kemono.cr", # Kemono 镜像站地址
    "kemono_api_base": "https://kemono.cr/api/v1", # Kemono API 地址
    "kemono_cookie": "", # Kemono Cookie (由环境变量 NEKOSHELF_KEMONO_COOKIE 解密后注入)
    "kemono_format": "pdf", # 漫画/插画下载格式: pdf (默认) 或 cbz
    "kemono_save_content": False, # 是否在下载附件的同时保存帖子正文内容 (默认 False)
}


UPDATE_CONFIG = {
    # update 命令行为配置：让命令行更简洁，把默认行为放这里统一管理
    # allowed_fields: 允许被 update 修改的字段
    "allowed_fields": ["title", "author", "series", "tags", "status"],
    # default_dry_run_show: --dry-run 时默认展示多少条（太大会刷屏）
    "default_dry_run_show": 50,
    # default_dry_run_diff: --dry-run 时是否默认显示字段变更详情
    "default_dry_run_diff": False,
    # default_bulk_limit: 批量更新的默认上限（None 表示不限制；可配 20 之类做安全阀）
    "default_bulk_limit": None,
    # enable_text_ops: 是否开启 title/author/series 的 += / -= 字符串追加/删除子串
    "enable_text_ops": True,
}
