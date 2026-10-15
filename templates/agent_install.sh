#!/usr/bin/env bash
# KahaniFM Agent — one command setup + run (Mac / Linux)
set -e
HUB="{{ hub }}"; KEY="{{ key }}"; NAME="{{ name }}"; VER="{{ v }}"
HOME2="$HOME/.kahanifm-agent-dev"; OUT="$HOME/Desktop/KahaniFM Outputs DEV"
mkdir -p "$HOME2" "$OUT"
echo; echo "  KahaniFM DEV Agent (test version) — $NAME"; echo "  Hub: $HUB"; echo
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then echo "python3 nahi mila. Mac: 'xcode-select --install' ya python.org se install karo, phir dobara chalao."; exit 1; fi
[ -x "$HOME2/venv/bin/python" ] || "$PY" -m venv "$HOME2/venv"
VPY="$HOME2/venv/bin/python"
for f in agent.py engine_browser.py imgconv.py; do curl -fsSL "$HUB/agent/files/$f" -o "$HOME2/$f"; done
if [ "$(cat "$HOME2/deps.ok" 2>/dev/null)" != "$VER" ]; then
  echo "[2/4] Packages install ho rahe hain..."
  "$VPY" -m pip install -q --upgrade pip >/dev/null
  "$VPY" -m pip install -q requests playwright pillow
  echo "$VER" > "$HOME2/deps.ok"
fi
cat > "$HOME2/agent.json" <<JSON
{"hub_url": "$HUB", "agent_key": "$KEY", "name": "$NAME", "cdp_url": "http://localhost:9223", "output_dir": "$OUT"}
JSON
if ! curl -fs "http://localhost:9223/json/version" >/dev/null 2>&1; then
  CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  [ -x "$CH" ] || CH=$(command -v google-chrome || command -v chromium || true)
  "$CH" --remote-debugging-port=9223 --user-data-dir="$HOME2/chrome-profile" --no-first-run https://chatgpt.com/ >/dev/null 2>&1 &
  sleep 4
  if [ ! -f "$HOME2/login.ok" ]; then
    read -r -p "Naye Chrome mein ChatGPT login karo, phir Enter dabao... " _ </dev/tty
    echo ok > "$HOME2/login.ok"
  fi
fi
echo "[4/4] Agent chalu — window khuli rakho. Images: $OUT"
cd "$HOME2" && exec "$VPY" agent.py
