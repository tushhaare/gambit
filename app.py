"""
Gambit — AI poster & thumbnail studio (workspaces: KahaniFM, SpeakEasy, ...)
==================================
Local dashboard: series banao, master prompt + series/episode briefs daalo,
drag karke order set karo, Generate dabao. Worker ek-ek brief ChatGPT (ya
OpenAI API) ko bhejta hai, images outputs/<series>/ mein save karta hai aur
Excel log update karta hai.

Team mode: ye PC "hub" hai. Teammates browser se login karte hain; har teammate
ke laptop pe agent.py chalta hai jo unke apne ChatGPT se images banata hai aur
hub pe bhej deta hai.

Run:  python app.py   ->  http://localhost:5000
"""
import json
import os
import platform
import queue
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import io
import secrets
import zipfile
from datetime import timedelta

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import imgconv

BASE = Path(__file__).parent
IS_SERVERLESS = os.environ.get("IS_SERVERLESS", "").lower() in ("1", "true") or bool(os.environ.get("NETLIFY") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
DEFAULT_DATA_DIR = Path("/tmp/kfm_data") if IS_SERVERLESS else BASE
DATA_DIR = Path(os.environ.get("DATA_DIR", str(DEFAULT_DATA_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUT = DATA_DIR / "outputs"
SETTINGS_FILE = DATA_DIR / "settings.json"
OUT.mkdir(exist_ok=True)

DEFAULT_SETTINGS = {
    "cdp_url": "http://localhost:9223",
    "image_prefix": "Create an image: ",
    "master_wait": 90,
    "image_timeout": 360,
    "gap_seconds": 8,
    "retries": 1,
    "openai_api_key": "",
    "api_model": "dall-e-3",
    "api_size": "1024x1024",
    "api_quality": "",
    "master_suffix": ("IMPORTANT: Do NOT generate any image for this message. These are only the rules for this chat. "
                      "Reply with just one line: \"READY — rules samajh gaya, brief bhejo.\" "
                      "Generate an image only when I send a brief."),
    "series_format": "webp",   # series thumbnail ka format
    "episode_format": "png",   # episode thumbnails ka format
    "webp_quality": 92,
    "poster_site_url": "https://funda-audio-thumbnail-gen.vercel.app/",
    "poster_size": "1000x1500",
    "poster_format": "webp",
    "poster_timeout": 300,
    "poster_headless": 1,      # 1 = chhupa browser, 0 = dikhne wala (debug)
    "public_url": "",          # teammates wala link (jaise https://sagar-pc.tail1234.ts.net)
}

app = Flask(__name__)
# Cloudflare Tunnel / ngrok ke peeche sahi https link pehchanne ke liye
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
SECRET_FILE = DATA_DIR / "secret.key"
env_secret = os.environ.get("SECRET_KEY")
if env_secret:
    app.secret_key = env_secret.strip()
else:
    if not SECRET_FILE.exists():
        try:
            SECRET_FILE.write_text(secrets.token_hex(32))
        except Exception:
            pass
    if SECRET_FILE.exists():
        try:
            app.secret_key = SECRET_FILE.read_text().strip()
        except Exception:
            app.secret_key = secrets.token_hex(32)
    else:
        app.secret_key = secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=30)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600   # static files 1 ghanta cache
APP_VERSION = "4.0-dev"
try:  # JSON/HTML/JS ko gzip karke bhejo (tunnel pe tez)
    from flask_compress import Compress
    Compress(app)
except Exception:
    pass


def _asset_version():
    """CSS/JS ka content badle to version badle — browser purani cached file na dikhaye."""
    import hashlib
    h = hashlib.md5(APP_VERSION.encode())
    for f in ("static/style.css", "static/app.js"):
        try:
            h.update((BASE / f).read_bytes())
        except Exception:
            pass
    return h.hexdigest()[:10]


ASSET_V = _asset_version()


@app.context_processor
def _inject_version():
    return {"v": ASSET_V}
AGENT_ONLINE_SECS = 45


# ---------------- settings ----------------
def load_settings():
    s = dict(DEFAULT_SETTINGS)
    src = SETTINGS_FILE if SETTINGS_FILE.exists() else (BASE / "settings.json")
    if src.exists():
        try:
            s.update(json.loads(src.read_text(encoding="utf-8")))
        except Exception:
            pass
    if s.get("cdp_url") == "http://localhost:9222":   # DEV: purane tool ke Chrome se takraav na ho
        s["cdp_url"] = "http://localhost:9223"
    return s


def save_settings(new):
    s = load_settings()
    for k in DEFAULT_SETTINGS:
        if k in new:
            v = new[k]
            if isinstance(DEFAULT_SETTINGS[k], list) and not isinstance(v, list):
                continue
            if isinstance(DEFAULT_SETTINGS[k], int):
                try:
                    v = int(v)
                except Exception:
                    continue
            s[k] = v
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Warning: could not save settings to {SETTINGS_FILE}: {e}")
    return s


# ---------------- helpers ----------------
def slugify(text, maxlen=50):
    t = re.sub(r"[^\w\s-]", "", text or "", flags=re.U).strip().lower()
    t = re.sub(r"[\s_-]+", "_", t)
    return (t[:maxlen].strip("_")) or "untitled"


# ---------------- final file naming ----------------
BAD_CHARS = r'[\\/:*?"<>|]'


def clean_name(text):
    """Windows-safe file name: : / ? * etc hata do, spaces theek karo."""
    t = re.sub(BAD_CHARS, " ", text or "")
    t = re.sub(r"\s+", " ", t).strip(" .-—–")
    return t or "Untitled"


def nice_case(text):
    """ALL CAPS ho to Title Case karo, warna jaisa hai waisa."""
    letters = [c for c in text if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return " ".join(w.capitalize() for w in text.split())
    return text


def episode_title(label):
    """'EP01 — HASTINAPUR SE VIDAAI' -> 'Hastinapur Se Vidaai' (koi prefix/suffix nahi)."""
    t = re.sub(r"^\s*(EP(ISODE)?\s*\d+)\s*[:\-—–|.]*\s*", "", label or "", flags=re.I)
    t = t.strip(' "“”')
    return nice_case(t)


def final_base(series, item):
    """Final file ka base naam (extension ke bina)."""
    if (item.get("final_name") or "").strip():
        return clean_name(item["final_name"])
    if item["kind"] == "series":
        return clean_name(series["name"])
    return clean_name(episode_title(item["label"]) or item["label"])


def build_final(series_id, log=print):
    """outputs/<series>/final/ — app pe upload karne wali final WebP files.
    - Episode:  <Episode Name>.webp                       (CD poster, Vercel se)
    - Series:   <Series Name> (Series Thumbnail).webp      (CD poster, Vercel se)
                <Series Name>.webp                        (bina CD, square thumbnail)
    """
    s = db.get_series(series_id)
    if not s:
        return []
    settings = load_settings()
    q = int(settings["webp_quality"])
    final = series_dir(s) / "final"
    final.mkdir(exist_ok=True)
    for old in final.glob("*.webp"):
        old.unlink()
    used, made = set(), []

    def unique(base):
        name, n = base, 2
        while name.lower() in used:
            name, n = f"{base} ({n})", n + 1
        used.add(name.lower())
        return name

    for it in s["items"]:
        base = final_base(s, it)
        if it["kind"] == "series":
            if it["image_path"] and Path(it["image_path"]).exists():
                p = final / f"{unique(base)}.webp"
                imgconv.write(p, Path(it["image_path"]).read_bytes(), q)
                made.append(p)
            if it.get("poster_path") and Path(it["poster_path"]).exists():
                p = final / f"{unique(base + ' (Series Thumbnail)')}.webp"
                imgconv.write(p, Path(it["poster_path"]).read_bytes(), q)
                made.append(p)
        elif it.get("poster_path") and Path(it["poster_path"]).exists():
            p = final / f"{unique(base)}.webp"
            imgconv.write(p, Path(it["poster_path"]).read_bytes(), q)
            made.append(p)
    log(f"Final folder ready: {len(made)} WebP file(s) -> {final}")
    return made


def series_dir(series):
    d = OUT / f"{series['id']:03d}_{slugify(series['name'])}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def item_ext(item, settings=None):
    s = settings or load_settings()
    fmt = s["series_format"] if item["kind"] == "series" else s["episode_format"]
    fmt = (fmt or "png").lower().lstrip(".")
    return fmt if fmt in imgconv.FORMATS else "png"


def item_filename(items, item, settings=None):
    idx = [i["id"] for i in items].index(item["id"])
    tag = "00_series" if item["kind"] == "series" else f"{idx:02d}"
    return f"{tag}_{slugify(item['label'], 40)}.{item_ext(item, settings)}"


def split_bulk(text):
    parts = [p.strip() for p in re.split(r"^\s*===\s*$", text or "", flags=re.M)]
    return [p for p in parts if p]


def guess_label(prompt, fallback):
    first = prompt.strip().splitlines()[0] if prompt.strip() else ""
    m = re.search(r"EP(?:ISODE)?\s*0*(\d+)", first, flags=re.I)
    if m:
        ep = f"EP{int(m.group(1)):02d}"
        title = re.search(r'["“]([^"”]{2,60})["”]', prompt)
        if title:
            return f"{ep} — {title.group(1).strip()}"
        rest = re.sub(r"^.*?EP(?:ISODE)?\s*\d+\s*[:\-—–|]*\s*", "", first, flags=re.I).strip(" :-—*#")
        return f"{ep} — {rest[:50]}" if rest else ep
    if len(first) <= 70 and first:
        return first.strip(" :-—#*")
    return fallback


def write_excel(series_id):
    """outputs/<series>/<series>_log.xlsx ko refresh karta hai."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except Exception:
        return None
    s = db.get_series(series_id)
    if not s:
        return None
    d = series_dir(s)
    path = d / f"{slugify(s['name'])}_log.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Thumbnails"
    ws.append(["Series", s["name"]])
    ws.append(["Engine", s["engine"]])
    ws.append(["Chat URL", s.get("chat_url") or ""])
    ws.append(["Updated", datetime.now().strftime("%Y-%m-%d %H:%M")])
    ws.append([])
    head = ["#", "Type", "Label", "Status", "File", "Updated", "Error", "Prompt", "App poster (WebP)", "Final file name(s)"]
    ws.append(head)
    for c in ws[6]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="F7A928")
    colors = {"done": "D9F7E3", "failed": "FFE0E0", "running": "FFF4CC", "queued": "E6F0FF"}
    for n, it in enumerate(s["items"]):
        ws.append([
            n, it["kind"], it["label"], it["status"], it["image_path"] or "",
            it["updated_at"] or "", it["error"] or "", it["prompt"], it.get("poster_path") or "",
            (lambda b: f"{b}.webp + {b} (Series Thumbnail).webp" if it["kind"] == "series" else f"{b}.webp")(final_base(s, it)),
        ])
        row = ws.max_row
        if it.get("poster_path"):
            pc = ws.cell(row=row, column=9)
            pc.hyperlink = str(Path(it["poster_path"]).resolve())
            pc.font = Font(color="0563C1", underline="single")
        if it["image_path"]:
            cell = ws.cell(row=row, column=5)
            cell.hyperlink = str(Path(it["image_path"]).resolve())
            cell.font = Font(color="0563C1", underline="single")
        fill = colors.get(it["status"])
        if fill:
            ws.cell(row=row, column=4).fill = PatternFill("solid", fgColor=fill)
        ws.cell(row=row, column=8).alignment = Alignment(wrap_text=True, vertical="top")
    for col, w in zip("ABCDEFGHIJ", [5, 9, 34, 10, 50, 18, 40, 90, 50, 60]):
        ws.column_dimensions[col].width = w
    ws2 = wb.create_sheet("Master prompt")
    ws2["A1"] = s["master_prompt"]
    ws2["A1"].alignment = Alignment(wrap_text=True, vertical="top")
    ws2.column_dimensions["A"].width = 140
    try:
        wb.save(path)
    except PermissionError:
        # Excel mein file khuli ho to alag naam se save
        path = d / f"{slugify(s['name'])}_log_{int(time.time())}.xlsx"
        wb.save(path)
    return path


# ---------------- v3.5: master variants (har variant = alag ChatGPT chat) ----------------
def _jl(text, default):
    try:
        v = json.loads(text or "")
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


def variants_of(s):
    """[{name, angle, prompt}] — purani series (bina variants) = ek hi variant (uska master_prompt)."""
    v = _jl(s.get("master_variants"), [])
    v = [x for x in v if isinstance(x, dict)]
    if not v:
        return [{"name": "A — Master", "angle": "", "prompt": s.get("master_prompt") or ""}]
    act = active_of(s, len(v))
    v[act] = dict(v[act], prompt=s.get("master_prompt") or v[act].get("prompt", ""))  # textarea wala hi sach hai
    return v


def active_of(s, n=None):
    n = n or max(1, len(_jl(s.get("master_variants"), [])))
    a = int(s.get("active_variant") or 0)
    return a if 0 <= a < n else 0


def master_for(s, v):
    vs = variants_of(s)
    return vs[v % len(vs)].get("prompt", "") if vs else (s.get("master_prompt") or "")


def chat_for(s, v):
    if v == active_of(s):
        return s.get("chat_url") or ""
    return _jl(s.get("variant_chats"), {}).get(str(v), "")


def set_chat(sid, v, url):
    s = db.get_series(sid)
    if not s:
        return
    chats = _jl(s.get("variant_chats"), {})
    chats[str(v)] = url
    fields = {"variant_chats": json.dumps(chats)}
    if v == active_of(s):
        fields["chat_url"] = url
    db.update_series(sid, **fields)


def next_variant(s, it):
    n = len(variants_of(s))
    if n <= 1:
        return 0
    base = it.get("variant") if (it.get("variant") is not None and it.get("variant") >= 0) else active_of(s, n)
    return (base + 1) % n


def series_public(s):
    """API ke liye: JSON fields parse karke bhejo."""
    if not s:
        return {}
    s = dict(s)
    s["variants"] = [{"name": v.get("name", ""), "angle": v.get("angle", ""), "prompt": v.get("prompt", ""),
                      "has_chat": bool(chat_for(s, i))} for i, v in enumerate(variants_of(s))]
    s["active_variant"] = active_of(s, len(s["variants"]))
    s["characters"] = _jl(s.get("characters"), [])
    import workspaces as wsmod
    tpl = db.get_template(s.get("template_id") or 0) if s.get("template_id") else None
    s["template"] = {"id": tpl["id"], "name": tpl["name"], "layout": tpl["layout"], "ratio": tpl["ratio"]} if tpl else None
    s["refs"] = [{"name": Path(p).name, "url": f"/api/ref/{s.get('workspace_id') or 1}/{Path(p).name}",
                  "from": "project" if Path(p).name in _jl(s.get("refs"), []) else "template"}
                 for p in wsmod.project_refs(s)]
    s.pop("variant_chats", None)
    s.pop("master_variants", None)
    return s


# ---------------- worker ----------------
class Worker:
    def __init__(self, start_thread=True):
        self.jobs = queue.Queue()
        self.stop_flag = threading.Event()
        self.state = "idle"
        self.current = None  # {"series_id", "item_id", "label"}
        self.logs = []
        self.log_seq = 0
        self.lock = threading.Lock()
        if start_thread and not IS_SERVERLESS:
            threading.Thread(target=self.loop, daemon=True).start()

    def log(self, msg):
        with self.lock:
            self.log_seq += 1
            line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
            self.logs.append({"n": self.log_seq, "t": line})
            self.logs = self.logs[-500:]
        print(line, flush=True)

    def enqueue(self, series_id, item_ids, new_chat=False, variant=None):
        if IS_SERVERLESS:
            self.log("Serverless mode: Hub PC pe browser generation nahi ho sakti. Teammate ka agent use karein ('Run on').")
            return
        for iid in item_ids:
            db.update_item(iid, status="queued", error="")
        self.stop_flag.clear()
        self.jobs.put({"series_id": series_id, "item_ids": item_ids, "new_chat": new_chat, "variant": variant})
        self.log(f"Queue mein {len(item_ids)} thumbnail(s) add hue.")

    def stop(self):
        self.stop_flag.set()
        # queue khali karo
        while True:
            try:
                job = self.jobs.get_nowait()
                for iid in job["item_ids"]:
                    it = db.get_item(iid)
                    if it and it["status"] == "queued":
                        db.update_item(iid, status="pending")
            except queue.Empty:
                break
        self.log("Stop dabaya gaya — current item ke baad ruk jaayega.")

    def loop(self):
        while True:
            job = self.jobs.get()
            try:
                if job.get("type") == "posters":
                    self.run_posters(job)
                else:
                    self.run_job(job)
            except Exception as e:
                self.log(f"Job error: {e}")
            finally:
                for iid in ([] if job.get("type") == "posters" else job["item_ids"]):
                    it = db.get_item(iid)
                    if it and it["status"] in ("queued", "running"):
                        db.update_item(iid, status="pending")
                write_excel(job["series_id"])
                self.state, self.current = "idle", None

    def enqueue_posters(self, series_id, item_ids):
        if IS_SERVERLESS:
            self.log("Serverless mode: Hub PC pe poster automation nahi chal sakti.")
            return
        self.stop_flag.clear()
        self.jobs.put({"type": "posters", "series_id": series_id, "item_ids": item_ids})
        self.log(f"Poster job queue mein ({len(item_ids)} image).")

    def run_posters(self, job):
        from poster_site import make_posters

        settings = load_settings()
        s = db.get_series(job["series_id"])
        items = [db.get_item(i) for i in job["item_ids"]]
        items = [i for i in items if i and i["image_path"] and Path(i["image_path"]).exists()]
        if not s or not items:
            self.log("Poster ke liye koi bani hui image nahi mili.")
            return
        self.state = "posters"
        self.current = {"series_id": s["id"], "item_id": None, "label": f"Posters ({len(items)})"}
        out = series_dir(s) / "posters"
        self.log(f"=== Posters: {s['name']} — {len(items)} image(s) -> {settings['poster_site_url']} ===")
        t_post = time.time()
        saved = make_posters(settings, [i["image_path"] for i in items], out, self.log, self.stop_flag.is_set)
        try:
            db.log_event("poster", s["id"], None, "poster_site", "Hub PC", t_post, time.time(), bool(saved), 1,
                         "" if saved else "No posters", "", {"count": len(saved or []), "asked": len(items)})
        except Exception:
            pass
        # poster ko uske thumbnail se match karo (file ke naam se)
        matched = 0
        for it in items:
            stem = Path(it["image_path"]).stem.lower()
            hit = next((p for p in saved if p.stem.lower().startswith(stem) or stem in p.stem.lower()), None)
            if hit:
                db.update_item(it["id"], poster_path=str(hit))
                matched += 1
        if not matched and len(saved) == len(items):
            # naam match na ho to order se jodo (dono ko file-naam se sort karke)
            for it, p in zip(sorted(items, key=lambda i: Path(i["image_path"]).name), sorted(saved, key=lambda p: p.name)):
                db.update_item(it["id"], poster_path=str(p))
            matched = len(items)
        self.log(f"Posters ready: {len(saved)} file(s) in {out} ({matched} thumbnails se match hue)")
        build_final(s["id"], self.log)

    def make_engine(self, kind, settings):
        if kind == "api":
            from engine_api import ApiEngine
            return ApiEngine(settings, self.log)
        from engine_browser import BrowserEngine
        return BrowserEngine(settings, self.log)

    def run_job(self, job):
        settings = load_settings()
        s = db.get_series(job["series_id"])
        if not s:
            return
        self.state = "starting"
        vs = variants_of(s)
        v = job.get("variant")
        v = active_of(s, len(vs)) if v is None or v < 0 else v % len(vs)
        master = master_for(s, v)
        vname = vs[v].get("name") or f"Variant {v + 1}"
        self.log(f"=== {s['name']} — engine: {s['engine']} — master: {vname} ===")
        engine = self.make_engine(s["engine"], settings)
        out_dir = series_dir(s)
        try:
            old_chat = chat_for(s, v)
            reuse = s["engine"] == "browser" and old_chat and not job["new_chat"]
            url = engine.open(old_chat if reuse else "")
            if reuse:
                self.log(f"Purani chat khuli ({vname} pehle se usme hai): {url}")
            else:
                if master.strip():
                    import workspaces as wsmod
                    refs = wsmod.project_refs(s) if s["engine"] == "browser" else []
                    engine.send_master(master, refs)
                if s["engine"] == "browser":
                    set_chat(s["id"], v, engine.current_url())
                    self.log(f"Nayi chat ({vname}): {engine.current_url()}")

            for iid in job["item_ids"]:
                if self.stop_flag.is_set():
                    break
                items = db.get_items(s["id"])
                it = db.get_item(iid)
                if not it:
                    continue
                self.state = "running"
                self.current = {"series_id": s["id"], "item_id": iid, "label": it["label"]}
                db.update_item(iid, status="running", error="")
                fname = item_filename(items, it, settings)
                path = out_dir / fname
                ok, err = False, ""
                t_start, tries = time.time(), 0
                for attempt in range(int(settings["retries"]) + 1):
                    tries = attempt + 1
                    if self.stop_flag.is_set():
                        err = "Stopped"
                        break
                    self.log(f"[{it['label']}] bhej raha hoon (try {attempt + 1})...")
                    try:
                        ok, err = engine.generate(it["prompt"], path, self.stop_flag.is_set)
                    except Exception as e:
                        ok, err = False, str(e)
                    if ok:
                        break
                    self.log(f"[{it['label']}] fail: {err}")
                    engine.screenshot(out_dir / f"error_{path.stem}.png")
                    if s["engine"] == "browser" and attempt < int(settings["retries"]):
                        try:
                            engine.page.goto(engine.current_url())
                            engine.page.wait_for_timeout(5000)
                        except Exception:
                            pass
                was_regen = bool((it.get("image_path") or "").strip())
                if err != "Stopped":
                    try:
                        db.log_event("thumb", s["id"], iid, s["engine"], "Hub PC", t_start, time.time(), ok, tries,
                                     "" if ok else err, settings.get("api_model", "") if s["engine"] == "api" else "",
                                     {"variant": v, "regen": was_regen})
                    except Exception:
                        pass
                if ok:
                    _postprocess(s, path, self.log)
                    db.update_item(iid, status="done", image_path=str(path), error="", variant=v,
                                   regen_count=(it.get("regen_count") or 0) + (1 if was_regen else 0))
                    self.log(f"[{it['label']}] saved -> {path.name}")
                else:
                    db.update_item(iid, status="pending" if err == "Stopped" else "failed", error=err)
                write_excel(s["id"])
                if not self.stop_flag.is_set():
                    time.sleep(int(settings["gap_seconds"]))
            self.log("Job khatam." if not self.stop_flag.is_set() else "Ruk gaya.")
        finally:
            engine.close()


worker = None


# ---------------- pages ----------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------- Gambit: workspaces / templates / refs / builder ----------------
def _postprocess(s, path, log=print):
    import workspaces as wsmod
    try:
        ws = db.get_workspace(s.get("workspace_id") or 1)
        if ws:
            wsmod.postprocess(path, ws, s.get("ratio") or "", log)
    except Exception as e:
        log(f"Post-process error: {e}")


def _ws_public(ws):
    w = dict(ws)
    w["characters"] = _jl(w.get("characters"), [])
    w["has_logo"] = bool(w.get("logo_path"))
    w["logo_url"] = f"/api/workspaces/{w['id']}/logo?t={int(time.time())}" if w["has_logo"] else ""
    w["templates"] = []
    for t in db.list_templates(w["id"]):
        t = dict(t)
        t["refs"] = [{"name": n, "url": f"/api/ref/{w['id']}/{n}"} for n in _jl(t.get("refs"), [])]
        w["templates"].append(t)
    w["series_count"] = len(db.list_series(w["id"]))
    return w


IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


def _save_ref_files(wid, files):
    import workspaces as wsmod
    names = []
    for f in files:
        if not f or not f.filename.lower().endswith(IMG_EXT):
            continue
        name = f"{secrets.token_hex(4)}_{slugify(Path(f.filename).stem, 30)}{Path(f.filename).suffix.lower()}"
        (wsmod.ref_dir(wid) / name).write_bytes(f.read())
        names.append(name)
    return names


@app.get("/api/workspaces")
def api_workspaces():
    import workspaces as wsmod
    return jsonify({"workspaces": [_ws_public(w) for w in db.list_workspaces()],
                    "ratios": list(wsmod.RATIOS), "layouts": wsmod.LAYOUTS,
                    "layout_cols": {k: v["cols"] for k, v in wsmod.LAYOUT_SPEC.items()}})


@app.post("/api/workspaces")
def api_workspace_create():
    require_admin()
    d = request.get_json(force=True) or {}
    wid = db.create_workspace(name=(d.get("name") or "New workspace").strip(), kind="generic",
                              project_label=d.get("project_label") or "Project", default_ratio=d.get("default_ratio") or "1:1",
                              base_prompt=d.get("base_prompt") or "", position=len(db.list_workspaces()))
    db.create_template(wid, name="Default", ratio=d.get("default_ratio") or "1:1", layout="free", prompt="")
    return jsonify(_ws_public(db.get_workspace(wid)))


@app.put("/api/workspaces/<int:wid>")
def api_workspace_update(wid):
    require_admin()
    d = request.get_json(force=True) or {}
    if "characters" in d and isinstance(d["characters"], list):
        d["characters"] = json.dumps(d["characters"], ensure_ascii=False)
    for k in ("logo_on", "logo_width_pct", "safe_bottom_pct"):
        if k in d:
            try:
                d[k] = int(d[k])
            except Exception:
                d.pop(k)
    d.pop("logo_path", None)
    db.update_workspace(wid, **d)
    return jsonify(_ws_public(db.get_workspace(wid)))


@app.delete("/api/workspaces/<int:wid>")
def api_workspace_delete(wid):
    require_admin()
    if db.list_series(wid):
        return jsonify({"ok": False, "msg": "Is workspace mein abhi projects hain — pehle unhe delete karo."})
    if len(db.list_workspaces()) <= 1:
        return jsonify({"ok": False, "msg": "Kam se kam ek workspace chahiye."})
    db.delete_workspace(wid)
    return jsonify({"ok": True})


@app.post("/api/workspaces/<int:wid>/logo")
def api_workspace_logo(wid):
    require_admin()
    import workspaces as wsmod
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith((".png", ".webp")):
        return jsonify({"ok": False, "msg": "Logo PNG (transparent background) daalo."})
    d = wsmod.ref_dir(wid).parent
    p = d / "logo.png"
    from PIL import Image
    try:
        rel = str(p.relative_to(DATA_DIR)).replace("\\", "/")
    except ValueError:
        try:
            rel = str(p.relative_to(BASE)).replace("\\", "/")
        except ValueError:
            rel = str(p).replace("\\", "/")
    db.update_workspace(wid, logo_path=rel, logo_on=1)
    return jsonify({"ok": True, **_ws_public(db.get_workspace(wid))})


@app.get("/api/workspaces/<int:wid>/logo")
def api_workspace_logo_get(wid):
    import workspaces as wsmod
    ws = db.get_workspace(wid)
    p = wsmod.logo_file(ws) if ws else None
    if not p:
        abort(404)
    return send_file(p, mimetype="image/png")


@app.post("/api/workspaces/<int:wid>/templates")
def api_template_create(wid):
    require_admin()
    d = request.get_json(force=True) or {}
    ws = db.get_workspace(wid)
    if not ws:
        abort(404)
    tid = db.create_template(wid, name=(d.get("name") or "New template").strip(), ratio=d.get("ratio") or ws["default_ratio"],
                             layout=d.get("layout") or "free", prompt=d.get("prompt") or "",
                             position=len(db.list_templates(wid)))
    return jsonify(_ws_public(db.get_workspace(wid)))


@app.put("/api/templates/<int:tid>")
def api_template_update(tid):
    require_admin()
    t = db.get_template(tid)
    if not t:
        abort(404)
    d = request.get_json(force=True) or {}
    d.pop("refs", None)
    db.update_template(tid, **d)
    return jsonify(_ws_public(db.get_workspace(t["workspace_id"])))


@app.delete("/api/templates/<int:tid>")
def api_template_delete(tid):
    require_admin()
    t = db.get_template(tid)
    if not t:
        abort(404)
    db.delete_template(tid)
    return jsonify(_ws_public(db.get_workspace(t["workspace_id"])))


@app.post("/api/templates/<int:tid>/refs")
def api_template_refs_add(tid):
    require_admin()
    t = db.get_template(tid)
    if not t:
        abort(404)
    names = _jl(t.get("refs"), []) + _save_ref_files(t["workspace_id"], request.files.getlist("files"))
    db.update_template(tid, refs=json.dumps(names[-8:]))
    return jsonify(_ws_public(db.get_workspace(t["workspace_id"])))


@app.delete("/api/templates/<int:tid>/refs/<name>")
def api_template_refs_del(tid, name):
    require_admin()
    t = db.get_template(tid)
    if not t:
        abort(404)
    db.update_template(tid, refs=json.dumps([n for n in _jl(t.get("refs"), []) if n != name]))
    return jsonify(_ws_public(db.get_workspace(t["workspace_id"])))


@app.get("/api/ref/<int:wid>/<name>")
def api_ref_get(wid, name):
    import workspaces as wsmod
    p = wsmod.ref_dir(wid) / Path(name).name
    if not p.exists():
        abort(404)
    if request.args.get("w"):
        return _cached(send_file(_thumb_for(p, int(request.args.get("w"))), mimetype="image/webp"))
    return send_file(p)


@app.post("/api/series/<int:sid>/refs")
def api_series_refs_add(sid):
    s = db.get_series(sid)
    if not s:
        abort(404)
    names = _jl(s.get("refs"), []) + _save_ref_files(s.get("workspace_id") or 1, request.files.getlist("files"))
    db.update_series(sid, refs=json.dumps(names[-6:]), variant_chats="{}", chat_url="")
    return api_get_series(sid)


@app.delete("/api/series/<int:sid>/refs/<name>")
def api_series_refs_del(sid, name):
    s = db.get_series(sid)
    if not s:
        abort(404)
    db.update_series(sid, refs=json.dumps([n for n in _jl(s.get("refs"), []) if n != name]), variant_chats="{}", chat_url="")
    return api_get_series(sid)


@app.post("/api/series/<int:sid>/build")
def api_series_build(sid):
    """Post builder: table (sheet se copy) -> har post ka brief (VISIBLE TEXT + VISUAL INSTRUCTIONS)."""
    import workspaces as wsmod
    s = db.get_series(sid)
    if not s:
        abort(404)
    d = request.get_json(force=True) or {}
    layout = d.get("layout") or ((db.get_template(s.get("template_id") or 0) or {}).get("layout")) or "grid4"
    if layout not in wsmod.LAYOUT_SPEC:
        return jsonify({"ok": False, "msg": "Is template ka builder nahi hai — Bulk paste use karo."})
    rows = wsmod.parse_table(d.get("table", ""), layout)
    if not rows:
        return jsonify({"ok": False, "msg": "Table khaali hai. Har line = ek row, columns tab ya | se alag."})
    posts = wsmod.build_posts(layout, rows, d.get("title", "").strip(), d.get("subtitle", "").strip())
    if d.get("preview"):
        return jsonify({"ok": True, "posts": [{"label": l, "brief": b} for l, b in posts], "rows": len(rows)})
    if d.get("replace"):
        for it in s["items"]:
            db.delete_item(it["id"])
    for label, brief in posts:
        db.add_item(sid, label, brief, "episode")
    write_excel(sid)
    return jsonify({"ok": True, "created": len(posts), "series": series_public(db.get_series(sid))})


@app.get("/agent/job/<int:jid>/ref/<int:i>")
def agent_ref(jid, i):
    import workspaces as wsmod
    u = agent_user()
    j = _job_for(u, jid)
    refs = wsmod.project_refs(db.get_series(j["series_id"]) or {})
    if i >= len(refs):
        abort(404)
    return send_file(refs[i])


# ---------------- series API ----------------
@app.get("/api/dashboard")
def api_dashboard():
    import stats
    wid = request.args.get("workspace", type=int)
    d = stats.build(series_dir, AGENT_ONLINE_SECS, int(request.args.get("days", 14)), wid)
    d["queue"] = {"state": getattr(worker, "state", "idle"), "current": getattr(worker, "current", None)}
    return jsonify(d)


@app.get("/api/series")
def api_list_series():
    return jsonify(db.list_series(request.args.get("workspace", type=int)))


@app.post("/api/series")
def api_create_series():
    d = request.get_json(force=True) or {}
    name = (d.get("name") or "").strip() or "New project"
    import masters
    import workspaces as wsmod
    ws = db.get_workspace(int(d.get("workspace_id") or 0)) or (db.list_workspaces() or [{}])[0]
    tpl = db.get_template(int(d.get("template_id") or 0)) if d.get("template_id") else None
    if tpl and tpl["workspace_id"] != ws.get("id"):
        tpl = None
    ratio = d.get("ratio") or (tpl or {}).get("ratio") or ws.get("default_ratio") or "1:1"
    chars = _jl(ws.get("characters"), [])
    master = d.get("master_prompt") or wsmod.compose_project_master(ws, tpl, ratio)
    if chars and master.strip():
        master = masters.compose_master(master, chars)
    sid = db.create_series(name, master, d.get("engine", "browser"))
    u = current_user()
    db.update_series(sid, created_by=u["name"] if u else "",
                     run_on="hub" if (not u or u["role"] == "admin") else f"user:{u['id']}",
                     workspace_id=ws.get("id") or 1, template_id=(tpl or {}).get("id") or 0, ratio=ratio,
                     characters=json.dumps(chars, ensure_ascii=False))
    return jsonify(series_public(db.get_series(sid)))


@app.get("/api/series/<int:sid>")
def api_get_series(sid):
    s = db.get_series(sid)
    if not s:
        abort(404)
    s["folder"] = str(series_dir(s).resolve())
    return jsonify(series_public(s))


@app.put("/api/series/<int:sid>")
def api_update_series(sid):
    d = request.get_json(force=True) or {}
    old = db.get_series(sid)
    if not old:
        abort(404)
    for k in ("variant_chats", "chat_url"):
        d.pop(k, None)
    chats = _jl(old.get("variant_chats"), {})
    if d.pop("reset_chat", False):
        chats = {}                                   # "Agli baar nayi chat" = saare variants ki nayi chat
    act = active_of(old)
    if "variants" in d and isinstance(d["variants"], list):
        # variants edit (naam / prompt). Jo variant badla uski purani chat bhool jao.
        oldv = variants_of(old)
        newv = [{"name": str(v.get("name", "")), "angle": str(v.get("angle", "")), "prompt": str(v.get("prompt", ""))}
                for v in d.pop("variants") if isinstance(v, dict)][:6]
        if newv:
            for i, v in enumerate(newv):
                if i >= len(oldv) or v["prompt"] != oldv[i].get("prompt"):
                    chats.pop(str(i), None)
            d["master_variants"] = json.dumps(newv, ensure_ascii=False)
            act = min(act, len(newv) - 1)
            d["active_variant"] = act
            d["master_prompt"] = newv[act]["prompt"]
    if "active_variant" in d:
        n = len(_jl(d.get("master_variants") or old.get("master_variants"), [])) or 1
        act = max(0, min(int(d["active_variant"] or 0), n - 1))
        d["active_variant"] = act
        if "master_prompt" not in d:
            vs = _jl(d.get("master_variants") or old.get("master_variants"), [])
            if vs:
                d["master_prompt"] = vs[act].get("prompt", "")
    if "master_prompt" in d:
        vs = _jl(d.get("master_variants") or old.get("master_variants"), [])
        if vs and 0 <= act < len(vs) and vs[act].get("prompt") != d["master_prompt"]:
            vs[act]["prompt"] = d["master_prompt"]          # textarea edit -> active variant mein bhi
            d["master_variants"] = json.dumps(vs, ensure_ascii=False)
            chats.pop(str(act), None)                         # master badla -> agli baar nayi chat
        elif not vs and d["master_prompt"] != old["master_prompt"]:
            chats.pop(str(act), None)
    if "characters" in d and isinstance(d["characters"], list):
        # character sheet badla -> har master variant mein naya sheet daalo, un sab ki nayi chat
        import masters as pw
        chars = [{"name": str(c.get("name", "")).strip(), "role": str(c.get("role", "")).strip(),
                  "look": str(c.get("look", "")).strip()} for c in d["characters"] if isinstance(c, dict)]
        chars = [c for c in chars if c["name"] or c["look"]][:8]
        d["characters"] = json.dumps(chars, ensure_ascii=False)
        vs = _jl(d.get("master_variants") or old.get("master_variants"), [])
        if not vs:
            vs = [{"name": "A — Master", "angle": "", "prompt": d.get("master_prompt", old.get("master_prompt") or "")}]
        for v in vs:
            v["prompt"] = pw.compose_master(v.get("prompt", ""), chars)
        d["master_variants"] = json.dumps(vs, ensure_ascii=False)
        act = min(act, len(vs) - 1)
        d["master_prompt"] = vs[act]["prompt"]
        chats = {}
    d["variant_chats"] = json.dumps(chats)
    d["chat_url"] = chats.get(str(act), "")
    db.update_series(sid, **d)
    return api_get_series(sid)


@app.delete("/api/series/<int:sid>")
def api_delete_series(sid):
    db.delete_series(sid)
    return jsonify({"ok": True})


@app.post("/api/series/<int:sid>/items")
def api_add_items(sid):
    s = db.get_series(sid)
    if not s:
        abort(404)
    d = request.get_json(force=True) or {}
    created = []
    if d.get("bulk_text") is not None:
        parts = split_bulk(d["bulk_text"])
        has_series = any(i["kind"] == "series" for i in s["items"])
        ep_count = sum(1 for i in s["items"] if i["kind"] == "episode")
        for n, p in enumerate(parts):
            if n == 0 and not has_series and d.get("first_is_series", True):
                kind, label = "series", "Series thumbnail"
            else:
                ep_count += 1
                kind, label = "episode", guess_label(p, f"EP{ep_count:02d}")
            created.append(db.add_item(sid, label, p, kind))
    else:
        kind = d.get("kind", "episode")
        ep_count = sum(1 for i in s["items"] if i["kind"] == "episode")
        label = d.get("label") or ("Series thumbnail" if kind == "series" else f"EP{ep_count + 1:02d}")
        created.append(db.add_item(sid, label, d.get("prompt", ""), kind))
    write_excel(sid)
    return jsonify({"created": created, "series": series_public(db.get_series(sid))})


@app.post("/api/series/<int:sid>/reorder")
def api_reorder(sid):
    ids = (request.get_json(force=True) or {}).get("ids", [])
    db.reorder(sid, [int(i) for i in ids])
    return jsonify({"ok": True})


@app.post("/api/series/<int:sid>/generate")
def api_generate(sid):
    s = db.get_series(sid)
    if not s:
        abort(404)
    d = request.get_json(force=True) or {}
    mode = d.get("mode", "pending")
    items = s["items"]
    if d.get("item_ids"):
        wanted = {int(i) for i in d["item_ids"]}
        ids = [i["id"] for i in items if i["id"] in wanted]
    elif mode == "all":
        ids = [i["id"] for i in items]
    else:
        ids = [i["id"] for i in items if i["status"] in ("pending", "failed")]
    ids = [i for i in ids if (db.get_item(i)["prompt"] or "").strip()]
    if not ids:
        return jsonify({"ok": False, "msg": "Generate karne ko kuch nahi hai (prompt khaali ya sab done)."})
    # v3.5: Regenerate = jo image pehle ban chuki hai use AGLE master variant (alag chat) se banao
    rotate = bool(d.get("rotate", True)) and len(variants_of(s)) > 1
    groups = {}
    for iid in ids:
        it = db.get_item(iid)
        v = next_variant(s, it) if (rotate and (it.get("image_path") or "").strip()) else active_of(s)
        groups.setdefault(v, []).append(iid)
    vnames = [x.get("name") or f"Variant {i + 1}" for i, x in enumerate(variants_of(s))]
    run_on = s.get("run_on") or "hub"
    if s["engine"] == "browser" and run_on.startswith("user:"):
        uid = int(run_on.split(":")[1])
        u = db.get_user(uid)
        if not u:
            return jsonify({"ok": False, "msg": "Jis teammate pe 'Run on' set hai wo ab nahi hai. Run on badlo."})
        if db.active_agent_jobs(series_id=sid):
            return jsonify({"ok": False, "msg": "Is series ka ek job pehle se chal raha hai. Pehle Stop karo ya khatam hone do."})
        for iid in ids:
            db.update_item(iid, status="queued", error="")
        for v, gids in sorted(groups.items()):
            db.create_agent_job(sid, uid, gids, bool(d.get("new_chat")), v)
        online = time.time() - (u["last_seen"] or 0) < AGENT_ONLINE_SECS
        worker.log(f"{len(ids)} thumbnail(s) {u['name']} ke agent ko bheje ("
                   + ", ".join(f"{vnames[v]}: {len(g)}" for v, g in sorted(groups.items())) + ")"
                   + ("" if online else f" — {u['name']} ka agent abhi OFFLINE hai, chalu hote hi shuru hoga"))
        return jsonify({"ok": True, "queued": len(ids), "agent": u["name"], "online": online,
                        "variants": {vnames[v]: len(g) for v, g in groups.items()}})
    for v, gids in sorted(groups.items()):
        worker.enqueue(sid, gids, new_chat=bool(d.get("new_chat")), variant=v)
    return jsonify({"ok": True, "queued": len(ids), "variants": {vnames[v]: len(g) for v, g in groups.items()}})


@app.post("/api/stop")
def api_stop():
    d = request.get_json(silent=True) or {}
    worker.stop()
    for j in db.active_agent_jobs(series_id=d.get("series_id")):
        if j["status"] == "queued":
            finish_agent_job(j["id"], "stopped")
        else:
            db.update_agent_job(j["id"], stop=1)
    return jsonify({"ok": True})


@app.get("/api/status")
def api_status():
    since = int(request.args.get("since", 0))
    with worker.lock:
        logs = [l for l in worker.logs if l["n"] > since]
    reap_lost_jobs()
    agents = []
    for u in db.list_users():
        online = time.time() - (u["last_seen"] or 0) < AGENT_ONLINE_SECS
        jobs = db.active_agent_jobs(user_id=u["id"])
        job = None
        if jobs:
            ser = db.get_series(jobs[0]["series_id"])
            job = {"series_id": jobs[0]["series_id"], "series": ser["name"] if ser else "?",
                   "status": jobs[0]["status"], "label": jobs[0]["current_label"], "waiting": len(jobs) - 1}
        agents.append({"id": u["id"], "name": u["name"], "online": online, "job": job})
    sig = ""
    sid = request.args.get("sid", type=int)
    if sid:
        row = db.q("SELECT COUNT(*) AS n, COALESCE(MAX(updated_at),'') AS m, "
                   "COALESCE(SUM(LENGTH(status)+LENGTH(COALESCE(image_path,''))+LENGTH(COALESCE(poster_path,''))),0) AS z "
                   "FROM items WHERE series_id=?", (sid,), one=True)
        ser = db.q("SELECT COALESCE(chat_url,'') AS c, COALESCE(updated_at,'') AS u FROM series WHERE id=?", (sid,), one=True) or {}
        sig = f"{row['n']}|{row['m']}|{row['z']}|{ser.get('c','')}|{ser.get('u','')}"
    return jsonify({
        "sig": sig,
        "state": worker.state,
        "current": worker.current,
        "queued_jobs": worker.jobs.qsize(),
        "logs": logs,
        "agents": agents,
        "me": current_user_public(),
    })


# ---------------- items API ----------------
@app.put("/api/items/<int:iid>")
def api_update_item(iid):
    d = request.get_json(force=True) or {}
    if d.get("status") not in (None, "pending", "done"):
        d.pop("status", None)
    db.update_item(iid, **d)
    return jsonify(db.get_item(iid))


@app.delete("/api/items/<int:iid>")
def api_delete_item(iid):
    db.delete_item(iid)
    return jsonify({"ok": True})


@app.get("/api/items/<int:iid>/image")
def api_item_image(iid):
    it = db.get_item(iid)
    if not it or not it["image_path"] or not Path(it["image_path"]).exists():
        abort(404)
    return _cached(send_file(it["image_path"]))


THUMB_DIR = OUT / ".thumbs"


def _cached(resp):
    """URL mein ?t=<updated_at> hota hai, isliye browser 1 saal cache kar sakta hai."""
    resp.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return resp


def _thumb_for(path, size):
    src = Path(path)
    st = src.stat()
    import hashlib
    key = hashlib.md5(f"{src.resolve()}|{st.st_mtime_ns}|{st.st_size}|{size}".encode()).hexdigest()
    out = THUMB_DIR / f"{key}.webp"
    if not out.exists():
        imgconv.thumbnail(src, out, size=size)
    return out


@app.get("/api/items/<int:iid>/thumb")
def api_item_thumb(iid):
    """Dashboard ke cards/filmstrip/gallery ke liye chhoti image."""
    it = db.get_item(iid)
    which = request.args.get("of", "image")
    path = it and (it.get("poster_path") if which == "poster" else it["image_path"])
    if not path or not Path(path).exists():
        abort(404)
    size = max(64, min(int(request.args.get("s", 320)), 1024))
    try:
        return _cached(send_file(_thumb_for(path, size), mimetype="image/webp"))
    except Exception:
        return _cached(send_file(path))


@app.post("/api/items/<int:iid>/upload")
def api_upload_image(iid):
    """Manual fallback: ChatGPT/Gemini se khud banayi image yahan drop karo."""
    it = db.get_item(iid)
    f = request.files.get("file")
    if not it or not f:
        abort(400)
    s = db.get_series(it["series_id"])
    settings = load_settings()
    path = series_dir(s) / item_filename(s["items"], it, settings)
    imgconv.write(path, f.read(), int(settings["webp_quality"]))
    if request.form.get("raw") != "1":
        _postprocess(s, path, worker.log)
    db.update_item(iid, status="done", image_path=str(path), error="")
    write_excel(s["id"])
    return jsonify(db.get_item(iid))


@app.post("/api/series/<int:sid>/posters")
def api_posters(sid):
    """Bani hui thumbnails ko Funda Poster Studio site se 2:3 WebP posters banwao."""
    s = db.get_series(sid)
    if not s:
        abort(404)
    d = request.get_json(force=True) or {}
    if d.get("poster_size"):
        save_settings({"poster_size": d["poster_size"]})
    wanted = {int(i) for i in d.get("item_ids", [])}
    ids = [i["id"] for i in s["items"]
           if i["image_path"] and Path(i["image_path"]).exists() and (not wanted or i["id"] in wanted)]
    if not ids:
        return jsonify({"ok": False, "msg": "Pehle thumbnails generate karo — koi bani hui image nahi hai."})
    worker.enqueue_posters(sid, ids)
    return jsonify({"ok": True, "queued": len(ids)})


@app.get("/api/items/<int:iid>/poster")
def api_item_poster(iid):
    it = db.get_item(iid)
    if not it or not it.get("poster_path") or not Path(it["poster_path"]).exists():
        abort(404)
    return _cached(send_file(it["poster_path"]))


@app.post("/api/series/<int:sid>/open-posters")
def api_open_posters(sid):
    s = db.get_series(sid)
    if not s:
        abort(404)
    d = series_dir(s) / "posters"
    d.mkdir(exist_ok=True)
    return _open_path(d)


@app.post("/api/series/<int:sid>/final")
def api_build_final(sid):
    """Final folder dobara banao (naam badle ho to) aur kholo."""
    s = db.get_series(sid)
    if not s:
        abort(404)
    made = build_final(sid, worker.log)
    write_excel(sid)
    d = request.get_json(silent=True) or {}
    res = {"ok": True, "count": len(made), "files": [p.name for p in made],
           "folder": str((series_dir(s) / "final").resolve())}
    if d.get("open"):
        _open_path(series_dir(s) / "final")
    return jsonify(res)


@app.get("/api/series/<int:sid>/final-names")
def api_final_names(sid):
    s = db.get_series(sid)
    if not s:
        abort(404)
    out = {}
    for it in s["items"]:
        b = final_base(s, it)
        out[it["id"]] = [f"{b}.webp", f"{b} (Series Thumbnail).webp"] if it["kind"] == "series" else [f"{b}.webp"]
    return jsonify(out)


@app.post("/api/series/<int:sid>/convert-formats")
def api_convert_formats(sid):
    """Pehle se bani images ko current format settings (series=WebP, episodes=PNG) mein badlo."""
    s = db.get_series(sid)
    if not s:
        abort(404)
    settings = load_settings()
    changed = 0
    for it in s["items"]:
        old = Path(it["image_path"] or "")
        if not it["image_path"] or not old.exists():
            continue
        new = series_dir(s) / item_filename(s["items"], it, settings)
        if new.suffix.lower() == old.suffix.lower() and new == old:
            continue
        imgconv.write(new, old.read_bytes(), int(settings["webp_quality"]))
        if new.resolve() != old.resolve():
            old.unlink(missing_ok=True)
        db.update_item(it["id"], image_path=str(new))
        changed += 1
    write_excel(sid)
    return jsonify({"ok": True, "changed": changed})


# ---------------- export / folder ----------------
@app.get("/api/series/<int:sid>/export")
def api_export(sid):
    path = write_excel(sid)
    if not path:
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)


@app.post("/api/series/<int:sid>/open-folder")
def api_open_folder(sid):
    require_admin()
    s = db.get_series(sid)
    if not s:
        abort(404)
    return _open_path(series_dir(s))


def _open_path(path):
    d = str(Path(path).resolve())
    try:
        if platform.system() == "Windows":
            os.startfile(d)  # noqa
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e), "folder": d})
    return jsonify({"ok": True, "folder": d})


@app.get("/api/settings")
def api_get_settings():
    s = load_settings()
    s["openai_api_key"] = ("•••• " + s["openai_api_key"][-4:]) if s["openai_api_key"] else ""
    return jsonify(s)


@app.put("/api/settings")
def api_put_settings():
    require_admin()
    d = request.get_json(force=True) or {}
    if str(d.get("openai_api_key", "")).startswith("••••"):
        d.pop("openai_api_key")
    save_settings(d)
    return api_get_settings()


# =====================================================================
#                        TEAM: login, users, agents
# =====================================================================
PUBLIC_PATHS = ("/login", "/setup", "/static/", "/agent/", "/favicon")


def current_user():
    uid = session.get("uid")
    return db.get_user(uid) if uid else None


def current_user_public():
    u = current_user()
    return {"id": u["id"], "name": u["name"], "role": u["role"]} if u else None


def require_admin():
    u = current_user()
    if not u or u["role"] != "admin":
        abort(403)


@app.before_request
def _guard():
    path = request.path
    if any(path.startswith(p) for p in PUBLIC_PATHS):
        return None
    if db.count_users() == 0:
        return redirect(url_for("setup_page")) if not path.startswith("/api/") else (jsonify({"error": "setup"}), 401)
    if not current_user():
        session.clear()
        if path.startswith("/api/"):
            return jsonify({"error": "login"}), 401
        return redirect(url_for("login_page"))
    return None


@app.route("/setup", methods=["GET", "POST"])
def setup_page():
    if db.count_users() > 0:
        return redirect(url_for("login_page"))
    err = ""
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        pw = request.form.get("password") or ""
        if len(name) < 2 or len(pw) < 6:
            err = "Naam kam se kam 2 aur password kam se kam 6 characters ka rakho."
        else:
            uid = db.create_user(name, generate_password_hash(pw), "admin", secrets.token_urlsafe(24))
            session.permanent = True
            session["uid"] = uid
            return redirect("/")
    return render_template("auth.html", mode="setup", error=err)


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if db.count_users() == 0:
        return redirect(url_for("setup_page"))
    err = ""
    if request.method == "POST":
        u = db.get_user_by_name((request.form.get("name") or "").strip())
        if u and check_password_hash(u["pw_hash"], request.form.get("password") or ""):
            session.permanent = True
            session["uid"] = u["id"]
            return redirect("/")
        err = "Naam ya password galat hai."
    return render_template("auth.html", mode="login", error=err)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.get("/api/me")
def api_me():
    return jsonify(current_user_public())


@app.post("/api/me/password")
def api_me_password():
    u = current_user()
    d = request.get_json(force=True) or {}
    if not check_password_hash(u["pw_hash"], d.get("old", "")):
        return jsonify({"ok": False, "msg": "Purana password galat hai."})
    if len(d.get("new", "")) < 6:
        return jsonify({"ok": False, "msg": "Naya password kam se kam 6 characters ka ho."})
    db.update_user(u["id"], pw_hash=generate_password_hash(d["new"]))
    return jsonify({"ok": True})


def hub_url_guess():
    if tunnel and tunnel.url:
        return tunnel.url
    pub = (load_settings().get("public_url") or "").strip().rstrip("/")
    if pub:
        return pub
    url = request.host_url.rstrip("/")
    host = request.host.split(":")[0]
    proto = request.headers.get("X-Forwarded-Proto", "").lower()
    if host.endswith(".ts.net") or host.endswith(".trycloudflare.com") or host.endswith(".ngrok-free.app") or host.endswith(".netlify.app") or proto == "https":
        url = "https://" + host  # tunnel / netlify hamesha https hota hai
    return url


@app.get("/api/me/agent-config")
def api_me_agent_config():
    """Teammate apne agent ki config file yahin se download karta hai."""
    u = current_user()
    cfg = {"hub_url": hub_url_guess(), "agent_key": u["agent_key"], "name": u["name"],
           "cdp_url": "http://localhost:9223"}
    buf = io.BytesIO(json.dumps(cfg, indent=2).encode())
    return send_file(buf, as_attachment=True, download_name="agent.json", mimetype="application/json")


@app.get("/api/team")
def api_team():
    me = current_user()
    out = []
    for u in db.list_users():
        out.append({"id": u["id"], "name": u["name"], "role": u["role"],
                    "online": time.time() - (u["last_seen"] or 0) < AGENT_ONLINE_SECS,
                    "last_seen": u["last_seen"]})
    return jsonify({"users": out, "me": current_user_public(), "is_admin": me["role"] == "admin"})


@app.post("/api/team")
def api_team_add():
    require_admin()
    d = request.get_json(force=True) or {}
    name, pw = (d.get("name") or "").strip(), d.get("password") or ""
    if len(name) < 2 or len(pw) < 6:
        return jsonify({"ok": False, "msg": "Naam 2+ aur password 6+ characters ka rakho."})
    if db.get_user_by_name(name):
        return jsonify({"ok": False, "msg": "Is naam ka user pehle se hai."})
    db.create_user(name, generate_password_hash(pw), d.get("role") or "member", secrets.token_urlsafe(24))
    return jsonify({"ok": True})


@app.delete("/api/team/<int:uid>")
def api_team_delete(uid):
    require_admin()
    if uid == current_user()["id"]:
        return jsonify({"ok": False, "msg": "Apne aap ko delete nahi kar sakte."})
    for j in db.active_agent_jobs(user_id=uid):
        finish_agent_job(j["id"], "stopped")
    db.delete_user(uid)
    return jsonify({"ok": True})


@app.post("/api/team/<int:uid>/reset")
def api_team_reset(uid):
    """Admin: teammate ka password badlo / naya agent key do."""
    require_admin()
    d = request.get_json(force=True) or {}
    if d.get("password"):
        if len(d["password"]) < 6:
            return jsonify({"ok": False, "msg": "Password 6+ characters ka ho."})
        db.update_user(uid, pw_hash=generate_password_hash(d["password"]))
    if d.get("new_key"):
        db.update_user(uid, agent_key=secrets.token_urlsafe(24))
    return jsonify({"ok": True})


# ---------------- downloads (teammates ke liye zip) ----------------
@app.get("/api/series/<int:sid>/download/<what>")
def api_download(sid, what):
    s = db.get_series(sid)
    if not s:
        abort(404)
    base = series_dir(s)
    if what == "final":
        build_final(sid, lambda *_: None)
        files = sorted((base / "final").glob("*.webp"))
    elif what == "posters":
        files = sorted(p for p in (base / "posters").glob("*") if p.suffix.lower() in (".webp", ".png", ".jpg", ".jpeg"))
    elif what == "images":
        files = [Path(i["image_path"]) for i in s["items"] if i["image_path"] and Path(i["image_path"]).exists()]
    else:
        abort(404)
    if not files:
        return jsonify({"ok": False, "msg": "Is download mein abhi koi file nahi hai."}), 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.name)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"{clean_name(s['name'])} - {what}.zip",
                     mimetype="application/zip")


# ---------------- agent API (teammate ke laptop wala agent.py) ----------------
def agent_user():
    u = db.get_user_by_key(request.headers.get("X-Agent-Key", ""))
    if not u:
        abort(401)
    db.update_user(u["id"], last_seen=time.time())
    return u


def finish_agent_job(jid, status):
    j = db.get_agent_job(jid)
    if not j:
        return
    for iid in j["item_ids"]:
        it = db.get_item(iid)
        if it and it["status"] in ("queued", "running"):
            db.update_item(iid, status="pending")
    db.update_agent_job(jid, status=status, current_label="")
    write_excel(j["series_id"])


def reap_lost_jobs():
    """Agent 3 min se gayab ho to uska claimed job band karke items pending."""
    for j in db.active_agent_jobs():
        if j["status"] != "claimed":
            continue
        u = db.get_user(j["user_id"])
        if not u or time.time() - (u["last_seen"] or 0) > 180:
            finish_agent_job(j["id"], "lost")
            worker.log(f"Agent ({u['name'] if u else '?'}) offline ho gaya — job ruka, items pending.")


def _job_for(u, jid):
    j = db.get_agent_job(jid)
    if not j or j["user_id"] != u["id"]:
        abort(404)
    return j


@app.post("/agent/hello")
def agent_hello():
    u = agent_user()
    worker.log(f"Agent online: {u['name']}")
    return jsonify({"ok": True, "name": u["name"]})


@app.post("/agent/poll")
def agent_poll():
    u = agent_user()
    jobs = db.active_agent_jobs(user_id=u["id"])
    if not jobs:
        return jsonify({"job": None})
    j = jobs[0]
    s = db.get_series(j["series_id"])
    if not s:
        finish_agent_job(j["id"], "stopped")
        return jsonify({"job": None})
    if j["status"] == "queued":
        db.update_agent_job(j["id"], status="claimed")
        worker.log(f"{u['name']} ke agent ne '{s['name']}' shuru kiya ({len(j['item_ids'])} thumbnail).")
    settings = load_settings()
    items = []
    for iid in j["item_ids"]:
        it = db.get_item(iid)
        if it and it["status"] in ("queued", "running"):
            items.append({"id": it["id"], "label": it["label"], "prompt": it["prompt"],
                          "local_name": f"{final_base(s, it)}.{item_ext(it, settings)}"})
    v = j.get("variant")
    v = active_of(s) if v is None or v < 0 else v % len(variants_of(s))
    return jsonify({"job": {
        "id": j["id"], "series_id": s["id"], "series": s["name"], "series_folder": clean_name(s["name"]),
        "master_prompt": master_for(s, v),
        "refs": [{"url": f"/agent/job/{j['id']}/ref/{i}", "name": Path(p).name}
                 for i, p in enumerate(__import__("workspaces").project_refs(s))] if not chat_for(s, v) or j["new_chat"] else [],
        "chat_url": "" if j["new_chat"] else chat_for(s, v),
        "items": items,
        "settings": {k: settings[k] for k in ("image_prefix", "master_wait", "image_timeout", "gap_seconds", "retries")},
    }})


@app.get("/agent/job/<int:jid>")
def agent_job_state(jid):
    u = agent_user()
    j = _job_for(u, jid)
    return jsonify({"stop": bool(j["stop"]) or j["status"] not in ("queued", "claimed")})


@app.post("/agent/job/<int:jid>/chat")
def agent_job_chat(jid):
    u = agent_user()
    j = _job_for(u, jid)
    url = (request.get_json(force=True) or {}).get("chat_url", "")
    s = db.get_series(j["series_id"])
    v = j.get("variant")
    v = active_of(s) if (v is None or v < 0) else v
    set_chat(j["series_id"], v, url)
    return jsonify({"ok": True})


@app.post("/agent/job/<int:jid>/log")
def agent_job_log(jid):
    u = agent_user()
    _job_for(u, jid)
    msg = str((request.get_json(force=True) or {}).get("msg", ""))[:500]
    worker.log(f"[{u['name']}] {msg}")
    return jsonify({"ok": True})


AGENT_ITEM_START = {}


@app.post("/agent/job/<int:jid>/item/<int:iid>/start")
def agent_item_start(jid, iid):
    u = agent_user()
    j = _job_for(u, jid)
    if iid not in j["item_ids"]:
        abort(404)
    it = db.get_item(iid)
    db.update_item(iid, status="running", error="")
    db.update_agent_job(jid, current_label=it["label"] if it else "")
    AGENT_ITEM_START[(jid, iid)] = time.time()
    return jsonify({"ok": True})


@app.post("/agent/job/<int:jid>/item/<int:iid>/result")
def agent_item_result(jid, iid):
    u = agent_user()
    j = _job_for(u, jid)
    if iid not in j["item_ids"]:
        abort(404)
    it = db.get_item(iid)
    if not it:
        abort(404)
    f = request.files.get("file")
    err = ""
    if f:
        s = db.get_series(it["series_id"])
        settings = load_settings()
        path = series_dir(s) / item_filename(s["items"], it, settings)
        imgconv.write(path, f.read(), int(settings["webp_quality"]))
        _postprocess(s, path, worker.log)
        jv = j.get("variant")
        jv = active_of(s) if (jv is None or jv < 0) else jv
        was_regen = bool((it.get("image_path") or "").strip())
        db.update_item(iid, status="done", image_path=str(path), error="", variant=jv,
                       regen_count=(it.get("regen_count") or 0) + (1 if was_regen else 0))
        worker.log(f"[{u['name']}] {it['label']} saved -> {path.name}")
    else:
        err = str((request.form.get("error") or (request.get_json(silent=True) or {}).get("error") or "Fail"))[:400]
        db.update_item(iid, status="pending" if err == "Stopped" else "failed", error=err)
        worker.log(f"[{u['name']}] {it['label']} fail: {err}")
    t0 = AGENT_ITEM_START.pop((jid, iid), None)
    err_txt = "" if f else err
    if err_txt != "Stopped":
        try:
            db.log_event("thumb", it["series_id"], iid, "browser", u["name"], t0, time.time(), bool(f), 1, err_txt, "",
                         {"variant": j.get("variant"), "regen": bool((it.get("image_path") or "").strip())})
        except Exception:
            pass
    write_excel(it["series_id"])
    return jsonify({"ok": True})


@app.post("/agent/job/<int:jid>/finish")
def agent_job_finish(jid):
    u = agent_user()
    j = _job_for(u, jid)
    finish_agent_job(jid, "done" if not j["stop"] else "stopped")
    worker.log(f"{u['name']} ka job khatam.")
    return jsonify({"ok": True})


# ---------------- one-command agent install (teammates) ----------------
AGENT_FILES = {"agent.py": BASE / "agent" / "agent.py",
               "engine_browser.py": BASE / "engine_browser.py",
               "imgconv.py": BASE / "imgconv.py"}


@app.get("/agent/files/<name>")
def agent_files(name):
    p = AGENT_FILES.get(name)
    if not p or not p.exists():
        abort(404)
    return send_file(p, mimetype="text/x-python", max_age=0)


def _install_script(kind):
    u = db.get_user_by_key(request.args.get("k", ""))
    if not u:
        msg = "Ye command purana hai ya galat hai. Dashboard -> Team & my agent se naya command copy karo."
        body = f'Write-Host "{msg}" -ForegroundColor Red' if kind == "ps1" else f'echo "{msg}"'
        return app.response_class(body, mimetype="text/plain"), 401
    text = render_template(f"agent_install.{kind}", hub=hub_url_guess(), key=u["agent_key"], name=u["name"], v=APP_VERSION)
    if kind == "ps1":
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    return app.response_class(text, mimetype="text/plain")


@app.get("/agent/install.ps1")
def agent_install_ps1():
    return _install_script("ps1")


@app.get("/agent/install.sh")
def agent_install_sh():
    return _install_script("sh")


@app.get("/api/link")
def api_link():
    """Dashboard: aaj ka team link + mera one-line agent command."""
    u = current_user()
    hub = hub_url_guess()
    tunnel_status = tunnel.status if tunnel else ("cloud" if IS_SERVERLESS else "off")
    return jsonify({
        "url": hub,
        "tunnel": {"status": tunnel_status, "error": tunnel.error if tunnel else ""},
        "ps": f'irm "{hub}/agent/install.ps1?k={u["agent_key"]}" | iex',
        "mac": f'curl -fsSL "{hub}/agent/install.sh?k={u["agent_key"]}" | bash',
    })


tunnel = None


def start():
    global worker, tunnel
    db.init()
    import workspaces as wsmod
    wsmod.seed()
    if worker is None:
        worker = Worker()
    if not IS_SERVERLESS and tunnel is None and os.environ.get("KFM_TUNNEL", "1") == "1" and __name__ == "__main__":
        from tunnel import Tunnel
        tunnel = Tunnel(int(os.environ.get("KFM_PORT", "5100")), log=lambda m: worker.log(m) if worker else print(m))
    if tunnel is not None and tunnel.status == "off":
        tunnel.start()


start()

if __name__ == "__main__":
    port = int(os.environ.get("KFM_PORT", "5100"))
    print("\n  [DEV] Gambit — poster & thumbnail studio")
    print(f"  Is PC pe:        http://localhost:{port}")
    print(f"  Teammates ke liye: http://<is-PC-ka-Tailscale-naam-ya-IP>:{port}\n")
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port, threads=16)
    except ImportError:
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
