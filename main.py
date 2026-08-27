import os
import glob
import re
import datetime
import httpx
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import yt_dlp

app = FastAPI(title="StreamVault - Debug & Download Engine", version="3.5.0")

DOWNLOADS_DIR = "/tmp/downloads"
COOKIES_FILE = "/tmp/cookies.txt"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


# ==========================================
# COOKIE VALIDATION & REPAIR ENGINE
# ==========================================
def inspect_and_write_cookies() -> dict:
    """
    Render ke Environment se cookies read karke fix karta hai aur detailed stats deta hai.
    """
    raw_cookies = os.getenv("YOUTUBE_COOKIES", "").strip()
    
    if not raw_cookies and os.path.exists("cookies.txt"):
        with open("cookies.txt", "r", encoding="utf-8") as f:
            raw_cookies = f.read().strip()

    if not raw_cookies:
        return {"loaded": False, "reason": "No YOUTUBE_COOKIES found in Environment or local cookies.txt", "lines": 0}

    # Render escaped newlines ko actual newlines me convert karna
    raw_cookies = raw_cookies.replace("\\n", "\n").replace("\\t", "\t")

    lines = [line.strip() for line in raw_cookies.splitlines() if line.strip()]
    
    # Netscape Header ensure karna
    content_lines = []
    if not any("Netscape" in line for line in lines[:3]):
        content_lines.append("# Netscape HTTP Cookie File")
        content_lines.append("# http://curl.haxx.se/rfc/cookie_spec.html")
    
    valid_cookie_count = 0
    for line in lines:
        if not line.startswith("#") and len(line.split()) >= 6:
            valid_cookie_count += 1
        content_lines.append(line)

    fixed_cookie_data = "\n".join(content_lines) + "\n"
    
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        f.write(fixed_cookie_data)

    return {
        "loaded": True,
        "path": COOKIES_FILE,
        "total_lines": len(lines),
        "valid_cookies": valid_cookie_count,
        "file_size": len(fixed_cookie_data)
    }


def clean_url(url: str) -> str:
    url = url.strip()
    match = re.search(r'(?:youtu\.be\/|v\/|u\/\w\/|embed\/|watch\?v=)([^#\&\?\s]{11})', url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}", match.group(1)
    return url, url


def format_views(views):
    if not views:
        return "N/A"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M views"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K views"
    return f"{views:,} views"


def format_duration(seconds):
    if not seconds:
        return "00:00"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ==========================================
