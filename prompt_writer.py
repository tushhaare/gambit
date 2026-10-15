"""
Scripts -> Master prompt + briefs, Google Gemini (FREE text API) se.

Ek series = EK request (saari scripts ek saath). Output JSON (v3.5):
  {category, characters[], master_prompt, variant_angles[A,B,C], series_brief, episodes[], notes}
  -> tool har angle ko master ke saath jod ke 3 poore master variants banata hai (output chhota = tez).
Streaming + kam "thinking" (Settings: speed) + kai API keys (ek ki limit khatam to agli).
Base instruction: prompts/gemini_instruction.md
Category libraries (house style per category): prompts/categories/<key>.md  — Train page se edit/version hote hain.
Key: https://aistudio.google.com/apikey (free). Free tier pe Google data improve karne ke liye use kar sakta hai.
"""
import json
import os
import re
import time
from pathlib import Path

import requests

BASE = os.environ.get("GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")
INSTRUCTION_FILE = Path(__file__).parent / "prompts" / "gemini_instruction.md"
DEFAULT_MODEL = "gemini-3.8-flash"
# agar chosen model na mile / quota khatam ho to inhe baari-baari try karo (sab free text models)
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3-flash-preview",
                   "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]

# ---- v3.5: category libraries (prompts/categories/<key>.md) ----
CATEGORY_DIR = INSTRUCTION_FILE.parent / "categories"
CATEGORIES = [  # (key, label, one-line hint)  — order = dropdown order
    ("devotional", "Devotional", "vrat katha, festival, aastha"),
    ("mythology", "Mythology", "puran, devta-asur, epic"),
    ("crime", "Crime (cinematic)", "true crime, convicted accused, investigation"),
    ("crime_sensitive", "True crime — sensitive", "acquitted/unsolved/minors: sirf objects"),
    ("heist", "Heist / Robbery", "chori, train/bank robbery, con"),
    ("horror", "Horror / Supernatural", "bhoot, khauf, haunting"),
    ("disaster", "Disaster / Documentary", "baadh, hadsa, rescue, history"),
    ("biopic", "Biopic / Rebel / Sports", "asli hero, baaghi, khiladi"),
    ("regular", "Regular / Drama", "family, romance, social"),
]
CAT_KEYS = [c[0] for c in CATEGORIES]
CAT_LABEL = {c[0]: c[1] for c in CATEGORIES}
# purane "style" keys -> category
STYLES = {"auto": "AUTO", **{k: CAT_LABEL[k] for k in CAT_KEYS}}

CLOSING_LINES = "I will now send briefs one by one. Generate one image per brief."

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category": {"type": "STRING"},
        "characters": {
            "type": "ARRAY",
            "items": {"type": "OBJECT",
                      "properties": {"name": {"type": "STRING"}, "role": {"type": "STRING"}, "look": {"type": "STRING"}},
                      "required": ["name", "role", "look"]},
        },
        "master_prompt": {"type": "STRING"},
        "variant_angles": {
            "type": "ARRAY",
            "items": {"type": "OBJECT",
                      "properties": {"name": {"type": "STRING"}, "angle": {"type": "STRING"}},
                      "required": ["name", "angle"]},
        },
        "series_brief": {"type": "STRING"},
        "episodes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "episode": {"type": "INTEGER"},
                    "title": {"type": "STRING"},
                    "brief": {"type": "STRING"},
                },
                "required": ["episode", "title", "brief"],
            },
        },
        "notes": {"type": "STRING"},
    },
    "required": ["category", "characters", "master_prompt", "variant_angles", "series_brief", "episodes", "notes"],
}


VERSIONS_DIR = INSTRUCTION_FILE.parent / "versions"
VERSIONS_INDEX = VERSIONS_DIR / "index.json"


def _doc_paths(doc="base"):
    """doc = 'base' (main instruction) ya category key. Returns (file, versions_dir)."""
    if doc in (None, "", "base"):
        return INSTRUCTION_FILE, VERSIONS_DIR
    if doc not in CAT_KEYS:
        raise ValueError("unknown category")
    return CATEGORY_DIR / f"{doc}.md", VERSIONS_DIR / f"cat_{doc}"


