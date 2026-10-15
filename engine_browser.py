"""
Engine 1: ChatGPT in your own logged-in Chrome (via Chrome DevTools port 9223).

Chrome must be started with --remote-debugging-port=9223 (use start_chrome.bat).
All briefs of a series go into ONE chat, after the master prompt, so the
characters and style stay consistent.
"""
import base64
import time

import imgconv
from pathlib import Path


MASTER_SUFFIX = ("IMPORTANT: Do NOT generate any image for this message. These are only the rules for this chat. "
                 "Reply with just one line: \"READY — rules samajh gaya, brief bhejo.\" "
                 "Generate an image only when I send a brief.")


class BrowserEngine:
    def __init__(self, settings, log):
        self.s = settings
        self.log = log
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None

    # ---------- lifecycle ----------
    def open(self, chat_url=""):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.connect_over_cdp(self.s["cdp_url"])
        except Exception as e:
            raise RuntimeError(
                "Chrome (ChatGPT wala) band hai ya connect nahi hua. Dashboard se command dobara chalao ya start_chrome.bat "
                f"(port 9223). Details: {e}"
            )
        self.context = self.browser.contexts[0]
        self.page = self.context.new_page()
        self.page.goto(chat_url or "https://chatgpt.com/")
        self.page.wait_for_timeout(4000)
        self.get_prompt_box()
        return self.page.url

    def close(self):
        try:
            if self.page:
                self.page.close()  # sirf tab band, aapka Chrome khula rahega
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def current_url(self):
        return self.page.url if self.page else ""

    def screenshot(self, path):
        try:
            self.page.screenshot(path=str(path))
        except Exception:
            pass

    # ---------- page helpers ----------
    def get_prompt_box(self, timeout=60):
        page = self.page
        candidates = [
            lambda: page.get_by_role("textbox", name="Ask ChatGPT"),
            lambda: page.get_by_placeholder("Ask ChatGPT"),
            lambda: page.locator("#prompt-textarea"),
            lambda: page.locator('div[contenteditable="true"]'),
            lambda: page.get_by_role("textbox"),
            lambda: page.locator("textarea"),
        ]
        end = time.time() + timeout
        while time.time() < end:
            for make in candidates:
                try:
                    box = make().first
                    if box.is_visible():
                        return box
                except Exception:
                    pass
            page.keyboard.press("Escape")
            page.wait_for_timeout(700)
        raise RuntimeError("ChatGPT ka prompt box nahi mila (login / popup check karo).")

    def attach(self, files):
        """Reference images ChatGPT message mein attach karo (hidden file input se). Fail ho to bina refs ke chalo."""
        files = [str(f) for f in (files or []) if Path(f).exists()]
        if not files:
            return 0
        try:
            inputs = self.page.locator('input[type="file"]')
            n = inputs.count()
            target = None
            for i in range(n):
                acc = (inputs.nth(i).get_attribute("accept") or "")
                if not acc or "image" in acc or "*" in acc:
                    target = inputs.nth(i)
                    break
            if target is None:
                self.log("Reference upload ka input nahi mila — bina reference ke bhej raha hoon.")
                return 0
            target.set_input_files(files)
            # upload poora hone do: thumbnails aayein aur send button enable ho
            end = time.time() + 30 + 10 * len(files)
            self.page.wait_for_timeout(2500)
            while time.time() < end:
                busy = self.page.locator('[role="progressbar"], [aria-label*="Uploading"], circle[class*="progress"]')
                if not busy.count():
                    break
                self.page.wait_for_timeout(1000)
            self.page.wait_for_timeout(1500)
            self.log(f"{len(files)} reference image(s) attach ki.")
            return len(files)
        except Exception as e:
            self.log(f"Reference attach nahi hua ({str(e)[:100]}) — bina reference ke bhej raha hoon.")
            return 0

    def send(self, text, files=None):
        if files:
            self.attach(files)
        box = self.get_prompt_box()
        box.click()
        self.page.wait_for_timeout(300)
        self.page.keyboard.insert_text(text)
        self.page.wait_for_timeout(600)
        self.page.keyboard.press("Enter")

    def images(self):
        return self.page.evaluate(
            """() => Array.from(document.querySelectorAll('main img'))
                  .filter(i => i.complete && i.naturalWidth >= 400 && i.naturalHeight >= 400)
                  .map(i => i.currentSrc || i.src)
                  .filter(s => s && !s.startsWith('data:'))"""
        )

    def is_generating(self):
        for sel in ['[data-testid="stop-button"]', 'button[aria-label*="Stop"]', 'button[aria-label*="stop"]']:
            try:
                if self.page.locator(sel).first.is_visible():
                    return True
            except Exception:
                pass
        return False

    def wait_reply(self, seconds):
        self.page.wait_for_timeout(4000)
        end = time.time() + seconds
        while time.time() < end and self.is_generating():
            self.page.wait_for_timeout(2000)
        self.page.wait_for_timeout(2000)

    def wait_new_image(self, before, timeout, stop_flag):
        end = time.time() + timeout
        last, since = None, None
        while time.time() < end:
            if stop_flag():
                return None
            new = [s for s in self.images() if s not in before]
            if new:
                newest = new[-1]
                if newest == last:
                    if since and time.time() - since > 6 and not self.is_generating():
                        return newest
                else:
                    last, since = newest, time.time()
            self.page.wait_for_timeout(2000)
        return None

    # ---------- saving the REAL image file ----------
    def _fetch_in_page(self, src):
        """Logged-in ChatGPT page ke andar se hi image fetch karo (cookies/login ke saath)."""
        data = self.page.evaluate(
            """async (src) => {
                const r = await fetch(src, {credentials: 'include'});
                if (!r.ok) return null;
                const b = await r.blob();
                if (b.size < 20000) return null;
                return await new Promise(res => {
                    const fr = new FileReader();
                    fr.onload = () => res(fr.result);
                    fr.readAsDataURL(b);
                });
            }""",
            src,
        )
        if data and "," in data:
            return base64.b64decode(data.split(",", 1)[1])
        return None

    def _canvas_in_page(self, src):
        """Fallback: already-loaded <img> ko full resolution canvas pe draw karke PNG lo."""
        data = self.page.evaluate(
            """(src) => {
                const img = Array.from(document.querySelectorAll('main img'))
                    .reverse().find(i => (i.currentSrc || i.src) === src);
                if (!img) return null;
                const c = document.createElement('canvas');
                c.width = img.naturalWidth; c.height = img.naturalHeight;
                c.getContext('2d').drawImage(img, 0, 0);
                try { return c.toDataURL('image/png'); } catch (e) { return null; }
            }""",
            src,
        )
        if data and "," in data:
            return base64.b64decode(data.split(",", 1)[1])
        return None

    def _download_button(self, src, path):
        """Fallback: image pe hover karke ChatGPT ka Download button dabao."""
        img = self.page.locator("main img").last
        for i in self.page.locator("main img").all()[::-1]:
            try:
                if (i.get_attribute("src") or "") == src:
                    img = i
                    break
            except Exception:
                pass
        img.scroll_into_view_if_needed()
        img.hover()
        self.page.wait_for_timeout(800)
        btn = None
        for sel in ['button[aria-label*="Download"]', 'button[aria-label*="download"]',
                    'a[download]', '[data-testid*="download"]']:
            loc = self.page.locator(sel)
            if loc.count():
                btn = loc.last
                break
        if not btn:
            return False
        with self.page.expect_download(timeout=30000) as dl:
            btn.click()
        dl.value.save_as(str(path))
        imgconv.write(path, Path(path).read_bytes(), int(self.s.get('webp_quality', 92)))
        return Path(path).stat().st_size > 20000

    def save(self, src, path):
        attempts = [
            ("page-fetch", lambda: self._fetch_in_page(src)),
            ("api-request", lambda: (lambda r: r.body() if r.ok and len(r.body()) > 20000 else None)(self.context.request.get(src))),
            ("canvas", lambda: self._canvas_in_page(src)),
        ]
        for name, fn in attempts:
            try:
                data = fn()
                if data:
                    imgconv.write(path, data, int(self.s.get('webp_quality', 92)))
                    self.log(f"Original image save hui ({name}, {len(data)//1024} KB)")
                    return True
            except Exception as e:
                self.log(f"{name} se save nahi hua: {str(e)[:120]}")
        try:
            if self._download_button(src, path):
                self.log("Download button se original image save hui")
                return True
        except Exception as e:
            self.log(f"Download button se nahi hua: {str(e)[:120]}")
        self.log("Original image nahi mil payi — item FAILED mark kar raha hoon (screenshot save nahi karunga).")
        return False

    # ---------- public API used by the worker ----------
    def send_master(self, master, files=None):
        self.log("Master prompt bhej raha hoon (sirf READY reply maangta hoon, image nahi)...")
        suffix = self.s.get("master_suffix", MASTER_SUFFIX)
        text = master.rstrip()
        if files:
            text += ("\n\nREFERENCE IMAGES (attached): these are approved examples of this brand's style. Match their "
                     "look — layout feel, typography weight, colours, illustration style and characters — but never copy "
                     "their text; every image uses only the text I send in its brief.")
        self.send(text + ("\n\n" + suffix if suffix else ""), files)
        self.wait_reply(int(self.s["master_wait"]))

    def generate(self, prompt, out_path, stop_flag):
        before = set(self.images())
        self.send(self.s["image_prefix"] + prompt)
        src = self.wait_new_image(before, int(self.s["image_timeout"]), stop_flag)
        if not src:
            return False, "Image nahi aayi (ChatGPT ne mana kiya ya timeout)."
        if self.save(src, out_path):
            return True, ""
        return False, "Image save nahi ho payi."
