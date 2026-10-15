# KahaniFM Thumbnail Automation Tool

Laptop pe chalne wala dashboard: series banao → master prompt daalo → series + episode briefs add karo → drag karke order set karo → **Generate**. Tool ek-ek brief ChatGPT ko bhejta hai (master prompt ke baad, usi chat mein), image banne ka wait karta hai, aur image **folder** + **Excel sheet** dono mein record karta hai.

---

## 1. Ek baar ka setup (Windows)

1. **Python 3.10+** install karo → https://www.python.org/downloads/
   Installer mein **"Add Python to PATH"** zaroor tick karna.
2. **Google Chrome** installed hona chahiye.
3. Zip ko kisi folder mein unzip karo, jaise `D:\KahaniFM-Thumbnail-Tool`.
4. `run.bat` pe double-click karo.
   Pehli baar ye `.venv` banata hai aur sab packages install karta hai (2-3 min). Phir browser mein **http://localhost:5000** khul jaata hai.

> Mac: Terminal mein `./run.sh` aur `./start_chrome_mac.sh`.

## 2. ChatGPT ko jodna (browser engine)

1. `start_chrome.bat` double-click karo. Ek **alag Chrome** khulega (profile `C:\chrome-bot`).
2. Pehli baar isme **chatgpt.com par login** karo. Login yaad rahega, roz dobara nahi karna.
3. Ye Chrome window **khuli rehni chahiye** jab tak generate chal raha hai (minimise kar sakte ho).

> Zaroori: agar normal Chrome pehle se khula hai to bhi `start_chrome.bat` alag profile se khulega, koi dikkat nahi. Tool sirf apna naya tab kholta hai aur kaam ke baad sirf wahi tab band karta hai.

## 3. Roz ka kaam

1. `start_chrome.bat` → `run.bat`.
2. **+ New series** → naam daalo (jaise *Burari Case: Gyarah Log, Gyarah Sawaal*).
3. **Master prompt** box mein series ka master prompt paste karo.
4. Briefs add karo, teen mein se koi bhi tareeka:
   - **Bulk paste**: saare briefs ek saath, har brief ke beech ek line par sirf `===`. Pehla = series thumbnail, baaki EP01, EP02…
   - **.txt drop**: `.txt` files ko orange box mein drag-drop karo (ek file = ek brief, ya ek file mein `===` se alag briefs).
   - **+ Series thumbnail / + Episode**: ek-ek karke.
5. cards ko ⠿ handle se drag karke order set karo.
6. **Generate pending** dabao. Right side mein live log dikhega.
   - Pehli baar: nayi ChatGPT chat → master prompt → reply ka wait → phir har brief `Create an image: ...` ke saath.
   - Agli baar usi series mein: **wahi purani chat** khulti hai (characters/style same rehte hain).
   - Nayi chat chahiye to **New chat** toggle on karo, ya master prompt badlo (badalte hi agli baar nayi chat).
7. **Stop**: current image ke baad ruk jaata hai.

### Output kahan jaata hai
```
outputs/
  001_burari_case_gyarah_log/
    00_series_series_thumbnail.webp   <- series thumbnail WebP mein
    01_ep01_ek_subah.png
    02_ep02_rajister.png
    burari_case_gyarah_log_log.xlsx   <- har image ke baad auto-update
    error_....png                     <- fail hone par ChatGPT ka screenshot
```
- **Formats** button pehle se bani images ko current format settings mein convert kar deta hai (jaise purani PNG series thumbnail → WebP).
- **Folder** button folder kholta hai, **Excel** sheet download karta hai.
- Excel mein: #, Type, Label, Status, File (clickable link), Time, Error, Prompt + alag sheet mein master prompt.

### App posters (Funda Poster Studio, CD/vinyl wala 2:3 WebP)
Saare thumbnails ban jaane ke baad upar **Make app posters** (right side, step 4) dabao:
1. Kaunsi images bhejni hain tick karo (default: saari), poster size chuno (600×900 / 1000×1500 / 1080×1620 / 1200×1800).
2. **Generate posters** → Tool khud https://funda-audio-thumbnail-gen.vercel.app/ kholta hai (background mein, aapke installed Chrome se), saari images upload karta hai, **WebP** chunta hai, *Generate posters* dabata hai aur zip download karta hai.
3. Zip `outputs/<series>/posters/` mein extract hota hai. Har card pe purple **Poster** chip aata hai aur Excel mein "App poster (WebP)" column bhar jaata hai.
4. **Posters folder** (popup mein) → seedha app content pe upload karo.