def load_doc(doc="base"):
    try:
        return _doc_paths(doc)[0].read_text(encoding="utf-8")
    except Exception:
        return ""


def load_instruction():
    return load_doc("base")


def load_category(key):
    return load_doc(key) if key in CAT_KEYS else ""


def list_versions(doc="base"):
    try:
        return json.loads((_doc_paths(doc)[1] / "index.json").read_text(encoding="utf-8"))
    except Exception:
        return []


def get_version(vid, doc="base"):
    p = _doc_paths(doc)[1] / f"{vid}.md"
    return p.read_text(encoding="utf-8") if p.exists() else None


def save_doc(doc, text, note="", by=""):
    """Save + ek naya version banao (purane kabhi delete nahi hote)."""
    f, vdir = _doc_paths(doc)
    f.parent.mkdir(parents=True, exist_ok=True)
    vdir.mkdir(parents=True, exist_ok=True)
    vers = list_versions(doc)
    if not vers and f.exists():   # pehli baar: original ko v001 ki tarah bacha lo
        orig = f.read_text(encoding="utf-8")
        (vdir / "v001.md").write_text(orig, encoding="utf-8")
        vers.append({"id": "v001", "at": time.strftime("%Y-%m-%d %H:%M"), "note": "Original (Claude)", "by": "", "chars": len(orig)})
    vid = f"v{len(vers) + 1:03d}"
    (vdir / f"{vid}.md").write_text(text, encoding="utf-8")
    vers.append({"id": vid, "at": time.strftime("%Y-%m-%d %H:%M"), "note": note or "Edit", "by": by, "chars": len(text)})
    (vdir / "index.json").write_text(json.dumps(vers, ensure_ascii=False, indent=1), encoding="utf-8")
    f.write_text(text, encoding="utf-8")
    return vid


def sync_versions():
    """Startup pe: agar file versions ke aakhri wale se alag hai (jaise naya zip daala), use naya version bana do."""
    for doc in ["base"] + CAT_KEYS:
        try:
            vers = list_versions(doc)
            if not vers:
                continue
            cur = load_doc(doc)
            if cur.strip() and (get_version(vers[-1]["id"], doc) or "").strip() != cur.strip():
                save_doc(doc, cur, "Tool update (v3.5 file)", "")
        except Exception:
            pass


def save_instruction(text, note="", by=""):
    return save_doc("base", text, note, by)


def ep_number(name, text=""):
    for src in (name, text[:300]):
        m = re.search(r"EP(?:ISODE)?[\s_\-]*0*(\d{1,3})", src or "", flags=re.I)
        if m:
            return int(m.group(1))
    return 9999


def ep_title(name, text=""):
    """Script ki pehli line 'Series — EP03: Title' se title nikalo."""
    first = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    m = re.search(r"EP\s*\d+\s*[:\-—–]\s*(.+)$", first)
    if m:
        return m.group(1).strip()
    stem = re.sub(r"^[0-9a-f]{6,}-", "", Path(name).stem)
    stem = re.sub(r"^EP\d+[_\-\s]*", "", stem, flags=re.I)
    return stem.replace("_", " ").title()


def category_block(category):
    """Chosen category ki library; AUTO pe saari (Gemini khud chunta hai)."""
    if category in CAT_KEYS:
        return f"CATEGORY (forced by the team): {category}\n\n===== CATEGORY LIBRARY: {category} =====\n{load_category(category).strip()}"
    libs = [f"===== CATEGORY LIBRARY: {k} =====\n{load_category(k).strip()}" for k in CAT_KEYS if load_category(k).strip()]
    return ("CATEGORY: AUTO — read the scripts, pick the ONE best library key from: " + ", ".join(CAT_KEYS)
            + ". Return that key in \"category\" and follow only that library.\n\n" + "\n\n".join(libs))


