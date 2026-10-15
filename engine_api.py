"""
Engine 2 (recommended for stability): OpenAI Images API.

No browser, no selectors, no ChatGPT layout changes. Needs an OpenAI API key
(Settings -> OpenAI API key). Paid per image.
Each image prompt = series master prompt + episode brief, so style stays the same.
"""
import base64
from pathlib import Path

import requests

import imgconv

API_URL = "https://api.openai.com/v1/images/generations"


class ApiEngine:
    def __init__(self, settings, log):
        self.s = settings
        self.log = log
        self.master = ""

    def open(self, chat_url=""):
        if not self.s.get("openai_api_key"):
            raise RuntimeError("Settings mein OpenAI API key daalo (API engine ke liye zaroori).")
        return ""

    def close(self):
        pass

    def current_url(self):
        return ""

    def screenshot(self, path):
        pass

    def send_master(self, master, files=None):   # refs API engine pe abhi nahi jaate
        self.master = master or ""

    def generate(self, prompt, out_path, stop_flag):
        full = (self.master.strip() + "\n\n" + prompt.strip()).strip()
        body = {
            "model": self.s.get("api_model") or "dall-e-3",
            "prompt": full[:32000],
            "size": self.s.get("api_size", "1024x1024"),
            "n": 1,
        }
        quality = self.s.get("api_quality", "")
        if quality:
            body["quality"] = quality
        try:
            r = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {self.s['openai_api_key']}"},
                json=body,
                timeout=int(self.s.get("image_timeout", 360)),
            )
        except Exception as e:
            return False, f"API request fail: {e}"
        if r.status_code != 200:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except Exception:
                msg = r.text
            return False, f"API error {r.status_code}: {msg[:300]}"
        data = r.json()["data"][0]
        if data.get("b64_json"):
            imgconv.write(out_path, base64.b64decode(data["b64_json"]), int(self.s.get("webp_quality", 92)))
            return True, ""
        if data.get("url"):
            img = requests.get(data["url"], timeout=120)
            imgconv.write(out_path, img.content, int(self.s.get("webp_quality", 92)))
            return True, ""
        return False, "API ne image nahi bheji."
