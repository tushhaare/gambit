"""Image format helper: series thumbnail -> WebP, episodes -> PNG (Settings se badal sakte ho)."""
import io
from pathlib import Path

FORMATS = {"png": "PNG", "webp": "WEBP", "jpg": "JPEG"}


def convert(data: bytes, fmt: str, quality: int = 92) -> bytes:
    """bytes ko diye gaye format (png/webp/jpg) mein convert karta hai."""
    fmt = (fmt or "png").lower().lstrip(".")
    if fmt == "raw":
        return data  # jaisa aaya waisa (agent upload ke liye — sabse chhota, koi conversion nahi)
    try:
        from PIL import Image
    except Exception:
        return data  # Pillow nahi hai to jaisa hai waisa
    img = Image.open(io.BytesIO(data))
    if img.format == FORMATS.get(fmt):
        return data
    out = io.BytesIO()
    if fmt == "webp":
        img.save(out, "WEBP", quality=quality, method=6)
    elif fmt == "jpg":
        img.convert("RGB").save(out, "JPEG", quality=quality, optimize=True)
    else:
        img.save(out, "PNG", optimize=True)
    return out.getvalue()


def write(path, data: bytes, quality: int = 92) -> Path:
    """path ke extension ke hisaab se convert karke save karta hai."""
    path = Path(path)
    path.write_bytes(convert(data, path.suffix, quality))
    return path


def thumbnail(src_path, out_path, size=320, quality=78):
    """Chhota WebP preview (dashboard ke liye) — 1-2 MB ki jagah ~15-30 KB."""
    from PIL import Image
    img = Image.open(src_path)
    img.thumbnail((size, size * 2))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "WEBP", quality=quality, method=4)
    return Path(out_path)