def build_user_message(series_name, scripts, style, extra_notes):
    parts = [f"SERIES NAME: {series_name}",
             category_block(style),
             f"\nNUMBER OF EPISODE SCRIPTS: {len(scripts)} (write exactly one brief per episode, same order)",
             "Write ONE master_prompt and exactly 3 variant_angles (A, B, C) following the library's MASTER VARIANTS."]
    if extra_notes.strip():
        parts.append("EXTRA INSTRUCTIONS FROM THE TEAM (follow these):\n" + extra_notes.strip())
    for i, (name, text) in enumerate(scripts, 1):
        parts.append(f"\n===== EPISODE {i} | file: {name} | title: {ep_title(name, text)} =====\n{text.strip()}")
    parts.append("\nReturn ONLY the JSON object described by the schema.")
    return "\n".join(parts)


def character_sheet_text(characters):
    chars = [c for c in (characters or []) if (c.get("name") or "").strip() and (c.get("look") or "").strip()]
    if not chars:
        return ""
    lines = ["CHARACTER SHEET — these people recur across the series. Whenever a brief names one of them, draw "
             "exactly this person: same face, skin tone, hair, age, build and marks as described here and as in the "
             "earlier images of this chat. Never change their face between images."]
    for c in chars:
        role = f" ({c['role'].strip()})" if (c.get("role") or "").strip() else ""
        lines.append(f"- {c['name'].strip().upper()}{role}: {c['look'].strip()}")
    return "\n".join(lines)


_CLOSE_PATTERNS = [re.compile(r"(?im)^\s*I will now send briefs one by one\.?.*$"),
                   re.compile(r"(?im)^\s*Do NOT generate any image for this message.*$")]
SHEET_HEAD = "CHARACTER SHEET — these people recur"


def strip_sheet(text):
    """Purana character sheet block (heading + uske '- NAAM: look' lines) hatao, baaki sab rakho."""
    out, skip = [], False
    for line in (text or "").split("\n"):
        if line.strip().startswith(SHEET_HEAD):
            skip = True
            continue
        if skip and (line.strip().startswith("- ") or not line.strip()):
            continue
        skip = False
        out.append(line)
    return "\n".join(out)


