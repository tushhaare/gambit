"""
Netlify build preparation script.
Prepares the public/ directory containing static assets to be served directly by Netlify CDN.
"""
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
PUB = BASE / "public"
PUB.mkdir(parents=True, exist_ok=True)

# Copy static directory into public/static so CDN serves /static/* directly
static_src = BASE / "static"
static_dest = PUB / "static"

if static_dest.exists():
    shutil.rmtree(static_dest)

if static_src.exists():
    shutil.copytree(static_src, static_dest)
    print(f"Copied static assets to {static_dest}")

# Clean any stray index.html in public/ so /* correctly routes to the Flask function
stray_index = PUB / "index.html"
if stray_index.exists():
    stray_index.unlink()

print("Netlify build preparation complete.")
