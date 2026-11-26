"""Windows-friendly desktop entry point for the Faire Scraper dashboard."""
import os
import sys
import threading
from pathlib import Path


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "scrape-worker":
        from . import cli
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        cli.main()
        return

    data_dir = Path(os.environ.get("FAIRE_DATA_DIR", Path.home() / "AppData" / "Local" / "FaireScraper"))
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("FAIRE_DATA_DIR", str(data_dir))
    os.environ.setdefault("FAIRE_PROFILE_DIR", str(data_dir / "faire_profile"))
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    os.environ.setdefault("FAIRE_FRONTEND_DIR", str(bundle_root / "frontend"))
    bundled_browsers = bundle_root / "ms-playwright"
    if bundled_browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(bundled_browsers))
    import webview
    from . import web
    server, port = web.build_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    webview.create_window("Faire Scraper", f"http://127.0.0.1:{port}", width=1440, height=940, min_size=(1000, 700))
    webview.start()
    server.shutdown()


if __name__ == "__main__":
    main()