def compose_master(variant_prompt, characters):
    """Variant + character sheet + closing line. (READY wali line engine khud jodta hai.)
    Dobara chalao to purana sheet/closing hata ke naya lagata hai; team ka baaki text waisa hi rehta hai."""
    body = strip_sheet(variant_prompt or "")
    for rx in _CLOSE_PATTERNS:
        body = rx.sub("", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    sheet = character_sheet_text(characters)
    return "\n\n".join(x for x in (body, sheet, CLOSING_LINES) if x)


VARIANT_HEAD = "VARIANT LOOK"


def variant_prompt(master, name, angle):
    """Ek master + variant ka look-angle = us variant ka poora master (chat ke liye)."""
    base = re.split(r"\n\s*VARIANT LOOK\s*[—-]", master or "")[0].rstrip()
    if not (angle or "").strip():
        return base
    return (f"{base}\n\n{VARIANT_HEAD} — {name.strip()}: {angle.strip()}\n"
            "Apply this variant look (light, palette emphasis, lens and mood) to every image in this chat, "
            "while keeping all rules above.")


def _words(t):
    return set(re.findall(r"[a-z0-9]+", (t or "").lower()))


def enforce_continuity(brief, characters):
    """Agar brief mein character ka naam hai par uska fixed look nahi likha, to look jod do (face continuity)."""
    out = brief or ""
    for c in characters or []:
        name, look = (c.get("name") or "").strip(), (c.get("look") or "").strip()
        if not name or not look:
            continue
        if not re.search(r"\b" + re.escape(name.split()[0]) + r"\b", out, flags=re.I):
            continue
        lw = _words(look) - {"a", "an", "the", "and", "with", "of", "in", "on"}
        if lw and len(lw & _words(out)) / len(lw) >= 0.6:
            continue
        tail = "Square 1:1, title in the top 30%."
        add = f"Keep {name.upper()} exactly as in the character sheet ({look}) — same face as earlier images."
        if out.rstrip().endswith(tail):
            out = out.rstrip()[: -len(tail)].rstrip() + " " + add + " " + tail
        else:
            out = out.rstrip() + " " + add
    return out


def explain(status, msg):
    low = (msg or "").lower()
    if status == 429:
        m = re.search(r"retry in ([\d.]+)s", low)
        wait = f" ~{int(float(m.group(1)))} sec baad dobara try karo." if m else ""
        return "Gemini ki free limit poori (429)." + wait + " " + msg[:160]
    if status in (401, 403) or "api key not valid" in low:
        return "Gemini API key galat hai / band hai. " + msg[:160]
    if status == 404:
        return "Model nahi mila: " + msg[:160]
    return f"Gemini error {status}: {msg[:240]}"


def _thinking_cfg(model, speed):
    """Fast = kam sochna (bahut tez). Best = model ka default."""
    if speed == "best":
        return None
    m = model.lower()
    if "2.5" in m:
        return {"thinkingBudget": 128 if "pro" in m else 0}
    return {"thinkingLevel": "low"}


def _call(key, model, system, user, timeout, schema=None, temperature=0.8, speed="fast", on_chunk=None):
    """Streaming call. Returns (text, status, msg). on_chunk(text_so_far, thought_chunks) live progress ke liye."""
    gen = {"temperature": temperature, "maxOutputTokens": 24000,
           "responseMimeType": "application/json", "responseSchema": schema or SCHEMA}
    tc = _thinking_cfg(model, speed)
    if tc:
        gen["thinkingConfig"] = tc
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen}
    r = requests.post(f"{BASE}/models/{model}:streamGenerateContent", params={"alt": "sse"},
                      headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                      json=body, timeout=timeout, stream=True)
    if r.status_code != 200:
        try:
            err = r.json().get("error", {})
            msg = err.get("message") or r.text
            qids = [v.get("quotaId", "") for d in (err.get("details") or []) for v in (d.get("violations") or [])]
            if any(qids):
                msg += " [quota: " + ", ".join(q for q in qids if q) + "]"
        except Exception:
            msg = r.text
        if r.status_code == 400 and tc and "think" in (msg or "").lower():
            # ye model thinkingConfig nahi maanta — bina uske dobara
            return _call(key, model, system, user, timeout, schema, temperature, "best", on_chunk)
        return None, r.status_code, msg
    out, thoughts, why = [], 0, ""
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        try:
            j = json.loads(line[5:].strip())
        except Exception:
            continue
        if (j.get("promptFeedback") or {}).get("blockReason"):
            why = j["promptFeedback"]["blockReason"]
        for c in j.get("candidates", []):
            if c.get("finishReason") and c["finishReason"] not in ("STOP", "MAX_TOKENS"):
                why = c["finishReason"]
            for p in (c.get("content") or {}).get("parts", []):
                if p.get("thought"):
                    thoughts += 1
                elif p.get("text"):
                    out.append(p["text"])
        if on_chunk:
            try:
                on_chunk("".join(out), thoughts)
            except Exception:
                pass
    text = "".join(out)
    if not text.strip():
        return None, 200, f"Gemini ne khaali jawab diya ({why or 'unknown'})."
    return text, 200, ""


# ---------------- API keys pool (kai Google accounts) ----------------
USAGE_FILE = Path(__file__).parent / "gemini_usage.json"


def _quota_day():
    """Gemini ki daily limit Pacific time ki aadhi raat ko reset hoti hai."""
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    except Exception:
        return time.strftime("%Y-%m-%d", time.gmtime(time.time() - 8 * 3600))


def _usage():
    try:
        u = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        u = {}
    day = _quota_day()
    if u.get("day") != day:
        u = {"day": day, "keys": {}}
    return u


def _usage_save(u):
    try:
        USAGE_FILE.write_text(json.dumps(u, indent=1), encoding="utf-8")
    except Exception:
        pass


def key_id(key):
    import hashlib
    return hashlib.sha1((key or "").encode()).hexdigest()[:10]


