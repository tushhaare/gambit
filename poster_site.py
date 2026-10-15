"""
Funda Poster Studio automation
==============================
https://funda-audio-thumbnail-gen.vercel.app/  (square thumbnail -> 2:3 poster with
vinyl/CD layer; sab kuch browser ke andar hota hai, koi login nahi chahiye).

Flow: site kholo -> saari images upload -> poster size + WebP chuno ->
"Generate posters" -> zip download -> outputs/<series>/posters/ mein extract.

Browser: pehle aapka installed Google Chrome alag (headless) mode mein chalata hai,
taaki aapki ChatGPT wali window disturb na ho. Na chale to port-9223 wale Chrome
mein naya tab kholta hai.
"""
import re
import time
import zipfile
from pathlib import Path


def _click_option(page, pattern, log, what):
    """Radio / button / select / label — jo bhi ho, us option ko chuno."""
    rx = re.compile(pattern, re.I)
    tries = [
        lambda: page.get_by_role("radio", name=rx).first.check(timeout=1500),
        lambda: page.get_by_role("button", name=rx).first.click(timeout=1500),
        lambda: page.get_by_role("tab", name=rx).first.click(timeout=1500),
        lambda: page.get_by_label(rx).first.check(timeout=1500),
        lambda: page.get_by_text(rx).first.click(timeout=1500),
    ]
    for t in tries:
        try:
            t()
            log(f"Poster site: {what} chuna")
            return True
        except Exception:
            pass
    # <select> dropdown
    try:
        for sel in page.locator("select").all():
            for opt in sel.locator("option").all():
                label = (opt.inner_text() or "") + " " + (opt.get_attribute("value") or "")
                if rx.search(label):
                    sel.select_option(label=opt.inner_text().strip())
                    log(f"Poster site: {what} chuna (dropdown)")
                    return True
    except Exception:
        pass
    log(f"Poster site: '{what}' option nahi mila — default hi rahega")
    return False


def _open_page(pw, settings, log):
    """Returns (browser, context, page, close_fn)."""
    headless = bool(int(settings.get("poster_headless", 1)))
    for channel in ("chrome", "msedge", None):
        try:
            kw = {"headless": headless}
            if channel:
                kw["channel"] = channel
            b = pw.chromium.launch(**kw)
            ctx = b.new_context(accept_downloads=True, viewport={"width": 1400, "height": 1000})
            log(f"Poster site: {channel or 'chromium'} browser khula")
            return b, ctx, ctx.new_page(), b.close
        except Exception:
            continue
    # fallback: aapka port-9223 wala Chrome
    b = pw.chromium.connect_over_cdp(settings["cdp_url"])
    ctx = b.contexts[0]
    page = ctx.new_page()
    log("Poster site: port-9223 wale Chrome mein naya tab khola")
    return b, ctx, page, page.close


def make_posters(settings, files, out_dir, log, stop_flag=lambda: False):
    """files: list of image paths. Returns list of saved poster paths."""
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    url = settings.get("poster_site_url") or "https://funda-audio-thumbnail-gen.vercel.app/"
    size = settings.get("poster_size", "1000x1500")
    dims = re.findall(r"\d+", size)
    w, h = (dims[0], dims[1]) if len(dims) >= 2 else ("1000", "1500")
    timeout = int(settings.get("poster_timeout", 300))

    with sync_playwright() as pw:
        browser, ctx, page, close = _open_page(pw, settings, log)
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # 1) upload
            inp = page.locator('input[type="file"]').first
            inp.wait_for(state="attached", timeout=30000)
            inp.set_input_files([str(f) for f in files])
            log(f"Poster site: {len(files)} image(s) upload ki")
            page.wait_for_timeout(2500 + 300 * len(files))

            # 2) settings
            _click_option(page, rf"{w}\D{{1,6}}{h}", log, f"size {w}×{h}")
            _click_option(page, rf"^\s*{fmt}\b", log, fmt.upper())
            page.wait_for_timeout(800)

            # 3) generate + download
            downloads = []
            page.on("download", lambda d: downloads.append(d))
            page.get_by_role("button", name=re.compile(r"generate", re.I)).first.click()
            log("Poster site: 'Generate posters' dabaya, wait kar raha hoon...")
            clicked_dl = False
            end = time.time() + timeout
            while time.time() < end and not downloads:
                if stop_flag():
                    raise RuntimeError("Stopped")
                if not clicked_dl:
                    try:
                        btn = page.get_by_role("button", name=re.compile(r"download", re.I)).first
                        if btn.is_visible() and btn.is_enabled():
                            btn.click()
                            clicked_dl = True
                    except Exception:
                        try:
                            a = page.get_by_role("link", name=re.compile(r"download", re.I)).first
                            if a.is_visible():
                                a.click()
                                clicked_dl = True
                        except Exception:
                            pass
                page.wait_for_timeout(1500)
            if not downloads:
                page.screenshot(path=str(out_dir / "poster_site_error.png"), full_page=True)
                raise RuntimeError("Poster site se download nahi aaya (poster_site_error.png dekho).")

            # 4) save + extract
            page.wait_for_timeout(1500)  # multiple files ho to aa jaayein
            saved = []
            for d in downloads:
                name = d.suggested_filename or "posters.zip"
                target = out_dir / name
                d.save_as(str(target))
                if target.suffix.lower() == ".zip" or zipfile.is_zipfile(target):
                    with zipfile.ZipFile(target) as z:
                        for m in z.infolist():
                            if m.is_dir() or not re.search(r"\.(webp|png|jpe?g)$", m.filename, re.I):
                                continue
                            p = out_dir / Path(m.filename).name
                            p.write_bytes(z.read(m))
                            saved.append(p)
                    log(f"Poster site: zip mila ({name}), {len(saved)} poster extract kiye")
                else:
                    saved.append(target)
            return saved
        finally:
            try:
                close()
            except Exception:
                pass
