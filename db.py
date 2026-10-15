import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
IS_SERVERLESS = os.environ.get("IS_SERVERLESS", "").lower() in ("1", "true") or bool(os.environ.get("NETLIFY") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
DEFAULT_DATA_DIR = Path("/tmp/kfm_data") if IS_SERVERLESS else BASE
DATA_DIR = Path(os.environ.get("DATA_DIR", str(DEFAULT_DATA_DIR)))
DB_PATH = Path(os.environ.get("DB_PATH", str(DATA_DIR / "studio.db")))
_lock = threading.Lock()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_db_file():
    if not DB_PATH.exists():
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            seed_db = BASE / "studio.db"
            if seed_db.exists() and seed_db.resolve() != DB_PATH.resolve():
                import shutil
                shutil.copyfile(seed_db, DB_PATH)
        except Exception:
            pass


def conn():
    _ensure_db_file()
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                master_prompt TEXT DEFAULT '',
                engine TEXT DEFAULT 'browser',
                chat_url TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER NOT NULL,
                position INTEGER DEFAULT 0,
                kind TEXT DEFAULT 'episode',
                label TEXT DEFAULT '',
                prompt TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                image_path TEXT DEFAULT '',
                error TEXT DEFAULT '',
                updated_at TEXT,
                FOREIGN KEY(series_id) REFERENCES series(id) ON DELETE CASCADE
            );
            """
        )
        # purane database mein poster_path column jodo
        cols = [r[1] for r in c.execute("PRAGMA table_info(items)").fetchall()]
        if "poster_path" not in cols:
            c.execute("ALTER TABLE items ADD COLUMN poster_path TEXT DEFAULT ''")
        if "final_name" not in cols:
            c.execute("ALTER TABLE items ADD COLUMN final_name TEXT DEFAULT ''")
        scols = [r[1] for r in c.execute("PRAGMA table_info(series)").fetchall()]
        if "run_on" not in scols:
            c.execute("ALTER TABLE series ADD COLUMN run_on TEXT DEFAULT 'hub'")
        if "created_by" not in scols:
            c.execute("ALTER TABLE series ADD COLUMN created_by TEXT DEFAULT ''")
        # v3.5: category, master variants (JSON), har variant ki apni ChatGPT chat, character sheet
        for col, ddl in (("category", "TEXT DEFAULT ''"), ("master_variants", "TEXT DEFAULT ''"),
                         ("active_variant", "INTEGER DEFAULT 0"), ("variant_chats", "TEXT DEFAULT ''"),
                         ("characters", "TEXT DEFAULT ''")):
            if col not in scols:
                c.execute(f"ALTER TABLE series ADD COLUMN {col} {ddl}")
        for col, ddl in (("variant", "INTEGER DEFAULT -1"), ("regen_count", "INTEGER DEFAULT 0")):
            if col not in cols:
                c.execute(f"ALTER TABLE items ADD COLUMN {col} {ddl}")
        # Gambit v4: workspaces + templates
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kind TEXT DEFAULT 'generic',          -- kahanifm | speakeasy | generic
                project_label TEXT DEFAULT 'Project',
                color TEXT DEFAULT '#F7A928',
                default_ratio TEXT DEFAULT '1:1',
                base_prompt TEXT DEFAULT '',
                characters TEXT DEFAULT '',
                logo_path TEXT DEFAULT '',
                logo_on INTEGER DEFAULT 0,
                logo_width_pct INTEGER DEFAULT 28,
                safe_bottom_pct INTEGER DEFAULT 10,
                fit_mode TEXT DEFAULT 'crop',         -- crop | pad | off
                position INTEGER DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                ratio TEXT DEFAULT '',
                layout TEXT DEFAULT 'free',           -- free | grid4 | phrase4 | word | compare2
                prompt TEXT DEFAULT '',
                refs TEXT DEFAULT '[]',
                position INTEGER DEFAULT 0,
                created_at TEXT
            );
            """
        )
        scols = [r[1] for r in c.execute("PRAGMA table_info(series)").fetchall()]
        for col, ddl in (("workspace_id", "INTEGER DEFAULT 1"), ("template_id", "INTEGER DEFAULT 0"),
                         ("ratio", "TEXT DEFAULT ''"), ("refs", "TEXT DEFAULT '[]'")):
            if col not in scols:
                c.execute(f"ALTER TABLE series ADD COLUMN {col} {ddl}")
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                pw_hash TEXT NOT NULL,
                role TEXT DEFAULT 'member',
                agent_key TEXT UNIQUE,
                last_seen REAL DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                item_ids TEXT NOT NULL,
                new_chat INTEGER DEFAULT 0,
                status TEXT DEFAULT 'queued',
                stop INTEGER DEFAULT 0,
                current_label TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            );
            """
        )
        jcols = [r[1] for r in c.execute("PRAGMA table_info(agent_jobs)").fetchall()]
        if "variant" not in jcols:
            c.execute("ALTER TABLE agent_jobs ADD COLUMN variant INTEGER DEFAULT -1")
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,            -- thumb | prompt_write | poster | train
                series_id INTEGER,
                item_id INTEGER,
                engine TEXT DEFAULT '',
                who TEXT DEFAULT '',
                started_at REAL,
                ended_at REAL,
                seconds REAL,
                ok INTEGER DEFAULT 1,
                attempts INTEGER DEFAULT 1,
                error TEXT DEFAULT '',
                model TEXT DEFAULT '',
                meta TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS ev_kind_time ON events(kind, ended_at);
            """
        )
        # crash ke baad adhure agent jobs band
        c.execute("UPDATE agent_jobs SET status='lost' WHERE status IN ('queued','claimed')")
        # anything left "running/queued" from a crash goes back to pending
        c.execute("UPDATE items SET status='pending' WHERE status IN ('running','queued')")