def get_keys(settings):
    """[{id, label, key}] — pehli Settings wali key, phir extra keys (naye accounts)."""
    out, seen = [], set()
    k0 = (settings.get("gemini_text_key") or "").strip()
    if k0:
        out.append({"label": (settings.get("gemini_key_label") or "Key 1").strip() or "Key 1", "key": k0})
    for i, e in enumerate(settings.get("gemini_extra_keys") or []):
        k = (e.get("key") or "").strip()
        if k:
            out.append({"label": (e.get("label") or f"Key {i + 2}").strip(), "key": k})
    res = []
    for e in out:
        e["id"] = key_id(e["key"])
        if e["id"] not in seen:
            seen.add(e["id"])
            res.append(e)
    return res


def usage_summary(settings):
    u = _usage()
    rpd = int(settings.get("gemini_rpd") or 20)
    rows = []
    for k in get_keys(settings):
        ku = u["keys"].get(k["id"], {})
        rows.append({"id": k["id"], "label": k["label"], "tail": k["key"][-4:], "used": ku.get("used", 0), "rpd": rpd,
                     "full_models": sorted(ku.get("full", [])), "bad": bool(ku.get("bad"))})
    return {"day": u["day"], "keys": rows}


def _mark(kid, used=False, full_model=None, bad=False):
    u = _usage()
    ku = u["keys"].setdefault(kid, {"used": 0, "full": []})
    if used:
        ku["used"] = ku.get("used", 0) + 1
    if full_model and full_model not in ku.setdefault("full", []):
        ku["full"].append(full_model)
    if bad:
        ku["bad"] = True
    _usage_save(u)


def _run(settings, system, user, schema, temperature, log, progress=None, validate=None):
    """Har model ke liye saari keys try karo (best model pehle). Returns (data, model, key_label, seconds)."""
    keys = get_keys(settings)
    if not keys:
        raise RuntimeError("Settings → Gemini mein API key daalo (aistudio.google.com/apikey, free).")
    chosen = (settings.get("gemini_text_model") or DEFAULT_MODEL).strip()
    models = [chosen] + [m for m in FALLBACK_MODELS if m != chosen]
    timeout = int(settings.get("gemini_text_timeout") or 240)
    speed = settings.get("gemini_speed") or "fast"
    rpd = int(settings.get("gemini_rpd") or 20)
    errs = []
    for model in models:
        for k in keys:
            ku = _usage()["keys"].get(k["id"], {})
            if ku.get("bad") or model in ku.get("full", []):
                continue
            t0 = time.time()
            log(f"Gemini ({model}, {k['label']}) likh raha hai...")
            if progress:
                progress({"phase": "start", "model": model, "key": k["label"], "used": ku.get("used", 0), "rpd": rpd})
            cb = (lambda txt, th, _m=model, _k=k: progress({"phase": "writing" if txt else "thinking", "text": txt,
                                                             "thoughts": th, "model": _m, "key": _k["label"]})) if progress else None
            try:
                text, st, msg = _call(k["key"], model, system, user, timeout, schema, temperature, speed, cb)
            except requests.Timeout:
                errs.append(f"{model}/{k['label']}: timeout")
                log(errs[-1])
                break                       # model slow hai — agla model
            except requests.RequestException as e:
                raise RuntimeError(f"Gemini tak pahunch nahi paaye: {e}")
            if text is None:
                err = explain(st, msg) if st != 200 else msg
                errs.append(f"{model}/{k['label']}: {err}")
                log(errs[-1])
                low = (msg or "").lower()
                if st in (401, 403) or "api key not valid" in low:
                    _mark(k["id"], bad=True)
                    continue                # ye key kharab — agli key
                if st == 429:
                    if "perday" in low or "per day" in low or "daily" in low:
                        _mark(k["id"], full_model=model)
                        log(f"{k['label']} ki aaj ki limit ({model}) khatam — agli key.")
                    continue                # agli key, same (best) model
                if st == 404:
                    break                   # model hi nahi hai — agla model
                break                       # 5xx / khaali — agla model
            _mark(k["id"], used=True)
            try:
                data = parse_json(text)
                if validate:
                    validate(data)
            except Exception as e:
                errs.append(f"{model}/{k['label']}: jawab adhoora ({str(e)[:60]})")
                log(errs[-1])
                break
            return data, model, k["label"], round(time.time() - t0)
    if errs and all("429" in e or "limit" in e for e in errs):
        raise RuntimeError("Saari keys ki aaj ki free limit khatam. Settings → Gemini mein naye Google account ki key "
                           "jodo, ya limit reset hone tak ruko (roz dopahar ~12:30–1:30 IST).\n" + errs[-1])
    raise RuntimeError((errs[-1] if errs else "Koi bhi Gemini model/key kaam nahi kiya."))


