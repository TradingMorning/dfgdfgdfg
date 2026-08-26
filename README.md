# YouTube Stream & Format Extractor (Android Innertube Engine)

A robust Web & CLI YouTube format extractor and downloader designed to **bypass YouTube Datacenter bot verification (`Sign in to confirm you're not a bot`)** without requiring cookies or paid proxies.

---

## 🚀 1. Local PC par Run karne ka Tareeqa

### Step 1: Dependencies Install Karein
```bash
pip install -r requirements.txt
```

### Option A: Web UI Run Karein (Browser me Dekhne ke liye)
```bash
python app.py
```
👉 Browser me open karein: `http://localhost:5000`

### Option B: Terminal CLI Run Karein
```bash
python cli.py
```
👉 URL enter karein, format number choose karein aur download shuru ho jayega!

---

## 🌐 2. GitHub se Render.com par Deploy karne ka Tareeqa (100% Free Cloud Server)

### Step 1: GitHub Repository Banayein
1. Apne GitHub account par new repo create karein (e.g. `yt-stream-hub`).
2. Is folder ke code ko push karein:
```bash
git init
git add .
git commit -m "Initial commit of YT Downloader"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/yt-stream-hub.git
git push -u origin main
```

### Step 2: Render.com par Deploy Karein
1. [Render.com](https://dashboard.render.com/) me login karein.
2. Click on **New +** -> **Web Service**.
3. Apni GitHub repo (`yt-stream-hub`) connect karein.
4. Settings enter karein:
   - **Name:** `yt-stream-downloader`
   - **Language / Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** `Free`
5. Click **Deploy Web Service**!

Render aapko ek live link de dega (e.g. `https://yt-stream-downloader.onrender.com`), jise aap mobile/PC kisi bhi device se use kar sakte hain.
