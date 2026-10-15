# Deploying Gambit (Thumbnail Studio) on Netlify

This project is fully configured for deployment on Netlify using Netlify Serverless Functions (Python) and Netlify Edge CDN for static assets.

---

## 🚀 Quick Deployment (Two Options)

### Option 1: Git Push (Recommended)
1. Initialize git and commit your files (a `.gitignore` is already provided):
   ```bash
   git init
   git add .
   git commit -m "Deploy Gambit on Netlify"
   ```
2. Push the repository to GitHub, GitLab, or Bitbucket.
3. Open [Netlify Dashboard](https://app.netlify.com/) -> **Add new site** -> **Import an existing project**.
4. Select your repository. Netlify will automatically detect:
   - **Build command:** `python build_netlify.py`
   - **Publish directory:** `public`
   - **Functions directory:** `netlify/functions`
5. Click **Deploy Site**.

---

### Option 2: Netlify CLI
1. Install Netlify CLI:
   ```bash
   npm install -g netlify-cli
   ```
2. Log in and deploy:
   ```bash
   netlify login
   netlify init
   netlify deploy --prod
   ```

---

## ⚙️ Environment Variables (Netlify Site Settings)

Go to **Site settings** -> **Environment variables** in Netlify and configure:

| Variable | Description | Recommended Value |
|---|---|---|
| `SECRET_KEY` | Flask session secret key (keeps users logged in across serverless container restarts) | Any random 32+ character string (e.g. `openssl rand -hex 32`) |
| `OPENAI_API_KEY` | (Optional) OpenAI API key for API image generation | `sk-...` |
| `PYTHON_VERSION` | Python runtime version | `3.11` (preset in `netlify.toml`) |

---

## 💡 How It Works on Netlify

1. **Static CDN:** Files in `static/` (CSS, JS, libraries) are automatically prepared into `public/static/` by `build_netlify.py` during build and served directly by Netlify's global CDN.
2. **Serverless Functions:** Dynamic endpoints (`/`, `/api/*`, `/agent/*`, `/setup`, `/login`) run through `netlify/functions/app.py` via an optimized zero-dependency WSGI adapter.
3. **Team Mode:**
   - Your Netlify site URL (e.g. `https://your-studio.netlify.app`) acts as the central Hub.
   - Teammates open the URL in their browser and log in.
   - Teammates run their local agent (`agent.py`) using the one-line command from the dashboard.
   - The teammate's agent polls the Netlify Hub, generates thumbnails via their local ChatGPT/Chrome, and uploads completed images back to the Hub.

---

## ⚠️ Important Serverless Considerations

Netlify Serverless Functions run in an ephemeral execution environment (AWS Lambda):
- **Local Chrome / CDP:** A serverless cloud container does not run a desktop Chrome browser. Direct browser generation must be run through a teammate's agent (`Run on: <teammate>`), or via the OpenAI API engine.
- **Storage Persistence:** Files written to `/tmp` in serverless functions are temporary. For 24/7 persistent database and file storage without cold resets, you can also run this application on container platforms with persistent disks (like Render, Railway, Fly.io, or VPS) using `python app.py` or Waitress.