def fix_title(brief, title):
    """Brief ke shuru wala Title: "..." hamesha script ke asli title (CAPS) se bhar do."""
    brief = (brief or "").strip()
    title = (title or "").strip().upper()
    if not title:
        return brief
    new = f'Title: "{title}".'
    if re.match(r'^\s*Title\s*:\s*["“]', brief, flags=re.I):
        rest = re.sub(r'^\s*Title\s*:\s*["“][^"”]*["”]\s*\.?\s*', "", brief, count=1, flags=re.I)
        return f"{new} {rest}".strip()
    return f"{new} {brief}"


def parse_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise


def write_prompts(settings, series_name, scripts, style="auto", extra_notes="", log=print, progress=None):
    """scripts = [(filename, text)]. Returns dict with master variants, briefs etc. Raises RuntimeError."""
    if not scripts:
        raise RuntimeError("Koi script nahi mili. .txt files daalo.")
    scripts = sorted(scripts, key=lambda s: (ep_number(s[0], s[1]), s[0]))
    system = load_instruction()
    user = build_user_message(series_name, scripts, style, extra_notes)

    def validate(d):
        if not (d.get("master_prompt") or d.get("master_variants")):
            raise ValueError("master prompt khaali")
        if not d.get("episodes"):
            raise ValueError("briefs khaali")

    data, model, key_label, secs = _run(settings, system, user, None, 0.8, log, progress, validate)
    chars = [c for c in (data.get("characters") or []) if (c.get("name") or "").strip()][:6]
    data["characters"] = chars
    cat = (data.get("category") or "").strip().lower().replace(" ", "_")
    data["category"] = style if style in CAT_KEYS else (cat if cat in CAT_KEYS else "regular")
    master = (data.get("master_prompt") or "").strip()
    angles = [a for a in (data.get("variant_angles") or []) if (a.get("angle") or "").strip()][:4]
    variants = []
    if data.get("master_variants"):          # purana format bhi chale
        variants = [{"name": v.get("name", ""), "angle": v.get("angle", ""), "prompt": v.get("prompt", "")}
                    for v in data["master_variants"] if (v.get("prompt") or "").strip()][:4]
    elif angles:
        for a in angles:
            variants.append({"name": a.get("name", ""), "angle": a.get("angle", ""),
                             "prompt": variant_prompt(master, a.get("name", ""), a.get("angle", ""))})
    else:
        variants = [{"name": "A", "angle": "", "prompt": master}]
    for n, v in enumerate(variants):
        letter = "ABCD"[n]
        nm = re.sub(r"^\s*[A-D]\s*[—:\-.)]\s*", "", (v.get("name") or "").strip())
        v["name"] = f"{letter} — {nm or 'Variant'}"
        if "VARIANT LOOK" in v["prompt"]:
            v["prompt"] = re.sub(r"VARIANT LOOK — [^:]*:", f"VARIANT LOOK — {v['name']}:", v["prompt"], count=1)
        v["prompt"] = compose_master(v["prompt"], chars)
    data["master_variants"] = variants
    data["master_prompt"] = variants[0]["prompt"]
    data["style"] = CAT_LABEL.get(data["category"], data["category"])
    data["series_brief"] = enforce_continuity(data.get("series_brief", ""), chars)
    eps = sorted(data.get("episodes") or [], key=lambda e: int(e.get("episode") or 0))
    if len(eps) != len(scripts):
        log(f"Note: {len(scripts)} scripts thi, Gemini ne {len(eps)} briefs diye.")
    for i, e in enumerate(eps):                 # title hamesha script se
        if i < len(scripts):
            real = ep_title(*scripts[i])
            e["episode"] = ep_number(*scripts[i]) if ep_number(*scripts[i]) != 9999 else i + 1
            e["title"] = real or e.get("title", "")
        e["brief"] = enforce_continuity(fix_title(e.get("brief", ""), e.get("title", "")), chars)
    data["episodes"] = eps
    data["model"], data["key"], data["seconds"] = model, key_label, secs
    log(f"Gemini ({model}, {key_label}) ne {secs} sec mein master + {len(variants)} variants + "
        f"{len(chars)} characters + {len(eps)} briefs likhe ({data['style']}).")
    return data