# 1. LIVE DEBUGGING UI (FRONTEND)
# ==========================================
@app.get("/", response_class=HTMLResponse)
def home_ui():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StreamVault - Live Diagnostics & Downloader</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        .glass-panel {
            background: rgba(19, 25, 39, 0.7);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .custom-scroll::-webkit-scrollbar { width: 6px; }
        .custom-scroll::-webkit-scrollbar-track { background: rgba(0,0,0,0.2); }
        .custom-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
    </style>
</head>
<body class="bg-[#080c14] text-gray-100 min-h-screen flex flex-col items-center justify-start p-4 sm:p-6">

    <!-- Header -->
    <header class="w-full max-w-4xl text-center my-6">
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold mb-3">
            <i class="fa-solid fa-terminal"></i> Live Cloud Diagnostic Console
        </div>
        <h1 class="text-3xl sm:text-5xl font-extrabold tracking-tight">
            YouTube <span class="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-500">StreamVault</span>
        </h1>
    </header>

    <main class="w-full max-w-4xl space-y-6">
        <!-- Input Box -->
        <div class="glass-panel p-3 rounded-2xl shadow-xl flex flex-col sm:flex-row gap-2">
            <div class="relative flex-grow flex items-center">
                <i class="fa-brands fa-youtube text-red-500 absolute left-4 text-xl"></i>
                <input 
                    type="text" 
                    id="videoUrl" 
                    placeholder="Paste YouTube link here..."
                    class="w-full bg-[#101623] text-white pl-12 pr-4 py-3.5 rounded-xl border border-gray-800 focus:outline-none focus:border-indigo-500 transition text-sm"
                />
            </div>
            <button 
                onclick="runDiagnosticFetch()" 
                id="fetchBtn"
                class="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-3.5 rounded-xl font-bold transition flex items-center justify-center gap-2 text-sm whitespace-nowrap"
            >
                <i class="fa-solid fa-play"></i>
                <span>Fetch & Diagnose</span>
            </button>
        </div>

        <!-- Live Terminal Logs Console -->
        <div class="glass-panel rounded-2xl p-4 border border-gray-800 shadow-2xl">
            <div class="flex items-center justify-between pb-3 border-b border-gray-800 text-xs">
                <div class="flex items-center gap-2">
                    <span class="w-3 h-3 rounded-full bg-red-500 inline-block"></span>
                    <span class="w-3 h-3 rounded-full bg-yellow-500 inline-block"></span>
                    <span class="w-3 h-3 rounded-full bg-green-500 inline-block"></span>
                    <span class="text-gray-400 font-mono font-bold ml-2">LIVE CLOUD EXECUTION LOGS</span>
                </div>
                <span id="logStatusBadge" class="text-gray-500 font-mono">READY</span>
            </div>
            <div id="terminalLogs" class="font-mono text-xs text-gray-300 mt-3 h-44 overflow-y-auto space-y-1.5 custom-scroll p-2 bg-[#0a0e17] rounded-xl border border-gray-900">
                <p class="text-gray-600">// Waiting for URL input... Live events will appear here in real-time.</p>
            </div>
        </div>

        <!-- Video Result Display -->
        <div id="detailsCard" class="hidden glass-panel p-6 rounded-2xl border border-gray-800 shadow-2xl">
            <div class="flex flex-col md:flex-row gap-6">
                <div class="relative rounded-xl overflow-hidden md:w-5/12 flex-shrink-0 bg-black/50">
                    <img id="videoThumb" src="" alt="Thumbnail" class="w-full h-full object-cover rounded-xl" />
                    <span id="videoDuration" class="absolute bottom-2 right-2 bg-black/80 px-2 py-1 text-xs font-semibold rounded text-white font-mono"></span>
                </div>
                <div class="flex-grow flex flex-col justify-between">
                    <div>
                        <h2 id="videoTitle" class="text-lg sm:text-xl font-bold leading-snug text-white"></h2>
                        <div class="flex items-center gap-4 mt-2 text-xs text-gray-400">
                            <span><i class="fa-solid fa-user-circle text-indigo-400 mr-1"></i> <span id="videoUploader"></span></span>
                            <span><i class="fa-solid fa-eye text-purple-400 mr-1"></i> <span id="videoViews"></span></span>
                        </div>
                    </div>
                    <div class="mt-6">
                        <label class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2 block">Download Options:</label>
                        <div id="qualityButtons" class="flex flex-wrap gap-2"></div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <script>
        function addLog(msg, type = "info") {
            const term = document.getElementById("terminalLogs");
            const time = new Date().toLocaleTimeString();
            let color = "text-gray-300";
            let icon = "⚡";

            if (type === "success") { color = "text-emerald-400"; icon = "✅"; }
            else if (type === "warn") { color = "text-amber-400"; icon = "⚠️"; }
            else if (type === "error") { color = "text-rose-400"; icon = "❌"; }
            else if (type === "cookie") { color = "text-cyan-400"; icon = "🍪"; }

            const p = document.createElement("p");
            p.className = `${color} leading-relaxed`;
            p.innerHTML = `<span class="text-gray-600">[${time}]</span> ${icon} ${msg}`;
            term.appendChild(p);
            term.scrollTop = term.scrollHeight;
        }

        async function runDiagnosticFetch() {
            const urlInput = document.getElementById("videoUrl").value.trim();
            const term = document.getElementById("terminalLogs");
            const detailsCard = document.getElementById("detailsCard");
            const badge = document.getElementById("logStatusBadge");
            const fetchBtn = document.getElementById("fetchBtn");

            if (!urlInput) {
                alert("Please paste a valid YouTube URL.");
                return;
            }

            term.innerHTML = "";
            detailsCard.classList.add("hidden");
            badge.innerText = "RUNNING...";
            badge.className = "text-amber-400 font-mono animate-pulse";
            fetchBtn.disabled = true;

            addLog(`Received request for: <span class="text-white">${urlInput}</span>`);

            try {
                const response = await fetch(`/api/info?url=${encodeURIComponent(urlInput)}`);
                const result = await response.json();

                // Backend se jo logs aaye unhe terminal me render karna
                if (result.logs && Array.isArray(result.logs)) {
                    result.logs.forEach(l => addLog(l.message, l.type));
                }

                if (!response.ok || result.status !== "success") {
                    badge.innerText = "FAILED";
                    badge.className = "text-rose-400 font-mono";
                    addLog(result.detail || "Execution failed.", "error");
                    return;
                }

                badge.innerText = "SUCCESS";
                badge.className = "text-emerald-400 font-mono";

                // Populate Card
                document.getElementById("videoTitle").innerText = result.data.title;
                document.getElementById("videoThumb").src = result.data.thumbnail;
                document.getElementById("videoUploader").innerText = result.data.uploader;
                document.getElementById("videoViews").innerText = result.data.views_formatted;
                document.getElementById("videoDuration").innerText = result.data.duration_formatted;

                const qContainer = document.getElementById("qualityButtons");
                qContainer.innerHTML = "";

                // Best Quality Button
                const bestBtn = document.createElement("a");
                bestBtn.href = `/api/download?url=${encodeURIComponent(urlInput)}&quality=best`;
                bestBtn.className = "px-3.5 py-2 rounded-lg bg-indigo-600/30 hover:bg-indigo-600 border border-indigo-500 text-xs font-semibold flex items-center gap-2 text-white";
                bestBtn.innerHTML = `<i class="fa-solid fa-star text-yellow-400"></i> Best Quality (Auto MP4)`;
                qContainer.appendChild(bestBtn);

                // Other formats
                result.data.available_resolutions.forEach(res => {
                    const btn = document.createElement("a");
                    btn.href = `/api/download?url=${encodeURIComponent(urlInput)}&quality=${res}`;
                    btn.className = "px-3.5 py-2 rounded-lg bg-[#182032] hover:bg-gray-800 border border-gray-700 text-xs font-medium flex items-center gap-2 text-gray-200";
                    btn.innerHTML = `<i class="fa-solid fa-video text-indigo-400"></i> ${res}`;
                    qContainer.appendChild(btn);
                });

                detailsCard.classList.remove("hidden");

            } catch (err) {
                badge.innerText = "NETWORK ERROR";
                badge.className = "text-rose-400 font-mono";
                addLog(`Network Exception: ${err.message}`, "error");
            } finally {
                fetchBtn.disabled = false;
            }
        }

        document.getElementById("videoUrl").addEventListener("keypress", (e) => {
            if (e.key === "Enter") runDiagnosticFetch();
        });
    </script>
</body>
</html>
    """


# ==========================================
# 2. DIAGNOSTIC API WITH LIVE LOGS
# ==========================================
@app.get("/api/info")
async def get_video_info(url: str = Query(..., description="YouTube video URL")):
    logs = []
    
    clean_target_url, video_id = clean_url(url)
    logs.append({"type": "info", "message": f"Cleaned Video ID: <b>{video_id}</b>"})

    # 1. Cookie Status Check
    cookie_stats = inspect_and_write_cookies()
    if cookie_stats["loaded"]:
        logs.append({
            "type": "cookie", 
            "message": f"Cookie loaded: <b>{cookie_stats['valid_cookies']} valid entries</b> parsed from Environment ({cookie_stats['file_size']} bytes)."
        })
    else:
        logs.append({
            "type": "warn", 
            "message": f"Cookie status: {cookie_stats['reason']} (Attempting unauthenticated fallback)."
        })

    # 2. Attempt Extraction via yt-dlp
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb', 'web_creator', 'tv_embedded']
            }
        }
    }
    if cookie_stats["loaded"]:
        ydl_opts['cookiefile'] = cookie_stats["path"]

    try:
        logs.append({"type": "info", "message": "Querying YouTube API with multi-client engine..."})
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_target_url, download=False)
            
            formats = info.get('formats', [])
            resolutions = set()
            for f in formats:
                if f.get('height') and f.get('height') >= 360:
                    resolutions.add(f"{f.get('height')}p")

            sorted_resolutions = sorted(
                list(resolutions),
                key=lambda x: int(x.replace('p', '')) if x.replace('p', '').isdigit() else 0,
                reverse=True
            )

            logs.append({"type": "success", "message": f"Metadata successfully extracted: '{info.get('title')}'"})

            return JSONResponse(content={
                "status": "success",
                "logs": logs,
                "data": {
                    "id": video_id,
                    "title": info.get("title"),
                    "uploader": info.get("uploader"),
                    "duration_seconds": info.get("duration"),
                    "duration_formatted": format_duration(info.get("duration")),
                    "thumbnail": info.get("thumbnail"),
                    "views": info.get("view_count"),
                    "views_formatted": format_views(info.get("view_count")),
                    "available_resolutions": sorted_resolutions
                }
            })

    except Exception as yt_err:
        err_msg = str(yt_err)
        logs.append({"type": "error", "message": f"yt-dlp error: {err_msg[:120]}..."})
        
        # 3. Automatic Failover to Decentralized Resolver
        logs.append({"type": "warn", "message": "Triggering automatic mirror resolver fallback..."})
        
        async with httpx.AsyncClient(timeout=6.0) as client:
            resolvers = [
                f"https://invidious.nerdvpn.de/api/v1/videos/{video_id}",
                f"https://inv.tux.pizza/api/v1/videos/{video_id}",
                f"https://yt.artemislena.eu/api/v1/videos/{video_id}"
            ]
            for r_url in resolvers:
                try:
                    resp = await client.get(r_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        logs.append({"type": "success", "message": f"Mirror resolved stream details successfully!"})
                        return JSONResponse(content={
                            "status": "success",
                            "logs": logs,
                            "data": {
                                "id": video_id,
                                "title": data.get("title"),
                                "uploader": data.get("author"),
                                "duration_seconds": data.get("lengthSeconds"),
                                "duration_formatted": format_duration(data.get("lengthSeconds")),
                                "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                                "views": data.get("viewCount"),
                                "views_formatted": format_views(data.get("viewCount")),
                                "available_resolutions": ["1080p", "720p", "480p", "360p"]
                            }
                        })
                except Exception:
                    continue

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "logs": logs,
                "detail": "Failed on both yt-dlp and mirror resolvers. Check cookies or try another URL."
            }
        )


# ==========================================
# 3. DOWNLOAD HANDLER
# ==========================================
@app.get("/api/download")
def download_video(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="YouTube video URL"),
    quality: str = Query("best")
):
    clean_target_url, video_id = clean_url(url)
    cookie_stats = inspect_and_write_cookies()

    outtmpl_format = os.path.join(DOWNLOADS_DIR, "%(id)s_%(resolution)s.%(ext)s")

    if quality == "best":
        format_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    else:
        height = quality.replace("p", "")
        format_str = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height}]+bestaudio/best"

    ydl_opts = {
        'format': format_str,
        'outtmpl': outtmpl_format,
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb', 'web_creator', 'tv_embedded']
            }
        }
    }
    if cookie_stats["loaded"]:
        ydl_opts['cookiefile'] = cookie_stats["path"]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_target_url, download=True)
            matched_files = glob.glob(os.path.join(DOWNLOADS_DIR, f"{video_id}_*"))
            if not matched_files:
                raise HTTPException(status_code=500, detail="Downloaded media file not found.")

            downloaded_file = matched_files[0]
            raw_title = info.get("title", "video")
            safe_title = "".join(c for c in raw_title if c.isalnum() or c in (' ', '-', '_')).rstrip()

            background_tasks.add_task(lambda f: os.remove(f) if os.path.exists(f) else None, downloaded_file)

            return FileResponse(
                path=downloaded_file,
                filename=f"{safe_title}.mp4",
                media_type="video/mp4"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")
