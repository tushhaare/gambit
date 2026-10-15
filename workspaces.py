"""
Gambit — workspaces (KahaniFM, SpeakEasy, ...), templates, master prompt composition,
post builder (table -> briefs) aur image post-processing (exact ratio + logo).
"""
import json
import os
import re
from pathlib import Path

import db

BASE = Path(__file__).parent
IS_SERVERLESS = os.environ.get("IS_SERVERLESS", "").lower() in ("1", "true") or bool(os.environ.get("NETLIFY") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
DEFAULT_DATA_DIR = Path("/tmp/kfm_data") if IS_SERVERLESS else BASE
DATA_DIR = Path(os.environ.get("DATA_DIR", str(DEFAULT_DATA_DIR)))
SEEDS = BASE / "seeds"

RATIOS = {
    "1:1": (1, 1, "square"),
    "4:5": (4, 5, "vertical portrait (Instagram feed)"),
    "3:4": (3, 4, "vertical portrait"),
    "2:3": (2, 3, "vertical portrait (app poster)"),
    "9:16": (9, 16, "tall vertical (reels / stories)"),
    "16:9": (16, 9, "wide landscape (YouTube)"),
}
LAYOUTS = {
    "free": "Free (brief khud likho)",
    "grid4": "2×2 grid — word + Hindi + sentence",
    "phrase4": "2×2 phrase cards — Hindi + English",
    "word": "Single word card",
    "compare2": "2-object comparison",
}
# builder: kitni rows ek post mein, aur table ke columns
LAYOUT_SPEC = {
    "grid4": {"per_post": 4, "cols": ["word", "hindi", "sentence", "visual"]},
    "phrase4": {"per_post": 4, "cols": ["hindi", "english", "visual"]},
    "word": {"per_post": 1, "cols": ["word", "hindi", "sentence", "visual"]},
    "compare2": {"per_post": 2, "cols": ["hindi", "english", "visual"]},
}
PANEL_TINTS = ["butter yellow #FFF0BD", "pastel sky blue #D9F0FF", "pastel blush pink #FFE0E8", "pastel mint green #E8F8D5"]
POSITIONS = ["top-left", "top-right", "bottom-left", "bottom-right"]


def _read(name):
    try:
        return (SEEDS / name).read_text(encoding="utf-8")
    except Exception:
        return ""


SPEAKEASY_CHARACTERS = [
    {"name": "ANAYA", "role": "recurring girl",
     "look": "college student around 19, long voluminous wavy dark-brown hair, big expressive brown eyes, warm wheatish "
             "skin, rosy cheeks, friendly smile; usually a pink or lavender chunky knit sweater with blue jeans and a "
             "black backpack"},
    {"name": "VIVAAN", "role": "recurring boy",
     "look": "college student around 19, short messy curly black hair, big brown eyes, warm wheatish skin, expressive "
             "eyebrows; usually an olive-green jacket over a white tee or a mustard-yellow hoodie, black backpack"},
]

TEMPLATE_SEEDS = {
    "kahanifm": [
        {"name": "Series & episode thumbnails", "ratio": "1:1", "layout": "free", "prompt": ""},
    ],
    "speakeasy": [
        {"name": "Made Easy — 2×2 grid", "ratio": "3:4", "layout": "grid4", "prompt": """FORMAT: "MADE EASY" 2×2 LESSON GRID
- Top: big bold navy heading in chunky rounded capitals with a golden-yellow brush underline and small golden tick marks on both sides; one smaller navy subtitle line below it.
- Below: four large rounded cards in a 2×2 grid, generous gaps, each tinted with one pastel (butter yellow, sky blue, blush pink, mint green — in that order).
- Each card: (1) the English word huge in bold navy rounded sans at the top-left on a tinted label, (2) the Hindi meaning in Devanagari right below it on a smaller tinted chip, (3) a scene illustration filling the card that shows the meaning, with one tiny golden doodle accent, (4) a white rounded strip at the bottom with the example sentence in bold navy where the keyword sits inside a golden-yellow rounded pill in CAPITALS.
- Illustration style: polished stylized 3D animated-film look (original characters, not any studio's), warm natural daylight, soft depth of field, real Indian everyday settings.
- Hindi translations ARE part of the visible text in this format. The recurring characters may appear when a person is needed; use animals or objects when they explain the word better."""},
        {"name": "Phrase cards — Hindi + English", "ratio": "3:4", "layout": "phrase4", "prompt": """FORMAT: 2×2 DAILY-PHRASE CARDS (no heading)
- Four large rounded cards in a 2×2 grid on a warm-white background, generous gaps.
- Each card: a scene illustration on top (about 65% of the card) showing the situation of the phrase, then two stacked rounded text bands: the Hindi sentence in bold navy Devanagari on a pastel band, and the English sentence in bold navy on a lighter band of the same tint.
- Card tints in order: butter yellow, sky blue, lavender, mint green.
- Illustration style: polished stylized 3D animated-film look (original characters), cosy warm indoor daylight, expressive faces, small yellow doodle accents or a simple speech/thought bubble only when it explains the phrase.
- Hindi IS part of the visible text in this format. Use the recurring characters ANAYA and VIVAAN."""},
        {"name": "Word card — minimal", "ratio": "3:4", "layout": "word", "prompt": """FORMAT: MINIMAL SINGLE-WORD CARD
- Plain pure-white background, lots of empty space, everything centred.
- The English word huge in heavy black geometric sans at the top third; the Hindi meaning in thin dark-grey Devanagari just below it.
- In the middle, one simple flat vector illustration with thick dark outlines and a few flat colours (blue, golden yellow, green, red) that shows the meaning; two or three tiny yellow motion marks at most. No 3D, no background scenery.
- At the bottom (above the empty branding strip), the example sentence in a light grey sans with the keyword in bold black.
- Hindi IS part of the visible text in this format."""},
        {"name": "Vocab compare — 2 objects", "ratio": "3:4", "layout": "compare2", "prompt": """FORMAT: TWO-OBJECT VOCABULARY COMPARISON
- Warm-cream background split into two equal columns by one thin light-grey vertical line.
- Top of each column: the Hindi word in bold navy Devanagari inside a butter-yellow rounded rectangle.
- Middle of each column: one photorealistic studio product shot of the object, soft shadow, no props, same scale and lighting for both.
- Bottom of each column: the English name in bold navy rounded sans (may wrap to two lines).
- No heading, no extra labels. Hindi IS part of the visible text in this format."""},
    ],
}


def seed():
    """Pehli baar: KahaniFM (purani saari series yahin) + SpeakEasy workspace banao."""
    if db.list_workspaces():
        return
    k = db.create_workspace(name="KahaniFM", kind="kahanifm", project_label="Series", color="#F7A928",
                            default_ratio="1:1", base_prompt=_read("kahanifm_base.md"), position=0,
                            logo_on=0, fit_mode="off", safe_bottom_pct=0)
    s = db.create_workspace(name="SpeakEasy AI", kind="speakeasy", project_label="Post set", color="#FFBE32",
                            default_ratio="3:4", base_prompt=_read("speakeasy_base.md"), position=1,
                            characters=json.dumps(SPEAKEASY_CHARACTERS), logo_on=1, logo_width_pct=30,
                            safe_bottom_pct=10, fit_mode="crop")
    for wid, kind in ((k, "kahanifm"), (s, "speakeasy")):
        for i, t in enumerate(TEMPLATE_SEEDS[kind]):
            db.create_template(wid, position=i, **t)
    db.ex("UPDATE series SET workspace_id=? WHERE workspace_id IS NULL OR workspace_id=0 OR workspace_id=1", (k,))


def _jl(t, d):
    try:
        v = json.loads(t or "")
        return v if isinstance(v, type(d)) else d
    except Exception:
        return d


def ratio_line(ratio):
    r = RATIOS.get(ratio)
    if not r:
        return ""
    w, h, desc = r
    return f"CANVAS: every image is {ratio} {desc}. Keep all text and important elements inside safe margins."


def compose_project_master(ws, tpl, ratio):
    """Naye project ka master = workspace rules + template format + canvas."""
    parts = [(ws.get("base_prompt") or "").strip()]
    if tpl and (tpl.get("prompt") or "").strip():
        parts.append(tpl["prompt"].strip())
    rl = ratio_line(ratio)
    if rl:
        parts.append(rl)
    return "\n\n".join(p for p in parts if p)


# ---------------- post builder ----------------
def _split_row(line):
    for sep in ("\t", " | ", "|", ";"):
        if sep in line:
            return [c.strip() for c in line.split(sep)]
    return [line.strip()]


def parse_table(text, layout):
    """Sheet se copy kiya table (tab) ya 'a | b | c' lines -> rows (dicts). Header row khud skip."""
    cols = LAYOUT_SPEC[layout]["cols"]
    rows = []
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        cells = _split_row(raw)
        if not rows and [c.lower() for c in cells[:len(cols)]] == cols[:len(cells)]:
            continue   # header
        row = {c: (cells[i] if i < len(cells) else "") for i, c in enumerate(cols)}
        if any(row.get(c) for c in cols[:2]):
            rows.append(row)
    return rows


def _highlight(sentence, word):
    """*star* wala word highlight; warna sentence mein word dhoondho. Returns (sentence_clean, keyword)."""
    m = re.search(r"\*([^*]+)\*", sentence or "")
    if m:
        return re.sub(r"\*([^*]+)\*", r"\1", sentence).strip(), m.group(1).strip()
    if word:
        stem = re.escape(word.strip().split()[0])
        m = re.search(r"\b(" + stem + r"\w*)\b", sentence or "", flags=re.I)
        if m:
            return sentence.strip(), m.group(1)
    return (sentence or "").strip(), ""


def _q(t):
    return '"' + (t or "").replace('"', "'").strip() + '"'


def build_posts(layout, rows, title="", subtitle="", chars_hint=True):
    """rows -> [(label, brief)]. Har brief: VISIBLE TEXT (sirf yahi chhapna) + VISUAL INSTRUCTIONS (sirf chitra)."""
    spec = LAYOUT_SPEC[layout]
    n = spec["per_post"]
    chunks = [rows[i:i + n] for i in range(0, len(rows), n)]
    out = []
    total = len(chunks)
    for pi, chunk in enumerate(chunks, 1):
        vis, draw = [], []
        if layout == "grid4":
            if title:
                vis.append(f"- Heading: {_q(title.upper())}")
            if subtitle:
                vis.append(f"- Subtitle: {_q(subtitle)}")
            for i, r in enumerate(chunk):
                sent, key = _highlight(r.get("sentence"), r.get("word"))
                hl = f" — keyword {_q(key.upper())} in the golden pill (in capitals)" if key else ""
                vis.append(f"- Card {i + 1} ({POSITIONS[i]}, {PANEL_TINTS[i]}): word {_q(r.get('word'))} · Hindi "
                           f"{_q(r.get('hindi'))} · sentence {_q(sent)}{hl}")
                draw.append(f"- Card {i + 1}: " + (r.get("visual") or f"a clear everyday scene that shows the meaning of "
                                                   f"'{r.get('word')}', matching the sentence"))
        elif layout == "phrase4":
            for i, r in enumerate(chunk):
                vis.append(f"- Card {i + 1} ({POSITIONS[i]}): Hindi {_q(r.get('hindi'))} · English {_q(r.get('english'))}")
                draw.append(f"- Card {i + 1}: " + (r.get("visual") or f"ANAYA or VIVAAN acting out '{r.get('english')}' "
                                                   f"in a cosy everyday moment"))
        elif layout == "word":
            r = chunk[0]
            sent, key = _highlight(r.get("sentence"), r.get("word"))
            vis.append(f"- Word: {_q(r.get('word'))}")
            vis.append(f"- Hindi: {_q(r.get('hindi'))}")
            if sent:
                vis.append(f"- Sentence: {_q(sent)}" + (f" — {_q(key)} in bold" if key else ""))
            draw.append("- " + (r.get("visual") or f"one simple flat illustration that shows '{r.get('word')}'"))
        elif layout == "compare2":
            for i, r in enumerate(chunk):
                side = "Left" if i == 0 else "Right"
                vis.append(f"- {side} column: Hindi {_q(r.get('hindi'))} · English {_q(r.get('english'))}")
                draw.append(f"- {side} column: " + (r.get("visual") or f"a photorealistic {r.get('english')}"))
        nm = title or (chunk[0].get("word") or chunk[0].get("english") or chunk[0].get("hindi") or "Post")
        label = f"POST {pi:02d} — {nm.upper()}" + (f" ({pi}/{total})" if total > 1 and title else "")
        brief = ("VISIBLE TEXT (print exactly this, nothing else):\n" + "\n".join(vis) +
                 "\n\nVISUAL INSTRUCTIONS (draw these — never print them as text):\n" + "\n".join(draw) +
                 "\n\nFollow the FORMAT from the rules. Keep the bottom branding strip empty.")
        out.append((label, brief))
    return out


# ---------------- post-processing: exact ratio + logo ----------------
def logo_file(ws):
    p = (ws.get("logo_path") or "").strip()
    if not p:
        return None
    for cand in (DATA_DIR / p, BASE / p, Path(p)):
        if cand.exists():
            return cand
    return None


def postprocess(path, ws, ratio, log=print):
    """ChatGPT ki image ko exact ratio pe lao (crop/pad) + workspace logo neeche lagao. Original 'originals/' mein."""
    from PIL import Image
    path = Path(path)
    if not ws or not path.exists():
        return False
    fit = ws.get("fit_mode") or "off"
    logo = logo_file(ws) if int(ws.get("logo_on") or 0) else None
    target = RATIOS.get(ratio or "")
    if fit == "off" and not logo:
        return False
    try:
        orig_dir = path.parent / "originals"
        orig_dir.mkdir(exist_ok=True)
        keep = orig_dir / path.name
        if not keep.exists():
            keep.write_bytes(path.read_bytes())
        im = Image.open(keep).convert("RGBA")
        W, H = im.size
        if target and fit in ("crop", "pad"):
            tw, th = target[0], target[1]
            want = tw / th
            have = W / H
            if abs(want - have) > 0.01:
                if fit == "crop":
                    if have > want:                      # zyada chaudi -> side se kaato
                        nw = int(round(H * want))
                        x0 = (W - nw) // 2
                        im = im.crop((x0, 0, x0 + nw, H))
                    else:                                # zyada lambi -> upar-neeche se barabar kaato
                        nh = int(round(W / want))
                        y0 = (H - nh) // 2
                        im = im.crop((0, y0, W, y0 + nh))
                else:
                    bg = im.getpixel((min(2, max(0, W - 1)), min(2, max(0, H - 1))))
                    if have > want:
                        nh = int(round(W / want))
                        canvas = Image.new("RGBA", (W, nh), bg)
                        canvas.paste(im, (0, (nh - H) // 2))
                    else:
                        nw = int(round(H * want))
                        canvas = Image.new("RGBA", (nw, H), bg)
                        canvas.paste(im, ((nw - W) // 2, 0))
                    im = canvas
        if logo:
            lg = Image.open(logo).convert("RGBA")
            W2, H2 = im.size
            lw = max(40, int(W2 * int(ws.get("logo_width_pct") or 28) / 100))
            lh = int(lg.height * lw / lg.width)
            strip = int(H2 * max(4, int(ws.get("safe_bottom_pct") or 10)) / 100)
            if lh > strip * 0.8:                          # strip mein fit karo
                lh = int(strip * 0.8)
                lw = int(lg.width * lh / lg.height)
            lg = lg.resize((lw, lh), Image.LANCZOS)
            y = H2 - strip + (strip - lh) // 2
            im.alpha_composite(lg, ((W2 - lw) // 2, max(0, y)))
        import imgconv
        buf = __import__("io").BytesIO()
        if path.suffix.lower() == ".png":
            im.save(buf, "PNG")
        else:
            im.convert("RGB").save(buf, "PNG")
        imgconv.write(path, buf.getvalue(), 92)
        log(f"Post-process: {path.name} -> {im.size[0]}×{im.size[1]}" + (" + logo" if logo else ""))
        return True
    except Exception as e:
        log(f"Post-process fail ({path.name}): {e}")
        return False


def ref_dir(wid):
    d = DATA_DIR / "workspaces" / f"ws{int(wid)}" / "refs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_refs(series):
    """Is project ke saath ChatGPT ko jaane wali reference images (template + project)."""
    out = []
    tpl = db.get_template(series.get("template_id") or 0) if series.get("template_id") else None
    for name in (_jl(tpl.get("refs"), []) if tpl else []) + _jl(series.get("refs"), []):
        p = ref_dir(series.get("workspace_id") or 1) / Path(name).name
        if p.exists() and str(p) not in out:
            out.append(str(p))
    return out[:8]