def list_text_models(key):
    r = requests.get(f"{BASE}/models", headers={"x-goog-api-key": key}, params={"pageSize": 1000}, timeout=30)
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message") or r.text
        except Exception:
            msg = r.text
        raise RuntimeError(explain(r.status_code, msg))
    out = []
    for m in r.json().get("models", []):
        name = m.get("name", "").removeprefix("models/")
        if "generateContent" in (m.get("supportedGenerationMethods") or ["generateContent"]) and \
                name.startswith("gemini") and not any(x in name for x in ("image", "tts", "embedding", "live", "audio")):
            out.append(name)
    return sorted(set(out))


# ---------------- TRAINING: feedback se instruction sudhaaro ----------------
TRAINER_SYSTEM = """You maintain one instruction document used by an AI art director who writes ChatGPT image prompts
(master prompt variants + per-episode briefs) for a Hindi audio-series app's thumbnails.
The document is either the BASE INSTRUCTION (general rules) or a CATEGORY LIBRARY (house style for one genre:
look, title treatment, series-thumbnail formula, shot bank, prop bank, character styling, master variant angles, examples).
The team gives you feedback after looking at real outputs. Update the instruction so future outputs follow the feedback.
Rules:
- Keep the same markdown structure and headings (# SECTION). Edit in place; add a new section only if nothing fits.
- Make the SMALLEST set of changes that fully applies the feedback. Never drop existing rules unless the feedback says so.
- Never weaken safety rules (minors, gore, acquitted accused, idols, logos, politicians, real landmarks, actor likeness).
- If the team's edits to a series' prompts are given, infer the general lesson (not series-specific details) and encode it.
- Write rules as clear, specific, positive instructions. Keep it compact.
Return JSON: {"instruction": "<full updated instruction>", "changes": "<3-8 short Hinglish bullet lines: kya badla aur kyun>"}"""

TRAIN_SCHEMA = {"type": "OBJECT",
                "properties": {"instruction": {"type": "STRING"}, "changes": {"type": "STRING"}},
                "required": ["instruction", "changes"]}


def improve_instruction(settings, current, feedback, context="", log=print, doc="base", progress=None):
    """Returns (new_instruction, changes_text, model). Save nahi karta — UI pe preview hota hai."""
    if not (feedback or "").strip() and not (context or "").strip():
        raise RuntimeError("Feedback likho (kya achha nahi laga / kya chahiye).")
    kind = "BASE INSTRUCTION" if doc in (None, "", "base") else f"CATEGORY LIBRARY: {doc}"
    user = (f"DOCUMENT TYPE: {kind}\nCURRENT DOCUMENT:\n<<<\n{current}\n>>>\n\n"
            f"TEAM FEEDBACK:\n{feedback.strip() or '(none)'}\n")
    if context.strip():
        user += f"\nCONTEXT FROM A REAL SERIES:\n{context.strip()}\n"

    def validate(d):
        if len((d.get("instruction") or "").strip()) < 0.5 * len(current):
            raise ValueError("naya instruction bahut chhota (kuch kat gaya)")

    data, model, _k, _s = _run(settings, TRAINER_SYSTEM, user, TRAIN_SCHEMA, 0.4, log, progress, validate)
    return data["instruction"].strip(), (data.get("changes") or "").strip(), model
