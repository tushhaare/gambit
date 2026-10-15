"""
KahaniFM Agent — teammate ke laptop pe chalta hai
=================================================
Hub (Sagar ka PC) se kaam uthata hai aur AAPKE APNE logged-in ChatGPT
(Chrome, port 9223) mein thumbnails banwata hai, phir image hub pe bhej deta hai.

Chalane se pehle:
  1. start_chrome.bat  -> ChatGPT mein login
  2. agent.json        -> dashboard ke "Team & my agent" se download karke isi folder mein rakho
  3. run_agent.bat
"""
import json
import queue
import sys
import threading
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from engine_browser import BrowserEngine  # noqa: E402
import imgconv  # noqa: E402

CFG_FILE = HERE / "agent.json"
POLL_SECS = 5


def ts():
    return datetime.now().strftime("%H:%M:%S")


def load_cfg():
    if not CFG_FILE.exists():
        print("\n  agent.json nahi mila!")
        print("  Dashboard kholo -> 'Team & my agent' -> 'Download agent.json'")
        print(f"  aur file is folder mein rakho: {HERE}\n")
        input("  Enter dabao band karne ke liye...")
        sys.exit(1)
    cfg = json.loads(CFG_FILE.read_text(encoding="utf-8-sig"))
    cfg["hub_url"] = cfg["hub_url"].rstrip("/")
    cfg.setdefault("cdp_url", "http://localhost:9223")
    cfg.setdefault("output_dir", str(Path.home() / "Desktop" / "KahaniFM Outputs DEV"))
    return cfg


class Hub:
    def __init__(self, cfg):
        self.url = cfg["hub_url"]
        self.s = requests.Session()
        self.s.headers["X-Agent-Key"] = cfg["agent_key"]
        self.s.headers["ngrok-skip-browser-warning"] = "1"   # ngrok link ho to warning page skip
        self.s.headers["User-Agent"] = "KahaniFM-Agent/1.0"

    def post(self, path, **kw):
        r = self.s.post(self.url + path, timeout=kw.pop("timeout", 30), **kw)
        if r.status_code == 401:
            raise SystemExit("Agent key galat hai / purana hai. Dashboard se naya agent.json download karo.")
        r.raise_for_status()
        return r.json()

    def get(self, path):
        r = self.s.get(self.url + path, timeout=20)
        r.raise_for_status()
        return r.json()


