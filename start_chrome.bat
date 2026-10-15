@echo off
REM ChatGPT wala Chrome debugging port 9223 ke saath kholta hai.
REM Pehli baar isme chatgpt.com par login karo - login yaad rahega (C:\chrome-bot-dev profile).
set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
start "" %CHROME% --remote-debugging-port=9223 --user-data-dir="C:\chrome-bot-dev" https://chatgpt.com/
