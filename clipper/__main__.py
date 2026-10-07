"""Start Clipper: python -m clipper [--port 8765] [--no-browser]"""
import argparse
import atexit
import os
import signal
import socket
import sys
import threading
import time
import webbrowser

import httpx
import uvicorn

from . import db, scheduler, settings

PID_FILE = db.DATA_DIR / "clipper.pid"


def _port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name != "nt":  # match uvicorn, so a just-closed port isn't reported busy
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _clipper_answers(port):
    try:
        return "llm_provider" in httpx.get(f"http://127.0.0.1:{port}/api/settings", timeout=2).json()
    except Exception:  # noqa: BLE001
        return False


def _old_pids():
    """Processes started as `python -m clipper`: the pid file, plus a /proc scan for copies that predate it."""
    pids = set()
    try:
        pids.add(int(PID_FILE.read_text().strip()))
    except (OSError, ValueError):
        pass
    proc = "/proc"
    if os.path.isdir(proc):
        for entry in os.listdir(proc):
            if entry.isdigit() and int(entry) != os.getpid():
                try:
                    with open(f"{proc}/{entry}/cmdline", "rb") as f:
                        args = f.read().split(b"\0")
                except OSError:
                    continue
                if b"-m" in args and b"clipper" in args:
                    pids.add(int(entry))
    pids.discard(os.getpid())
    return pids


def _free_port(port):
    """If an older Clipper is still running on this port, stop it so the new code takes over."""
    if _port_free(port):
        return
    if not _clipper_answers(port):
        sys.exit(f"Port {port} is in use by another program. Start Clipper on a different port, e.g.  ./run.sh --port {port + 1}")
    pids = _old_pids()
    if not pids:
        sys.exit(f"An older Clipper is already running at http://127.0.0.1:{port} but its process can't be found.\n"
                 "Close the other window running it and try again.")
    print("Stopping the Clipper that was already running…", flush=True)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(60):
        if _port_free(port):
            return
        time.sleep(0.25)
    sys.exit("Couldn't stop the old Clipper. Close the window running it and try again.")


def _remove_pid_file():
    try:
        if PID_FILE.read_text().strip() == str(os.getpid()):
            PID_FILE.unlink()
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(prog="clipper")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="don't open the dashboard on start")
    args = ap.parse_args()

    db.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _free_port(args.port)
    PID_FILE.write_text(str(os.getpid()))
    atexit.register(_remove_pid_file)

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