Agar site badal jaaye aur kaam na kare: Settings → *Poster browser* = **Visible (debug)** karke dekho kahan atak raha hai; error ka screenshot `posters/poster_site_error.png` mein milega.

### Final folder (app pe upload karne wali files)
Posters bante hi `outputs/<series>/final/` folder apne aap banta hai. Saari files WebP mein:

| File | Kya hai |
|---|---|
| `Hastinapur Se Vidaai.webp` | Episode poster (CD wala, Vercel se) — sirf episode ka naam, koi EP number/prefix/suffix nahi |
| `Pandavas Swarg Ka Raasta (Series Thumbnail).webp` | Series poster (CD wala, Vercel se) |
| `Pandavas Swarg Ka Raasta.webp` | Series thumbnail bina CD (square) |

- Episode ka naam label se apne aap nikalta hai (`EP01 — HASTINAPUR SE VIDAAI` → `Hastinapur Se Vidaai`). Har card pe **Final name** box mein badal sakte ho.
- Windows file name mein `: / ? * " < > |` nahi chalte, isliye hata diye jaate hain (`Pandavas: Swarg…` → `Pandavas Swarg…`).
- Naam badla? **Final folder** button dabao — folder dobara ban ke khul jaata hai.

### Jab ChatGPT image nahi banata (refuse / timeout)
- Card **failed** ho jaata hai, error likha aata hai.
- Brief edit karo (safer wording) → card ka **Regenerate** dabao.
- Ya manual: **Copy prompt** → khud ChatGPT/Gemini mein banao → image ko card ke thumbnail box pe **drag-drop** karo (ya **Upload image**). Wo bhi folder + Excel mein record ho jaati hai.

## 4. Settings (sidebar mein neeche)
| Setting | Default | Matlab |
|---|---|---|
| Chrome debug URL | `http://localhost:9222` | start_chrome.bat wala port |
| Image prefix | `Create an image: ` | har brief ke aage lagta hai |
| Master reply wait | 90 | master prompt ke jawab ka max wait (sec) |
| Image timeout | 360 | ek image ka max wait (sec) |
| Gap between images | 8 | do images ke beech ruko (rate limit se bachne ke liye) |
| Retries | 1 | fail hone par kitni baar dobara |
| Series thumbnail format | WebP | series thumbnail isi format mein save hota hai |
| Episode thumbnails format | PNG | saare episodes isi format mein |
| WebP / JPG quality | 92 | 1-100 (zyada = better quality, badi file) |
| OpenAI API key / model / size / quality | — | sirf **OpenAI API** engine ke liye |

## 5. Do engines — kaunsa use karein?

**ChatGPT (my Chrome)** — free (aapke ChatGPT Plus plan mein), lekin website automation hai:
- ChatGPT ka layout badla to selectors toot sakte hain (`engine_browser.py` → `get_prompt_box` mein fix hota hai).
- ChatGPT ki image limits / rate limits lagti hain; bahut tez chalane se slow ho sakta hai → *Gap* badhao.
- Website automation OpenAI ke terms ke grey area mein hai; isliye ek-ek karke, normal speed pe chalta hai.

**OpenAI API (recommended for stability)** — series header mein *OpenAI API* toggle chuno, Settings mein key daalo:
- Koi browser nahi, koi layout break nahi, background mein chalta hai.
- Har image = master prompt + brief (dono saath jaate hain, isliye style same rehta hai).
- Per-image paisa lagta hai (platform.openai.com pe billing). `quality` = low/medium/high se cost control.
- Key sirf aapke laptop pe `settings.json` mein rehti hai.

Suggestion: roz ke volume ke liye **API engine** sabse reliable hai; ChatGPT engine tab use karo jab chat ki memory (same characters) zyada zaroori ho.

## 6. Troubleshooting
| Problem | Fix |
|---|---|
| "Chrome se connect nahi ho paya" | `start_chrome.bat` chalao; saare Chrome windows band karke dobara try. Browser mein http://localhost:9222/json/version khulna chahiye. |
| "Prompt box nahi mila" | Us Chrome mein ChatGPT login hai? Koi popup/verify screen? Haath se band karo, phir Generate. |
| Image aayi par save nahi hui | `outputs/.../error_*.png` dekho. Image timeout badhao. |
| `python` not found | Python dobara install, "Add to PATH" tick. |
| Port 5000 busy | `app.py` ki last line mein `port=5000` badal do. |
| Sab reset karna hai | App band karo, `studio.db` delete karo (images `outputs/` mein safe rahengi). |


---

## TEAM MODE — link + ek command (sab FREE)