def q(sql, args=(), one=False):
    with _lock, conn() as c:
        cur = c.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        return (rows[0] if rows else None) if one else rows


def ex(sql, args=()):
    with _lock, conn() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


# ---------- series ----------
def list_series(workspace_id=None):
    where, args = ("WHERE s.workspace_id=?", (workspace_id,)) if workspace_id else ("", ())
    return q(
        f"""SELECT s.*,
             (SELECT COUNT(*) FROM items i WHERE i.series_id=s.id) AS total,
             (SELECT COUNT(*) FROM items i WHERE i.series_id=s.id AND i.status='done') AS done,
             (SELECT COUNT(*) FROM items i WHERE i.series_id=s.id AND i.status='failed') AS failed
           FROM series s {where} ORDER BY s.id DESC""", args
    )


# ---------- workspaces / templates ----------
WS_FIELDS = ("name", "kind", "project_label", "color", "default_ratio", "base_prompt", "characters", "logo_path",
             "logo_on", "logo_width_pct", "safe_bottom_pct", "fit_mode", "position")
TPL_FIELDS = ("name", "ratio", "layout", "prompt", "refs", "position")


def list_workspaces():
    return q("SELECT * FROM workspaces ORDER BY position, id")


def get_workspace(wid):
    return q("SELECT * FROM workspaces WHERE id=?", (wid,), one=True)


def create_workspace(**f):
    f = {k: v for k, v in f.items() if k in WS_FIELDS}
    cols = ", ".join(list(f) + ["created_at"])
    return ex(f"INSERT INTO workspaces({cols}) VALUES ({','.join('?' * (len(f) + 1))})", (*f.values(), now()))


