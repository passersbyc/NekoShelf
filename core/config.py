# 配置
VERSION = "1.1"
LIBRARY_DIR = "library"
DB_FILE = "library.db"

# 导入(import)行为配置：平时只要粘贴路径即可，默认行为由这里统一管理
# 可选值说明：
# - delete_mode: keep/ask/always
# - dup_mode: ask/skip/import
# - parent_as_series_mode: ask/always/never
IMPORT_CONFIG = {
    "recursive": False,  # 导入文件夹时是否递归扫描子目录
    "dry_run": False,  # 是否仅预览(不落库、不搬运、不删除)
    "delete_mode": "ask",  # 导入后是否删除源文件：keep/ask/always
    "dup_mode": "ask",  # 遇到重复记录时如何处理：ask/skip/import
    "parent_as_series_mode": "ask",  # 导入文件夹时文件夹名作为系列名：ask/always/never
    "defaults": {
        "title": "",  # 默认标题(一般留空，让程序从文件名解析)
        "author": "",  # 默认作者(留空则从文件名/目录/文本头推断，缺失时为“佚名”)
        "tags": "",  # 默认标签(逗号分隔)
        "status": None,  # 默认状态：None=自动识别，0=连载中，1=已完结
        "series": "",  # 默认系列名(留空则自动推断/按 parent_as_series_mode 决定)
    },
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
