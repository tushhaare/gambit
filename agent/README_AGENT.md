# KahaniFM Agent (teammates ke liye)

Ye chhota program aapke laptop pe chalta hai. Dashboard (hub) se kaam uthata hai, **aapke apne ChatGPT** mein thumbnails banwata hai aur image wapas hub pe bhej deta hai.

## Ek baar ka setup (Windows)
1. **Python 3.10+** install karo → https://www.python.org/downloads/ ("Add Python to PATH" tick karna).
2. Hub ka link Sagar dega (jaise `https://thumbnails.getmyfunda.com`). *Sirf agar Sagar ne Tailscale wala setup kiya ho* to Tailscale install karke invite accept karna padega.
3. Ye folder kahin bhi unzip karo (jaise `D:\KahaniFM-Agent`).
4. Browser mein hub link kholo → apne naam/password se login.
5. Left neeche **Team & my agent** → **Download agent.json** → file isi folder mein rakho.

## Roz ka kaam
1. `start_chrome.bat` double-click → alag Chrome khulega → pehli baar **chatgpt.com pe login** karo (yaad rahega).
2. `run_agent.bat` double-click → black window mein "Logged in as: <aapka naam>" aayega. **Window khuli rakho.**
3. Dashboard mein series kholo → header mein **Run on = "<aapka naam> ka ChatGPT"** → **Generate pending**.
4. Images ban ke seedha dashboard mein aa jaayengi. Final files **Download** button se lo.

Dashboard mein left neeche green dot = aapka agent online.

## Problem?
| Problem | Fix |
|---|---|
| "Hub se connect nahi ho paya" | Browser mein hub link khulta hai? Sagar ka PC on hai? (Tailscale setup ho to Tailscale on hai?) |
| "Agent key galat hai" | Dashboard se dobara agent.json download karo (admin ne naya key banaya ho sakta hai). |
| "Chrome se connect nahi ho paya" | Pehle `start_chrome.bat` chalao. |
| "Prompt box nahi mila" | Us Chrome mein ChatGPT login hai? Koi popup khula hai? |

Mac: `./start_chrome_mac.sh` aur `./run_agent_mac.sh`.
