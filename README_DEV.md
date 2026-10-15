# Gambit — poster & thumbnail studio (DEV, v4.0)

## v4.0: Gambit = workspaces
Ek tool, kai brands. Sidebar mein upar **workspace switcher**: KahaniFM · SpeakEasy AI · (+ Naya workspace).
Har workspace ka apna: brand rules (master prompt ki shuruaat), templates, recurring characters, logo, default size,
projects (KahaniFM mein "Series", SpeakEasy mein "Post set") aur dashboard.

- **Workspace & templates** (sidebar): General (naam, size, logo, neeche branding strip %, exact-size crop/pad) ·
  Brand rules · Characters · Templates (format prompt + size + builder layout + reference images).
- **Naya project** = workspace rules + template format + size + characters → master prompt khud ban jaata hai.
- **Size:** 1:1, 4:5, 3:4, 2:3, 9:16, 16:9. ChatGPT jo bhi size de, image exact size pe crop/pad hoti hai
  (original `originals/` folder mein bachi rehti hai).
- **Logo khud lagta hai:** workspace ka PNG logo har nayi image ke neeche branding strip mein (SpeakEasy pe on).
- **Reference images:** template ki (sabke liye) + project ki — nayi ChatGPT chat mein master ke saath attach hoti hain
  ("is style jaisa banao, text copy mat karo"). Teammate agents bhi hub se download karke attach karte hain.
- **Post builder (SpeakEasy):** Google Sheet se table paste karo → posts khud bante hain. Har brief mein
  VISIBLE TEXT (sirf yahi chhapna) aur VISUAL INSTRUCTIONS (sirf chitra) alag — ChatGPT instructions ko text nahi chhapta.
  Templates: Made Easy 2×2 grid · Phrase cards (Hindi+English) · Word card (minimal) · Vocab compare (2 objects).
  `*star*` se keyword highlight; 12 rows = 3 posts khud.
- KahaniFM ke purane series KahaniFM workspace mein; App posters (CD) panel sirf KahaniFM mein.


Main tool ki ALAG copy — main tool ko chhoota nahi:
- Port **5100** (main tool 5000 pe), apni alag database/settings/outputs. Pehli baar naya admin account banao.
- **Apna alag team link** (trycloudflare) — `run.bat` chalate hi Team link card mein dikhega.
- **Dev agent purane agent ko nahi chhoota:** teammate ke laptop pe alag folder (`%LOCALAPPDATA%\KahaniFM-Agent-DEV`),
  alag Chrome (port **9223**, alag profile), outputs `Desktop\KahaniFM Outputs DEV`. Dono agents ek saath chal sakte hain.
- Hub PC pe dev ka ChatGPT Chrome bhi alag: `start_chrome.bat` (port 9223, profile C:\chrome-bot-dev).

## v3.7: Gemini / API prompt writer hata diya
Prompts ab manually: master prompt paste karo, briefs **Bulk paste** (`===` se alag). Settings se API keys, Train page,
Scripts → Prompts panel sab hata diye. `prompts/categories/*.md` style library ke roop mein rakhi hai (aage product ke liye).

## Jo features hain
- **Dashboard:** series, episodes, thumbnails (aaj / 7 din), avg time per thumbnail, success rate, roz ka chart,
  team leaderboard, fail reasons, kis waqt kaam hota hai, recent activity, variants & regenerate stats.
- **Master prompts A / B / C:** "+ Variant" se ek master ke variants banao (light/angle badal ke). Har variant ki apni
  ChatGPT chat. *Generate* = active variant; *Regenerate* (bani hui image) = agla variant → wahi brief, alag image.
  Toggle "Regenerate = naya variant" band = purana tarika (same chat).
- **Character sheet:** recurring characters ka fixed look — har variant ke master mein khud judta hai ("same face").
- **ChatGPT master pe image nahi banata:** master ke end mein "reply READY" line jaati hai (Settings se badlo).
- **Teammate installer (PowerShell) mein live timer** + packages sirf pehli baar install.
