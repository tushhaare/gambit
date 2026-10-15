"""
Netlify Serverless Function entrypoint for Gambit (Thumbnail Studio).
"""
import os
import sys
from pathlib import Path

# Add project root to Python search path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Declare serverless environment before importing app
os.environ["IS_SERVERLESS"] = "1"
os.environ.setdefault("DATA_DIR", "/tmp/kfm_data")

from app import app
from wsgi_adapter import handle_lambda


def handler(event, context):
    return handle_lambda(app, event, context)