class Agent:
    def __init__(self, cfg):
        self.cfg = cfg
        self.hub = Hub(cfg)
        self.job = None
        self._stop_cache = (0, False)
        self._logq = queue.Queue()
        threading.Thread(target=self._log_sender, daemon=True).start()

    # -- logging: console + hub ka live log (background mein, kaam ko rokta nahi) --
    def log(self, msg):
        print(f"[{ts()}] {msg}", flush=True)
        if self.job:
            self._logq.put((self.job["id"], msg))

    def _log_sender(self):
        while True:
            jid, msg = self._logq.get()
            try:
                self.hub.post(f"/agent/job/{jid}/log", json={"msg": msg}, timeout=10)
            except Exception:
                pass

    def should_stop(self):
        t, val = self._stop_cache
        if time.time() - t < 5:
            return val
        try:
            val = bool(self.hub.get(f"/agent/job/{self.job['id']}")["stop"])
        except Exception:
            val = False
        self._stop_cache = (time.time(), val)
        return val

    def save_local(self, job, it, src):
        """Apne laptop pe bhi copy: <Outputs>/<Series>/<Episode Name>.png (series thumbnail .webp)."""
        try:
            folder = Path(self.cfg["output_dir"]) / (job.get("series_folder") or job["series"])
            folder.mkdir(parents=True, exist_ok=True)
            name = it.get("local_name") or f"{it['id']}.png"
            imgconv.write(folder / name, src.read_bytes())
            print(f"[{ts()}]   ↳ saved: {folder / name}", flush=True)
        except Exception as e:
            print(f"[{ts()}]   ↳ local copy save nahi hui: {e}", flush=True)

    def run_job(self, job):
        self.job = job
        self._stop_cache = (0, False)
        jid = job["id"]
        settings = dict(job["settings"])
        settings["cdp_url"] = self.cfg["cdp_url"]
        self.log(f"=== {job['series']} — {len(job['items'])} thumbnail ===")
        engine = BrowserEngine(settings, self.log)
        tmp = Path(tempfile.mkdtemp(prefix="kfm_"))
        try:
            url = engine.open(job.get("chat_url") or "")
            if job.get("chat_url"):
                self.log("Purani chat khuli (master pehle se usme hai)")
            else:
                if (job.get("master_prompt") or "").strip():
                    refs = []
                    for i, r in enumerate(job.get("refs") or []):     # Gambit: reference images hub se lo
                        try:
                            rr = self.hub.s.get(self.hub.url + r["url"], timeout=60)
                            if rr.status_code == 200 and len(rr.content) > 1000:
                                f = tmp / f"ref{i}_{Path(r.get('name') or 'ref.png').name}"
                                f.write_bytes(rr.content)
                                refs.append(str(f))
                        except Exception as e:
                            self.log(f"Reference download nahi hua: {e}")
                    engine.send_master(job["master_prompt"], refs)
                self.hub.post(f"/agent/job/{jid}/chat", json={"chat_url": engine.current_url()})
                self.log(f"Nayi chat: {engine.current_url()}")

            for it in job["items"]:
                if self.should_stop():
                    self.log("Stop mila — ruk raha hoon.")
                    break
                self.hub.post(f"/agent/job/{jid}/item/{it['id']}/start")
                out = tmp / f"{it['id']}.raw"   # ChatGPT ki original file, bina conversion (chhoti + tez upload)
                ok, err = False, ""
                for attempt in range(int(settings.get("retries", 1)) + 1):
                    if self.should_stop():
                        err = "Stopped"
                        break
                    self.log(f"[{it['label']}] bhej raha hoon (try {attempt + 1})...")
                    try:
                        ok, err = engine.generate(it["prompt"], out, self.should_stop)
                    except Exception as e:
                        ok, err = False, str(e)
                    if ok:
                        break
                    self.log(f"[{it['label']}] fail: {err}")
                    try:
                        engine.page.goto(engine.current_url())
                        engine.page.wait_for_timeout(5000)
                    except Exception:
                        pass
                if ok and out.exists():
                    self.save_local(job, it, out)
                    with open(out, "rb") as f:
                        self.hub.post(f"/agent/job/{jid}/item/{it['id']}/result",
                                      files={"file": (out.name, f, "application/octet-stream")}, timeout=180)
                    self.log(f"[{it['label']}] hub pe bhej di ✓")
                else:
                    self.hub.post(f"/agent/job/{jid}/item/{it['id']}/result", data={"error": err or "Fail"})
                if not self.should_stop():
                    time.sleep(int(settings.get("gap_seconds", 8)))
        except SystemExit:
            raise
        except Exception as e:
            self.log(f"Job error: {e}")
        finally:
            engine.close()
            try:
                self.hub.post(f"/agent/job/{jid}/finish")
            except Exception:
                pass
            self.job = None

    def loop(self):
        print("\n  KahaniFM DEV Agent (test version)")
        print(f"  Hub: {self.cfg['hub_url']}")
        print(f"  Outputs: {self.cfg['output_dir']}")
        while True:
            try:
                r = self.hub.post("/agent/hello")
                print(f"  Logged in as: {r['name']}  —  kaam ka intezaar...\n  (ye window khuli rakho; band karne ke liye Ctrl+C)\n")
                break
            except SystemExit:
                raise
            except Exception as e:
                print(f"[{ts()}] Hub se connect nahi ho paya ({e}). Tailscale on hai? 15s mein dobara...")
                time.sleep(15)
        while True:
            try:
                job = self.hub.post("/agent/poll").get("job")
                if job and job.get("items"):
                    self.run_job(job)
                elif job:
                    self.hub.post(f"/agent/job/{job['id']}/finish")
                else:
                    time.sleep(POLL_SECS)
            except SystemExit:
                raise
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[{ts()}] Hub error: {e} — 15s mein dobara")
                time.sleep(15)


if __name__ == "__main__":
    try:
        Agent(load_cfg()).loop()
    except KeyboardInterrupt:
        print("\nAgent band.")
    except SystemExit as e:
        if str(e):
            print(f"\n  {e}\n")
            input("  Enter dabao band karne ke liye...")
