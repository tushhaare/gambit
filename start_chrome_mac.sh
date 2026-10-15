#!/usr/bin/env bash
# Mac: ChatGPT wala Chrome debugging port 9223 ke saath
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9223 --user-data-dir="$HOME/chrome-bot-dev" https://chatgpt.com/ &
