"""
Free temporary public link (Cloudflare Quick Tunnel)
===================================================
run.bat chalate hi ye cloudflared chalata hai aur ek naya link deta hai:
    https://<random-words>.trycloudflare.com
- Koi account / domain / paisa nahi.
- Har baar hub start karne pe naya link (temporary) — jab tak run.bat chalu hai tab tak link chalu.
- cloudflared.exe pehli baar apne aap download hota hai (tools/ folder mein).
"""
import os
import platform
import re
import shutil
import stat
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
TOOLS = BASE / "tools"
URL_RE = re.compile(r"https://[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com")  # quick links hamesha word-word-word hote hain (api.* nahi)

DOWNLOADS = {
    ("Windows", "AMD64"): "cloudflared-windows-amd64.exe",
    ("Windows", "x86"): "cloudflared-windows-386.exe",
    ("Linux", "x86_64"): "cloudflared-linux-amd64",
    ("Linux", "aarch64"): "cloudflared-linux-arm64",
}
RELEASE = "https://github.com/cloudflare/cloudflared/releases/latest/download/"


class Tunnel:
    def __init__(self, port, log=print):
        self.port = port
        self.log = log
        self.url = ""
        self.status = "off"      # off | starting | on | error
        self.error = ""
        self.proc = None

    # ---------- cloudflared binary ----------
    def binary(self):
        found = shutil.which("cloudflared")
        if found:
            return found
        sysname, machine = platform.system(), platform.machine()
        name = DOWNLOADS.get((sysname, machine))
        if sysname == "Darwin":
            raise RuntimeError("Mac pe ek baar Terminal mein chalao:  brew install cloudflared")
        if not name:
            raise RuntimeError(f"Is system ({sysname} {machine}) ke liye cloudflared khud install karo.")
        TOOLS.mkdir(exist_ok=True)
        target = TOOLS / ("cloudflared.exe" if sysname == "Windows" else "cloudflared")
        if not target.exists():
            self.log("cloudflared download ho raha hai (sirf pehli baar, ~20 MB)...")
            tmp = target.with_suffix(".part")
            urllib.request.urlretrieve(RELEASE + name, tmp)
            tmp.replace(target)
            if sysname != "Windows":
                target.chmod(target.stat().st_mode | stat.S_IEXEC)
        return str(target)

    # ---------- run ----------
    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            self.status, self.url, self.error = "starting", "", ""
            try:
                exe = self.binary()
                flags = 0x08000000 if platform.system() == "Windows" else 0  # CREATE_NO_WINDOW
                self.proc = subprocess.Popen(
                    [exe, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{self.port}"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags,
                )
                for line in self.proc.stdout:
                    m = URL_RE.search(line)
                    if m and not self.url:
                        self.url = m.group(0)
                        self.status = "on"
                        self.log(f"TEAM LINK READY:  {self.url}")
                        print("\n" + "=" * 64 + f"\n   TEAM LINK:  {self.url}\n" + "=" * 64 + "\n", flush=True)
                self.proc.wait()
                if not self.url:
                    self.status, self.error = "error", "Cloudflare link nahi mila (internet / firewall check karo)."
                self.log("Team link band ho gaya — 10 second mein dobara bana raha hoon...")
            except Exception as e:
                self.status, self.error = "error", str(e)
                self.log(f"Team link nahi ban paya: {e}")
                if "brew install" in str(e) or "khud install" in str(e):
                    return
            time.sleep(10)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
