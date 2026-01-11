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

# 爬虫配置
DOWNLOAD_CONFIG = {
    "pixiv_cookie": "first_visit_datetime_pc=2025-04-27%2020%3A14%3A32; p_ab_id=6; p_ab_id_2=4; p_ab_d_id=44120228; yuid_b=IUV3Ypk; privacy_policy_agreement=7; privacy_policy_notification=0; a_type=0; b_type=0; PHPSESSID=105466527_IZXWYkdmtue5ONigEt9t7ZdJ2yEQORG8; c_type=27; login_ever=yes; _ga=GA1.1.260133522.1746558510; _gcl_au=1.1.1159793158.1764791367; _ga_MZ1NL4PHH0=GS2.1.s1766257575$o4$g1$t1766257593$j42$l0$h0; mybestpixiv_active_user=1; _cfuvid=SgBruAFnXkMMvdwkZzk3pVRGMeTGZyatUY1582IMNL8-1767980980824-0.0.1.1-604800000; __cf_bm=DTggwsebJA2lmJohbfOCg4yStBCL85FBXB8OzGcNttU-1768119416-1.0.1.1-axlCD1zwl34uV2kkktguSKFNDchmekdDVZqCppxfpJTPX4G49p56UklAnWqlTfIdJAko1S5ff.LRAJvhNhKdBfCM3.hd76lw3IReqvgjSfHEY5c9xHRrRt07GOht638u; cf_clearance=KDU__tvIS3aDo7FrgDdLhsbCDaj45cS5jUCYDizSLas-1768121057-1.2.1.1-UV6bd8pdcQgh9Do2V6CS1.S45W.rAJOJLXo.u4CDsKB7KtSk.nHtEoBYDoskpeyxy0p0r2.JEI4qjTycYoR5_zYbn1GeMWwSiw5UmWQQtDFFsubMV8O5PRXJE2zOzEHHq4lOF8g4pmgt0Lyq9ZLGm_3xFNCPOxgNx6t3rAjBnzfQ4JgQG731kILhXTPKmeCtx8C1_NBsHI1X.Dp2bThZXclDmqa3cT0.cP_pesXwVDk; _ga_75BBYNYN9J=GS2.1.s1768118403$o264$g1$t1768121119$j59$l0$h0", # Pixiv Cookie
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
