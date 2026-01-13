import datetime
import os
import tempfile
from typing import Optional

from .download_manager import DownloadManager
from .import_engine import ImportEngine
from .utils import get_logger


class DownloadImportService:
    def __init__(self, db, fm):
        self.db = db
        self.fm = fm
        self._engine = ImportEngine(
            db,
            fm,
            import_exts={".txt", ".pdf", ".doc", ".docx", ".epub", ".cbz", ".zip"},
        )
        self._downloader = DownloadManager()

    @property
    def manager(self):
        return self._downloader

    def download_and_import(
        self,
        url: str,
        download_dir: Optional[str] = None,
        series_name: Optional[str] = None,
        save_content: bool = False,
        kemono_dl_mode: str = "attachment",
        dry_run: bool = False,
        dup_mode: str = "skip",
        quiet: bool = False,
    ):
        download_dir = (download_dir or "").strip()
        created_temp = False
        if not download_dir:
            download_dir = tempfile.mkdtemp(prefix="neko_dl_")
            created_temp = True

        logger = get_logger()
        started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            logger.info("download_start url=%s download_dir=%s", url, download_dir)
        except Exception:
            pass
        dl = self._downloader.download_with_meta(
            url,
            download_dir,
            series_name=series_name,
            save_content=save_content,
            kemono_dl_mode=kemono_dl_mode,
            db=self.db, # 注入数据库实例
            quiet=quiet,
        )
        ok = bool(dl.get("success"))
        msg = str(dl.get("message") or "")
        output_path = dl.get("output_path")
        if not ok:
            try:
                logger.info("download_fail url=%s message=%s", url, msg)
            except Exception:
                pass
            if created_temp:
                try:
                    os.rmdir(download_dir)
                except Exception:
                    pass
            return {
                "success": False,
                "message": msg,
                "download_dir": download_dir,
                "output_path": output_path,
                "imported": 0,
                "skipped": 0,
                "started_at": started_at,
            }

        imported = 0
        skipped = 0
        errors = []
        hash_cache = {}
        dup_choice = None

        if output_path:
            batch = []
            batch_size = 50
            for fp in self._engine.iter_import_files(output_path, recursive=True):
                batch.append(fp)
                if len(batch) >= batch_size:
                    for one in batch:
                        try:
                            ok2, is_dup, dup_choice = self._engine.import_one(
                                one,
                                overrides={"download_date": started_at, "source_url": url},
                                dry_run=dry_run,
                                dup_mode=dup_mode,
                                dup_choice=dup_choice,
                                hash_cache=hash_cache,
                                quiet=quiet,
                            )
                            if ok2:
                                if is_dup:
                                    skipped += 1
                                else:
                                    imported += 1
                            else:
                                errors.append(one)
                        except Exception:
                            errors.append(one)
                    batch = []
            if batch:
                for one in batch:
                    try:
                        ok2, is_dup, dup_choice = self._engine.import_one(
                            one,
                            overrides={"download_date": started_at, "source_url": url},
                            dry_run=dry_run,
                            dup_mode=dup_mode,
                            dup_choice=dup_choice,
                            hash_cache=hash_cache,
                            quiet=quiet,
                        )
                        if ok2:
                            if is_dup:
                                skipped += 1
                            else:
                                imported += 1
                        else:
                            errors.append(one)
                    except Exception:
                        errors.append(one)

        try:
            logger.info("download_done url=%s imported=%s skipped=%s errors=%s", url, imported, skipped, len(errors))
        except Exception:
            pass

        if created_temp:
            try:
                for root, dirs, files in os.walk(download_dir, topdown=False):
                    for name in files:
                        try:
                            os.remove(os.path.join(root, name))
                        except Exception:
                            pass
                    for name in dirs:
                        try:
                            os.rmdir(os.path.join(root, name))
                        except Exception:
                            pass
                os.rmdir(download_dir)
            except Exception:
                pass

        return {
            "success": True,
            "message": msg,
            "download_dir": download_dir,
            "output_path": output_path,
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "started_at": started_at,
        }
