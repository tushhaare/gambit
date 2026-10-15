"""Master prompt helpers: character sheet + closing lines (manual master prompts ke liye)."""
import re

CLOSING_LINES = "I will now send briefs one by one. Generate one image per brief."
SHEET_HEAD = "CHARACTER SHEET — these people recur"
_CLOSE_PATTERNS = [re.compile(r"(?im)^\s*I will now send briefs one by one\.?.*$"),
                   re.compile(r"(?im)^\s*Do NOT generate any image for this message.*$")]


def character_sheet_text(characters):
    chars = [c for c in (characters or []) if (c.get("name") or "").strip() and (c.get("look") or "").strip()]
    if not chars:
        return ""
    lines = [SHEET_HEAD + " across the series. Whenever a brief names one of them, draw exactly this person: "
             "same face, skin tone, hair, age, build and marks as described here and as in the earlier images of "
             "this chat. Never change their face between images."]
    for c in chars:
        role = f" ({c['role'].strip()})" if (c.get("role") or "").strip() else ""
        lines.append(f"- {c['name'].strip().upper()}{role}: {c['look'].strip()}")
    return "\n".join(lines)


def strip_sheet(text):
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


def compose_master(prompt, characters):
    """Master + character sheet + closing line. Dobara chalao to purana sheet hata ke naya lagata hai."""
    body = strip_sheet(prompt or "")
    for rx in _CLOSE_PATTERNS:
        body = rx.sub("", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    sheet = character_sheet_text(characters)
    if not sheet:
        return (prompt or "").strip()          # characters nahi to user ka master waisa hi
    return "\n\n".join(x for x in (body, sheet, CLOSING_LINES) if x)
