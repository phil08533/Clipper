"""SQLite storage. One short-lived connection per call keeps this safe across threads."""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "clipper.db"
VIDEOS_DIR = DATA_DIR / "videos"
PROFILES_DIR = DATA_DIR / "browser_profiles"
SHOTS_DIR = DATA_DIR / "screenshots"

_write_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS prompts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0,
  config TEXT NOT NULL,
  next_post_at REAL,
  schedule_plan TEXT,
  topic_cursor INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id INTEGER,
  status TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  hashtags TEXT NOT NULL DEFAULT '[]',
  topic TEXT NOT NULL DEFAULT '',
  script TEXT,
  duration REAL,
  error TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  posted_at REAL,
  files_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS videos_status ON videos(status);

CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id INTEGER NOT NULL,
  account_id INTEGER NOT NULL,
  platform TEXT NOT NULL,
  status TEXT NOT NULL,
  url TEXT,
  error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at REAL,
  updated_at REAL NOT NULL,
  UNIQUE(video_id, account_id)
);

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  label TEXT NOT NULL,
  profile TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'not_connected',
  note TEXT,
  checked_at REAL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  level TEXT NOT NULL,
  source TEXT NOT NULL,
  message TEXT NOT NULL,
  video_id INTEGER
);
"""


PLATFORM_NAMES = {"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram"}


def _columns(c, table):
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}


def init():
    for d in (DATA_DIR, VIDEOS_DIR, PROFILES_DIR, SHOTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    with _write_lock, connect() as c:
        # v1 had one account per platform; move those tables aside before creating the new ones.
        old_accounts = "platform" in _columns(c, "accounts") and "id" not in _columns(c, "accounts")
        old_posts = _columns(c, "posts") and "account_id" not in _columns(c, "posts")
        if old_accounts:
            c.execute("ALTER TABLE accounts RENAME TO accounts_v1")
        if old_posts:
            c.execute("ALTER TABLE posts RENAME TO posts_v1")
        c.executescript(SCHEMA)
        c.execute("PRAGMA journal_mode=WAL")
        if "schedule_plan" not in _columns(c, "campaigns"):
            c.execute("ALTER TABLE campaigns ADD COLUMN schedule_plan TEXT")
        _migrate_v1(c, old_accounts, old_posts)


def _migrate_v1(c, old_accounts, old_posts):
    ids = {}
    if old_accounts or old_posts:
        rows = {r["platform"]: dict(r) for r in c.execute("SELECT * FROM accounts_v1")} if old_accounts else {}
        for platform, name in PLATFORM_NAMES.items():
            row = rows.get(platform)
            if row or (PROFILES_DIR / platform).is_dir():
                cur = c.execute("INSERT INTO accounts (platform, label, profile, status, note, checked_at, created_at) VALUES (?,?,?,?,?,?,?)",
                                (platform, name, platform, row["status"] if row else "not_connected",
                                 row["note"] if row else None, row["checked_at"] if row else None, time.time()))
                ids[platform] = cur.lastrowid
    if old_posts:
        for r in c.execute("SELECT * FROM posts_v1").fetchall():
            if r["platform"] not in ids:
                cur = c.execute("INSERT INTO accounts (platform, label, profile, created_at) VALUES (?,?,?,?)",
                                (r["platform"], PLATFORM_NAMES.get(r["platform"], r["platform"]), r["platform"], time.time()))
                ids[r["platform"]] = cur.lastrowid
            c.execute("INSERT OR IGNORE INTO posts (video_id, account_id, platform, status, url, error, attempts, next_attempt_at, updated_at) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", (r["video_id"], ids[r["platform"]], r["platform"], r["status"], r["url"],
                                                     r["error"], r["attempts"], r["next_attempt_at"], r["updated_at"]))
        c.execute("DROP TABLE posts_v1")
    if old_accounts:
        c.execute("DROP TABLE accounts_v1")
    # v1 campaigns listed platforms; v2 lists accounts.
    for camp in c.execute("SELECT id, config FROM campaigns").fetchall():
        cfg = loads(camp["config"], {})
        if "accounts" not in cfg:
            cfg["accounts"] = [i for p, i in ids.items() if p in cfg.get("platforms", [])]
            cfg.pop("platforms", None)
            c.execute("UPDATE campaigns SET config=? WHERE id=?", (json.dumps(cfg), camp["id"]))


@contextmanager
def connect():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def query(sql, args=()):
    with connect() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    with _write_lock, connect() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


def now():
    return time.time()


# ---------- logging ----------

def log(level, source, message, video_id=None):
    print(f"[{time.strftime('%H:%M:%S')}] {level.upper():5} {source}: {message}", flush=True)
    try:
        execute("INSERT INTO logs (ts, level, source, message, video_id) VALUES (?,?,?,?,?)",
                (now(), level, source, str(message)[:4000], video_id))
    except sqlite3.Error:
        pass


# ---------- json helpers ----------

def loads(s, default):
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError):
        return default
