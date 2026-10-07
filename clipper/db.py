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
  platform TEXT NOT NULL,
  status TEXT NOT NULL,
  url TEXT,
  error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at REAL,
  updated_at REAL NOT NULL,
  UNIQUE(video_id, platform)
);

CREATE TABLE IF NOT EXISTS accounts (
  platform TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  note TEXT,
  checked_at REAL
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


def init():
    for d in (DATA_DIR, VIDEOS_DIR, PROFILES_DIR, SHOTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)
        c.execute("PRAGMA journal_mode=WAL")


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
