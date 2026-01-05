from .config import IMPORT_CONFIG
from .import_engine import ImportEngine


class ImportCommandsMixin:
    _IMPORT_EXTS = {".txt", ".pdf", ".doc", ".docx", ".epub"}

    def _engine(self):
        eng = getattr(self, "_import_engine", None)
        if eng is None:
            eng = ImportEngine(
                self.db,
                self.fm,
                import_exts=self._IMPORT_EXTS,
                import_config=IMPORT_CONFIG,
            )
            setattr(self, "_import_engine", eng)
        else:
            try:
                eng.import_exts = set(self._IMPORT_EXTS)
            except Exception:
                pass
            eng.import_config = IMPORT_CONFIG
        return eng

    def _get_import_config(self):
        return self._engine().get_import_config()

    def _file_hash(self, file_path, algo="sha256"):
        return self._engine().file_hash(file_path, algo=algo)

    def _abs_norm(self, p):
        return self._engine().abs_norm(p)

    def _pick_duplicate_action(self, fp, dup_book, ask_choice=None):
        return self._engine().pick_duplicate_action(fp, dup_book, ask_choice=ask_choice)

    def _looks_like_part_suffix(self, suffix):
        return self._engine().looks_like_part_suffix(suffix)

    def _normalize_tags(self, tags):
        return self._engine().normalize_tags(tags)

    def _parse_status(self, raw, default=0):
        return self._engine().parse_status(raw, default=default)

    def _infer_status_from_text(self, text, default=None):
        return self._engine().infer_status_from_text(text, default=default)

    def _strip_trailing_brackets(self, title):
        return self._engine().strip_trailing_brackets(title)

    def _strip_trailing_id(self, title):
        return self._engine().strip_trailing_id(title)

    def _infer_series_from_titlepart(self, title_part):
        return self._engine().infer_series_from_titlepart(title_part)

    def _peek_text_head(self, file_path, max_chars=4096):
        return self._engine().peek_text_head(file_path, max_chars=max_chars)

    def _infer_author_tags_from_text(self, text):
        return self._engine().infer_author_tags_from_text(text)

    def _parse_title_series_from_titlepart(self, title_part):
        return self._engine().parse_title_series_from_titlepart(title_part)

    def _parse_metadata_from_filename(self, file_path):
        return self._engine().parse_metadata_from_filename(file_path)

    def _import_one(self, file_path, overrides=None, dry_run=False, dup_mode="ask", dup_choice=None, hash_cache=None):
        return self._engine().import_one(
            file_path,
            overrides=overrides,
            dry_run=dry_run,
            dup_mode=dup_mode,
            dup_choice=dup_choice,
            hash_cache=hash_cache,
        )

    def _iter_import_files(self, path, recursive=False):
        yield from self._engine().iter_import_files(path, recursive=recursive)

    def _looks_like_flagged_invocation(self, raw):
        return self._engine().looks_like_flagged_invocation(raw)

    def _try_parse_as_single_path(self, raw):
        return self._engine().try_parse_as_single_path(raw)

    def _parse_import_tokens(self, tokens, defaults=None):
        return self._engine().parse_import_tokens(tokens, defaults=defaults)

    def _apply_legacy_positional_overrides(self, parsed):
        return self._engine().apply_legacy_positional_overrides(parsed)

    def _should_delete_source(self, delete_mode, ask_choice):
        return self._engine().should_delete_source(delete_mode, ask_choice)

    def _safe_delete_source(self, fp):
        return self._engine().safe_delete_source(fp)

    def do_import(self, arg):
        """导入文件: import <文件/文件夹路径>

        常用:
        1) 导入单文件: import /path/to/book.txt
        2) 导入文件夹: import /path/to/folder
        3) 路径含空格: import "/path/with space/folder"
        4) 也可直接粘贴路径(无需输入 import)

        模式:
        - 导入行为默认从 core/config.py 的 IMPORT_CONFIG 读取
        - 你可以在配置里统一设置: 递归/预览/删源文件/重复处理/父目录系列名/默认作者标签等

        IMPORT_CONFIG 常用项:
        - recursive: 是否递归扫描文件夹
        - dry_run: 是否仅预览(不落库、不搬运、不删除)
        - delete_mode: keep/ask/always (导入后是否删除源文件)
        - dup_mode: ask/skip/import (重复导入处理)
        - parent_as_series_mode: ask/always/never (导入文件夹时文件夹名是否作为系列名)
        - defaults: 默认元信息(可填 author/series/tags/status)

        扩展用法:
        - 仍兼容旧参数(可覆盖配置): --recursive/--dry-run/--delete-source/--ask-delete/--keep-source
        - 重复处理: --ask-dup/--skip-dup/--import-dup
        - 手动覆盖元信息: --title/--author/--tags/--status/--series

        注意:
        - 路径里有空格且还带 -- 参数时，请用引号包住路径喵~

        支持格式: txt/pdf/doc/docx/epub

        命名格式(自动解析优先级从上到下):
        1) 作品名_作者_标签_是否完结.ext
           例: 埃及探秘_佚名_女性化+ts_0.txt
        2) 作品名 卷号_作者_标签_是否完结.ext
           例: 战锤世界的ts堕落 1_佚名.docx
        3) 作者 - 作品名 (ID).ext
           例: エリナ - 关于我在四六级考试前一周的三天里，除了学习什么都干了这档事 (26888003).txt
        4) 任意文件名.ext
           - 作者缺失默认: 佚名
           - 标题中最后一个空格前的部分会自动归为系列名；空格后的“卷号/章节”(如 1, 堕01, v2, ep03, 上/下/番外/第二章) 会保留在作品名中
           - 标题末尾【已完结/全完结/连载中】等会自动识别状态并从标题中移除
           - txt 会尝试从文件开头识别: 作者: / 标签: / 状态关键词

        兼容旧写法:
        import /path/to/novel.txt "我的小说" "大神" "热血,冒险"
        """
        return self._engine().run(arg)
