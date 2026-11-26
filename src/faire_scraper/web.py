"""Small local web dashboard for the Faire scraper."""
import json
import errno
import mimetypes
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .storage import Store
from .auth import AuthStore

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = Path(os.environ.get("FAIRE_FRONTEND_DIR", ROOT / "frontend"))
DATA_DIR = Path(os.environ.get("FAIRE_DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "faire.db"
PROFILE_PATH = Path(os.environ.get("FAIRE_PROFILE_DIR", DATA_DIR / "faire_profile"))
LOG_PATH = DATA_DIR / "scraper.log"
CONTROL_PATH = DATA_DIR / "scraper.control"
AUTH_PATH = DATA_DIR / "dashboard-auth.json"
AUTH = AuthStore(AUTH_PATH)
SCRAPE_PROCESS = None
PROCESS_LOCK = threading.Lock()


def snapshot() -> dict:
    store = Store(str(DB_PATH))
    try:
        stats = store.stats()
        process_running = SCRAPE_PROCESS is not None and SCRAPE_PROCESS.poll() is None
        process_exit = None if process_running or SCRAPE_PROCESS is None else SCRAPE_PROCESS.returncode
        last_error = ""
        if process_exit not in (None, 0) and LOG_PATH.exists():
            lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
            last_error = "\n".join(lines[-8:])
        return {
            "stats": {"done": stats.get("done", 0), "pending": stats.get("pending", 0), "failed": stats.get("failed", 0)},
            "queue": store.queue(),
            "products": store.results(store.latest_run_id()),
            "latest_run_id": store.latest_run_id(),
            "running": process_running,
            "paused": CONTROL_PATH.exists() and CONTROL_PATH.read_text(encoding="utf-8").strip() == "paused",
            "process_exit": process_exit,
            "last_error": last_error,
            "log": LOG_PATH.read_text(encoding="utf-8", errors="replace")[-6000:] if LOG_PATH.exists() else "",
        }
    finally:
        store.close()


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_json(self, payload, status=200, cookie=""):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def session_token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "faire_session":
                return value
        return None

    def authorized(self):
        if not AUTH.configured():
            self.send_json({"error": "dashboard setup required"}, 401)
            return False
        if not AUTH.valid_session(self.session_token()):
            self.send_json({"error": "authentication required"}, 401)
            return False
        return True

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/status":
            self.send_json({"configured": AUTH.configured(), "authenticated": AUTH.valid_session(self.session_token())})
            return
        if parsed.path == "/api/state":
            if not self.authorized():
                return
            self.send_json(snapshot())
            return
        if parsed.path == "/api/export":
            if not self.authorized():
                return
            store = Store(str(DB_PATH))
            try:
                export_format = parse_qs(parsed.query).get("format", ["csv"])[0]
                run_query = parse_qs(parsed.query).get("run", ["latest"])[0]
                run_id = "" if run_query == "all" else store.latest_run_id()
                if export_format == "jsonl":
                    suffix = "all" if not run_id else run_id
                    output = DATA_DIR / f"products-{suffix}.jsonl"
                    store.export_jsonl(str(output), run_id)
                    content_type = "application/jsonl"
                elif export_format == "xlsx":
                    suffix = "all" if not run_id else run_id
                    output = DATA_DIR / f"products-{suffix}.xlsx"
                    store.export_xlsx(str(output), run_id)
                    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                else:
                    suffix = "all" if not run_id else run_id
                    output = DATA_DIR / f"products-{suffix}.csv"
                    store.export_csv(str(output), run_id)
                    content_type = "text/csv"
                body = output.read_bytes()
            finally:
                store.close()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{output.name}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.serve_static(parsed.path)

    def serve_static(self, requested):
        relative = "index.html" if requested in ("", "/") else requested.lstrip("/")
        path = (FRONTEND / relative).resolve()
        if FRONTEND not in path.parents or not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):  # noqa: N802
        global SCRAPE_PROCESS
        if self.path == "/api/auth/setup":
            password = str(self.read_json().get("password", ""))
            if not AUTH.setup(password):
                self.send_json({"error": "Use a password with at least 10 characters"}, 400)
                return
            token = AUTH.create_session()
            self.send_json({"ok": True}, cookie=f"faire_session={token}; HttpOnly; SameSite=Strict; Path=/")
            return
        if self.path == "/api/auth/login":
            password = str(self.read_json().get("password", ""))
            if not AUTH.verify(password):
                self.send_json({"error": "Invalid password"}, 401)
                return
            token = AUTH.create_session()
            self.send_json({"ok": True}, cookie=f"faire_session={token}; HttpOnly; SameSite=Strict; Path=/")
            return
        if self.path == "/api/auth/logout":
            AUTH.sessions.discard(self.session_token())
            self.send_json({"ok": True}, cookie="faire_session=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/")
            return
        if not self.authorized():
            return
        if self.path == "/api/queue":
            payload = self.read_json()
            urls = [str(url).strip() for url in payload.get("urls", []) if str(url).strip()]
            store = Store(str(DB_PATH))
            try:
                added = store.add_urls(urls)
            finally:
                store.close()
            self.send_json({"added": added})
            return
        if self.path == "/api/scrape":
            payload = self.read_json()
            with PROCESS_LOCK:
                if SCRAPE_PROCESS and SCRAPE_PROCESS.poll() is None:
                    self.send_json({"error": "already running"}, 409)
                    return
                env = os.environ.copy()
                env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
                env["FAIRE_DATA_DIR"] = str(DATA_DIR)
                env["FAIRE_PROFILE_DIR"] = str(PROFILE_PATH)
                env["FAIRE_FRONTEND_DIR"] = str(FRONTEND)
                LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                log_file = LOG_PATH.open("a", encoding="utf-8")
                log_file.write("\n--- scraper run started ---\n")
                log_file.flush()
                CONTROL_PATH.unlink(missing_ok=True)
                # --profile and --db are global argparse options, so they must
                # appear before the scrape subcommand.
                command = ([sys.executable, "scrape-worker", "--profile", str(PROFILE_PATH), "--db", str(DB_PATH), "scrape"]
                           if getattr(sys, "frozen", False) else
                           [sys.executable, "-m", "faire_scraper", "--profile", str(PROFILE_PATH), "--db", str(DB_PATH), "scrape"])
                if payload.get("refresh"):
                    command.append("--refresh")
                SCRAPE_PROCESS = subprocess.Popen(
                    command, start_new_session=True,
                    cwd=ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT,
                )
                log_file.close()
            self.send_json({"started": True})
            return
        if self.path == "/api/control":
            action = self.read_json().get("action")
            with PROCESS_LOCK:
                process = SCRAPE_PROCESS
                if not process or process.poll() is not None:
                    self.send_json({"error": "no scrape is running"}, 409)
                    return
                if action == "pause":
                    CONTROL_PATH.write_text("paused", encoding="utf-8")
                elif action == "resume":
                    CONTROL_PATH.write_text("running", encoding="utf-8")
                elif action == "stop":
                    process.terminate()
                    CONTROL_PATH.unlink(missing_ok=True)
                else:
                    self.send_json({"error": "unknown action"}, 400)
                    return
            self.send_json({"ok": True, "action": action})
            return
        self.send_json({"error": "not found"}, 404)


def build_server():
    port = int(os.environ.get("FAIRE_PORT", "8765"))
    server = None
    for candidate in range(port, port + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), DashboardHandler)
            port = candidate
            break
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
    if server is None:
        raise OSError(f"No available dashboard port in range {port}-{port + 9}")
    return server, port


def main():
    server, port = build_server()
    print(f"Faire dashboard running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
