from .config import IMPORT_CONFIG
from .import_engine import ImportEngine
from .utils import path_complete


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
        """导入文件: import <文件/文件夹路径> [选项]

        命名格式(自动解析优先级):
        1) 作品名_作者_标签_是否完结.ext
           例: 埃及探秘_佚名_女性化+ts_0.txt
        2) 作品名 卷号_作者_标签_是否完结.ext
           例: 战锤世界的ts堕落 1_佚名.docx
        3) 作者 - 作品名 (ID).ext
           例: エリナ - 学习 (26888003).txt
        4) 任意文件名.ext
           (自动识别系列/卷号/状态，默认作者: 佚名)

        选项:
        - --recursive     : 递归扫描文件夹
        - --dry-run       : 仅预览(不落库/不搬运/不删除)
        - --delete-source : 导入后删除源文件
        - --keep-source   : 导入后保留源文件
        - --skip-dup      : 跳过重复文件
        - --title="xxx"   : 强制指定标题
        - --author="xxx"  : 强制指定作者
        - --tags="a,b"    : 强制指定标签

        配置(core/config.py):
        - IMPORT_CONFIG 可设置默认行为: 递归/预览/删源/重复处理等

        注意:
        - 路径含空格请用引号包住喵！
        - 支持格式: txt/pdf/doc/docx/epub

        示例:
        1) import /path/to/book.txt
        2) import "/path/with space/" --recursive
        3) import . --dry-run
        4) /path/to/book.txt  (直接粘贴路径也可导入)
        """
        return self._engine().run(arg)

    def complete_import(self, text, line, begidx, endidx):
        return path_complete(text)