```
 Teammate ka laptop                              Aapka PC (hub)
 ┌────────────────────────────┐   temporary    ┌───────────────────────────┐
 │ Browser → team link        │   https link   │ run.bat (app.py)          │
 │ 1 PowerShell command:      │ ◀──── kaam ─── │ series, briefs, posters,  │
 │  agent + unka ChatGPT      │ ── images ───▶ │ final, Excel (sab copy)   │
 │ Desktop\KahaniFM Outputs\  │                └───────────────────────────┘
 │   <Series>\*.webp / *.png  │
 └────────────────────────────┘
```

### Aapka roz ka kaam (hub PC)
1. `run.bat` chalao. Pehli baar `cloudflared` apne aap download hota hai (~20 MB, Cloudflare ka free "Quick Tunnel" — koi account nahi).
2. 10–20 second mein window mein bada sa **TEAM LINK** aata hai: `https://kuch-random-words.trycloudflare.com`. Dashboard ke left side **Team link** card pe bhi dikhta hai → **Copy**.
3. Ye link teammates ko bhejo (WhatsApp/Slack). **Har baar `run.bat` restart = naya link.** Jab tak `run.bat` window khuli aur PC on hai, link chalta hai.
4. PC ko sleep mein mat jaane do jab team kaam kar rahi ho.
5. Pehli baar: dashboard → **Team & my agent → Add teammate** (naam + password).

### Teammate ka kaam — bas ek command
1. Team link kholo → login.
2. Left neeche **Team & my agent** → **"Mera agent — bas ek command"** → **Copy**.
3. Windows: **Start → "PowerShell"** kholo → paste → Enter. (Mac: Terminal mein Mac wala command.)
4. Script khud karti hai: Python (nahi hai to install) → agent → naya Chrome khol ke chatgpt.com (pehli baar login karke Enter) → agent chalu.
5. PowerShell window **khuli rakho**. Dashboard pe ● green = ready.
6. Series bana ke **Generate** → images unke laptop pe yahan banti hain:
   `Desktop\KahaniFM Outputs\<Series Name>\<Series Name>.webp`, `<Episode Name>.png` …
   Saath hi har image hub (aapke PC) pe bhi aati hai — posters, final files, Excel wahi bante hain. Zip download ki zaroorat nahi.
7. **Agle din naya link** → naya link kholke command dobara copy-paste (command mein link hota hai). Doosri baar se setup skip ho jaata hai, seedha chalu.

### Notes
- Teammate ko kuch install nahi karna padta — sirf Google Chrome (ya Edge) hona chahiye.
- **Vercel kyun nahi?** Vercel pe sirf chhote serverless functions chalte hain — hamesha chalu process, database, Chrome automation wahan nahi chal sakte. Isliye hub aapke PC pe aur link Cloudflare ka.
- Link public hai → **strong passwords** rakho. Team chhodne wale ko remove karo / "New agent key".
- Mac hub pe: ek baar `brew install cloudflared`.
- Link na aaye (office firewall): Settings → **Team link** mein koi aur link (Tailscale Funnel / ngrok) paste kar sakte ho — `start_link.bat` (Tailscale Funnel) optional backup hai.
- Har teammate ka kaam alag-alag ek saath chal sakta hai. Stop button current image ke baad rokta hai.
- **Admin only:** Settings, teammates add/remove, password reset, New agent key, Folder buttons.

## 7. Files
```
app.py              Flask server + background worker + Excel log
db.py               SQLite (studio.db) — series & items
engine_browser.py   ChatGPT via your Chrome (Playwright CDP)
engine_api.py       OpenAI Images API engine
poster_site.py      Funda Poster Studio site automation (2:3 WebP posters)
agent/              Teammate agent (one-command installer isi se files leta hai)
templates/agent_install.ps1/.sh   Teammate ka one-command setup
allow_firewall.bat  Port 5000 kholta hai (Run as administrator)
tunnel.py           Free temporary team link (Cloudflare Quick Tunnel, auto)
start_link.bat      (optional) Tailscale Funnel link
imgconv.py          PNG / WebP / JPG conversion
templates/, static/ Dashboard (HTML/CSS/JS, offline — internet sirf ChatGPT/API ke liye)
run.bat / run.sh    Setup + start
start_chrome.bat    Chrome with debug port 9222
examples/sample_briefs.txt   Bulk paste format ka example
```
Data: `studio.db` (series, briefs, status, users) · `settings.json` · `secret.key` · `outputs/` (images + Excel).
Backup ke liye bas ye teen cheezein copy kar lo.
