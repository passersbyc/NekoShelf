import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .database import DatabaseManager
from .file_manager import FileManager
from .download_service import DownloadImportService


def run_server(host: str = "127.0.0.1", port: int = 8765, db_path: str = "", library_dir: str = ""):
    cfg = config.load(reload=True)
    db = DatabaseManager(db_path or cfg["db_file"])
    fm = FileManager(library_dir or cfg["library_dir"])
    svc = DownloadImportService(db, fm)

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, code: int, payload):
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path.rstrip("/") == "" or self.path.rstrip("/") == "/health":
                return self._send_json(200, {"ok": True})
            return self._send_json(404, {"ok": False, "error": "not_found"})

        def do_POST(self):
            if self.path.rstrip("/") != "/download":
                return self._send_json(404, {"ok": False, "error": "not_found"})

            length = 0
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except Exception:
                length = 0

            try:
                body = self.rfile.read(length) if length > 0 else b"{}"
                data = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                return self._send_json(400, {"ok": False, "error": "invalid_json"})

            url = (data.get("url") or "").strip()
            if not url:
                return self._send_json(400, {"ok": False, "error": "missing_url"})

            out = svc.download_and_import(
                url=url,
                download_dir=data.get("download_dir"),
                series_name=data.get("series_name"),
                save_content=bool(data.get("save_content", False)),
                kemono_dl_mode=str(data.get("kemono_dl_mode") or "attachment"),
                dry_run=bool(data.get("dry_run", False)),
                dup_mode=str(data.get("dup_mode") or "skip"),
            )
            return self._send_json(200, {"ok": True, "result": out})

        def log_message(self, format, *args):
            return

    httpd = ThreadingHTTPServer((host, int(port)), Handler)
    try:
        httpd.serve_forever()
    finally:
        try:
            db.close()
        except Exception:
            pass
