"""Shared browser plumbing for the platform uploaders.

Each account gets its own persistent browser profile under data/browser_profiles/<profile>.
You sign in once yourself (in a normal browser window, not under automation); Playwright then
reuses that signed-in profile to post. Passwords are never stored by this app.
"""
import os
import platform as _platform
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .. import db

_locks = {}
_locks_guard = threading.Lock()


def lock_for(account):
    """One browser per profile at a time; different accounts can run in parallel."""
    with _locks_guard:
        return _locks.setdefault(account["profile"], threading.Lock())


class NotLoggedIn(RuntimeError):
    pass


class Unconfirmed(RuntimeError):
    """The post was submitted but success could not be verified. Never auto-retried, to avoid duplicates."""


def profile_dir(account):
    return db.PROFILES_DIR / account["profile"]


def _candidates(channel):
    sysname = _platform.system()
    if sysname == "Windows":
        roots = [os.environ.get("PROGRAMFILES", r"C:\Program Files"), os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                 os.environ.get("LOCALAPPDATA", "")]
        rel = {"chrome": r"Google\Chrome\Application\chrome.exe", "msedge": r"Microsoft\Edge\Application\msedge.exe"}.get(channel)
        return [str(Path(r) / rel) for r in roots if r and rel]
    if sysname == "Darwin":
        return {"chrome": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
                "msedge": ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]}.get(channel, [])
    names = {"chrome": ["google-chrome", "google-chrome-stable"], "msedge": ["microsoft-edge", "microsoft-edge-stable"]}.get(channel, [])
    return [shutil.which(n) for n in names if shutil.which(n)]


def browser_executable(settings):
    channel = settings["browser_channel"]
    for c in _candidates(channel):
        if c and Path(c).is_file():
            return c, channel
    # Fall back to Playwright's bundled Chromium.
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        return p.chromium.executable_path, "chromium"


# Playwright always starts Chrome with these, which decide how saved logins (cookies) are encrypted on disk.
# The sign-in window must match them exactly; otherwise on Linux the sign-in window encrypts cookies with the
# desktop keyring, Playwright can't read them, and the account looks signed out every time it opens.
LOGIN_ARGS = ["--password-store=basic", "--use-mock-keychain", "--no-first-run", "--no-default-browser-check", "--new-window"]


def open_login_window(settings, account, url):
    """Launches a plain (non-automated) browser on the platform's profile and waits until the user closes it."""
    exe, _ = browser_executable(settings)
    d = profile_dir(account)
    d.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([exe, *LOGIN_ARGS, f"--user-data-dir={d}", url],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # keep Chrome's log noise out of Clipper's terminal
    proc.wait(timeout=3600)


@contextmanager
def session(settings, account, headless=None):
    from playwright.sync_api import sync_playwright

    lock = lock_for(account)
    if not lock.acquire(timeout=3600):
        raise RuntimeError(f"{account['label']} browser is busy")
    try:
        exe, channel = browser_executable(settings)
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(profile_dir(account)),
                executable_path=exe if channel != "chromium" else None,
                headless=settings["headless"] if headless is None else headless,
                viewport={"width": 1366, "height": 900},
                ignore_default_args=["--enable-automation"],
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_default_timeout(30_000)
            try:
                yield page
            except Exception:
                try:
                    shot = db.SHOTS_DIR / f"{account['profile']}_{int(time.time())}.png"
                    page.screenshot(path=str(shot), full_page=True)
                    db.log("warn", account["platform"], f"{account['label']}: saved screenshot of the failure: screenshots/{shot.name}")
                except Exception:  # noqa: BLE001
                    pass
                raise
            finally:
                ctx.close()
    finally:
        lock.release()


# ---------- small helpers for brittle UIs ----------

def first_visible(page, selectors, timeout=15):
    """Returns the first locator among `selectors` that becomes visible, or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                if loc.is_visible():
                    return loc
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.4)
    return None


def click_if_visible(page, selectors, timeout=3):
    loc = first_visible(page, selectors, timeout)
    if loc:
        loc.click()
        return True
    return False


def replace_text(page, locator, text, delay=12):
    locator.click()
    page.keyboard.press("ControlOrMeta+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(text, delay=delay)


def wait_for_any_text(page, texts, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for t in texts:
            try:
                if page.get_by_text(t, exact=False).first.is_visible():
                    return t
            except Exception:  # noqa: BLE001
                pass
        time.sleep(1)
    return None