def update_workspace(wid, **f):
    f = {k: v for k, v in f.items() if k in WS_FIELDS}
    if f:
        ex(f"UPDATE workspaces SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), wid))


def delete_workspace(wid):
    ex("DELETE FROM templates WHERE workspace_id=?", (wid,))
    ex("DELETE FROM workspaces WHERE id=?", (wid,))


def list_templates(wid):
    return q("SELECT * FROM templates WHERE workspace_id=? ORDER BY position, id", (wid,))


def get_template(tid):
    return q("SELECT * FROM templates WHERE id=?", (tid,), one=True)


def create_template(wid, **f):
    f = {k: v for k, v in f.items() if k in TPL_FIELDS}
    cols = ", ".join(["workspace_id"] + list(f) + ["created_at"])
    return ex(f"INSERT INTO templates({cols}) VALUES ({','.join('?' * (len(f) + 2))})", (wid, *f.values(), now()))


def update_template(tid, **f):
    f = {k: v for k, v in f.items() if k in TPL_FIELDS}
    if f:
        ex(f"UPDATE templates SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), tid))


def delete_template(tid):
    ex("DELETE FROM templates WHERE id=?", (tid,))


def get_series(sid):
    s = q("SELECT * FROM series WHERE id=?", (sid,), one=True)
    if s:
        s["items"] = get_items(sid)
    return s


def create_series(name, master_prompt="", engine="browser"):
    return ex(
        "INSERT INTO series(name, master_prompt, engine, created_at, updated_at) VALUES (?,?,?,?,?)",
        (name, master_prompt, engine, now(), now()),
    )


def update_series(sid, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("name", "master_prompt", "engine", "chat_url", "run_on", "created_by",
                                                         "category", "master_variants", "active_variant", "variant_chats",
                                                         "characters", "workspace_id", "template_id", "ratio", "refs")}
    if not allowed:
        return
    sets = ", ".join(f"{k}=?" for k in allowed)
    ex(f"UPDATE series SET {sets}, updated_at=? WHERE id=?", (*allowed.values(), now(), sid))


def delete_series(sid):
    ex("DELETE FROM items WHERE series_id=?", (sid,))
    ex("DELETE FROM series WHERE id=?", (sid,))


# ---------- items ----------
def get_items(sid):
    return q("SELECT * FROM items WHERE series_id=? ORDER BY position, id", (sid,))


def get_item(iid):
    return q("SELECT * FROM items WHERE id=?", (iid,), one=True)


def add_item(sid, label, prompt, kind="episode"):
    pos = q("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM items WHERE series_id=?", (sid,), one=True)["p"]
    return ex(
        "INSERT INTO items(series_id, position, kind, label, prompt, status, updated_at) VALUES (?,?,?,?,?,?,?)",
        (sid, pos, kind, label, prompt, "pending", now()),
    )


def update_item(iid, **fields):
    allowed = {
        k: v for k, v in fields.items()
        if k in ("label", "prompt", "kind", "status", "image_path", "error", "position", "poster_path", "final_name",
                     "variant", "regen_count")
    }
    if not allowed:
        return
    sets = ", ".join(f"{k}=?" for k in allowed)
    ex(f"UPDATE items SET {sets}, updated_at=? WHERE id=?", (*allowed.values(), now(), iid))


def delete_item(iid):
    ex("DELETE FROM items WHERE id=?", (iid,))


def reorder(sid, ids):
    for pos, iid in enumerate(ids):
        ex("UPDATE items SET position=? WHERE id=? AND series_id=?", (pos, iid, sid))


# ---------- users ----------
def list_users():
    return q("SELECT id, name, role, agent_key, last_seen, created_at FROM users ORDER BY id")


def get_user(uid):
    return q("SELECT * FROM users WHERE id=?", (uid,), one=True)


def get_user_by_name(name):
    return q("SELECT * FROM users WHERE lower(name)=lower(?)", (name,), one=True)


def get_user_by_key(key):
    if not key:
        return None
    return q("SELECT * FROM users WHERE agent_key=?", (key,), one=True)


def create_user(name, pw_hash, role, agent_key):
    return ex("INSERT INTO users(name, pw_hash, role, agent_key, created_at) VALUES (?,?,?,?,?)",
              (name, pw_hash, role, agent_key, now()))


def update_user(uid, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("pw_hash", "role", "agent_key", "last_seen")}
    if allowed:
        sets = ", ".join(f"{k}=?" for k in allowed)
        ex(f"UPDATE users SET {sets} WHERE id=?", (*allowed.values(), uid))


def delete_user(uid):
    ex("DELETE FROM users WHERE id=?", (uid,))


def count_users():
    return q("SELECT COUNT(*) AS n FROM users", one=True)["n"]


# ---------- agent jobs ----------
def create_agent_job(series_id, user_id, item_ids, new_chat, variant=-1):
    import json as _j
    return ex("INSERT INTO agent_jobs(series_id, user_id, item_ids, new_chat, status, created_at, updated_at, variant) VALUES (?,?,?,?,?,?,?,?)",
              (series_id, user_id, _j.dumps(item_ids), int(bool(new_chat)), "queued", now(), now(), int(variant)))


def get_agent_job(jid):
    import json as _j
    j = q("SELECT * FROM agent_jobs WHERE id=?", (jid,), one=True)
    if j:
        j["item_ids"] = _j.loads(j["item_ids"])
    return j


def update_agent_job(jid, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("status", "stop", "current_label")}
    if allowed:
        sets = ", ".join(f"{k}=?" for k in allowed)
        ex(f"UPDATE agent_jobs SET {sets}, updated_at=? WHERE id=?", (*allowed.values(), now(), jid))


def active_agent_jobs(user_id=None, series_id=None):
    import json as _j
    sql = "SELECT * FROM agent_jobs WHERE status IN ('queued','claimed')"
    args = []
    if user_id is not None:
        sql += " AND user_id=?"
        args.append(user_id)
    if series_id is not None:
        sql += " AND series_id=?"
        args.append(series_id)
    rows = q(sql + " ORDER BY id", tuple(args))
    for r in rows:
        r["item_ids"] = _j.loads(r["item_ids"])
    return rows


# ---------------- events (dashboard ke liye) ----------------
def log_event(kind, series_id=None, item_id=None, engine="", who="", started_at=None, ended_at=None,
              ok=True, attempts=1, error="", model="", meta=None):
    import json as _json
    import time as _time
    end = ended_at or _time.time()
    start = started_at or end
    ex("INSERT INTO events(kind, series_id, item_id, engine, who, started_at, ended_at, seconds, ok, attempts, error, model, meta)"
       " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
       (kind, series_id, item_id, engine, who, start, end, round(end - start, 2), 1 if ok else 0, attempts,
        (error or "")[:400], model or "", _json.dumps(meta or {}, ensure_ascii=False)))


def events(kind=None, since=None):
    sql, args = "SELECT * FROM events WHERE 1=1", []
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if since:
        sql += " AND ended_at>=?"
        args.append(since)
    return q(sql + " ORDER BY ended_at", args)
