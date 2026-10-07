"""Start Clipper: python -m clipper [--port 8765] [--no-browser]"""
import argparse
import threading
import webbrowser

import uvicorn

from . import db, scheduler, settings


def main():
    ap = argparse.ArgumentParser(prog="clipper")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="don't open the dashboard on start")
    args = ap.parse_args()

    db.init()
    settings.seed()
    scheduler.start()
    url = f"http://127.0.0.1:{args.port}"
    print(f"Clipper is running at {url}  (Ctrl+C to stop)", flush=True)
    if settings.get("open_browser_on_start") and not args.no_browser:
        threading.Timer(1.5, webbrowser.open, (url,)).start()
    from .server import app
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
