import os
import glob
import re
import json
import urllib.request
import urllib.error
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import yt_dlp

app = FastAPI(title="StreamVault Universal Engine", version="9.0.0")

DOWNLOADS_DIR = "/tmp/downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# 10+ Active Decentralized High-Speed Nodes Pool
ACTIVE_MIRROR_NODES = [
    "https://invidious.nerdvpn.de/api/v1/videos/",
    "https://yt.artemislena.eu/api/v1/videos/",
    "https://invidious.jing.rocks/api/v1/videos/",
    "https://invidious.drgns.space/api/v1/videos/",
    "https://invidious.privacyredirect.com/api/v1/videos/",
    "https://inv.nadeko.net/api/v1/videos/"
]


def extract_video_id(url: str) -> str:
    url = url.strip()
    patterns = [
        r'(?:youtu\.be\/|v\/|u\/\w\/|embed\/|watch\?v=)([^#\&\?\s]{11})',
        r'shorts\/([^#\&\?\s]{11})',
        r'^([^#\&\?\s]{11})$'
    ]
    for p in patterns:
        match = re.search(p, url)
        if match:
            return match.group(1)
    raise ValueError("Invalid YouTube URL format.")


def format_views(views):
    if not views:
        return "N/A"
    try:
        views = int(views)
        if views >= 1_000_000:
            return f"{views / 1_000_000:.1f}M views"
        if views >= 1_000:
            return f"{views / 1_000:.1f}K views"
        return f"{views:,} views"
    except Exception:
        return str(views)


def format_duration(seconds):
    if not seconds:
        return "00:00"
    try:
        seconds = int(seconds)
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    except Exception:
        return "00:00"


# ==========================================
# 1. MODERN UI INTERFACE
# ==========================================
@app.get("/", response_class=HTMLResponse)
def home_ui():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StreamVault - Cloud Video Engine</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
    </style>
</head>
<body class="bg-[#080c14] text-gray-100 min-h-screen flex flex-col items-center justify-start p-4 sm:p-8">

    <header class="w-full max-w-3xl text-center my-8">
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold mb-3">
            <i class="fa-solid fa-bolt"></i> High-Speed Multi-Node Engine
        </div>
        <h1 class="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-500">
            YouTube StreamVault
        </h1>
        <p class="text-gray-400 mt-2 text-sm">Download High-Quality MP4 Video & Audio Streams</p>
    </header>

    <main class="w-full max-w-3xl space-y-6">
        <div class="bg-[#101623] p-3 rounded-2xl border border-gray-800 flex flex-col sm:flex-row gap-2 shadow-xl">
            <input 
                type="text" 
                id="videoUrl" 
                placeholder="Paste YouTube Video URL (e.g. https://youtu.be/...)"
                class="w-full bg-[#080c14] text-white px-4 py-3.5 rounded-xl border border-gray-800 focus:outline-none focus:border-indigo-500 text-sm"
            />
            <button 
                onclick="fetchDetails()" 
                id="fetchBtn"
                class="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-3.5 rounded-xl font-bold transition flex items-center justify-center gap-2 text-sm whitespace-nowrap shadow-lg shadow-indigo-600/30"
            >
                <i class="fa-solid fa-magnifying-glass"></i>
                <span>Get Video</span>
            </button>
        </div>

        <div id="loader" class="hidden my-8 text-center">
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-500 border-t-transparent"></div>
            <p class="text-gray-400 text-xs mt-2">Resolving video streams across nodes...</p>
        </div>

        <div id="errorAlert" class="hidden p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm"></div>

        <div id="detailsCard" class="hidden bg-[#101623] p-6 rounded-2xl border border-gray-800 shadow-2xl">
            <div class="flex flex-col md:flex-row gap-6">
                <div class="relative rounded-xl overflow-hidden md:w-5/12 flex-shrink-0 bg-black/50">
                    <img id="videoThumb" src="" alt="Thumbnail" class="w-full h-full object-cover rounded-xl" />
                    <span id="videoDuration" class="absolute bottom-2 right-2 bg-black/80 px-2 py-1 text-xs font-semibold rounded text-white font-mono"></span>
                </div>
                <div class="flex-grow flex flex-col justify-between">
                    <div>
                        <h2 id="videoTitle" class="text-lg font-bold text-white line-clamp-2"></h2>
                        <div class="flex items-center gap-4 mt-2 text-xs text-gray-400">
                            <span><i class="fa-solid fa-user text-indigo-400 mr-1"></i> <span id="videoUploader"></span></span>
                            <span><i class="fa-solid fa-eye text-purple-400 mr-1"></i> <span id="videoViews"></span></span>
                        </div>
                    </div>
                    <div class="mt-6">
                        <label class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2 block">Direct Download Formats:</label>
                        <div id="qualityButtons" class="flex flex-wrap gap-2"></div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <script>
        async function fetchDetails() {
            const urlInput = document.getElementById("videoUrl").value.trim();
            const loader = document.getElementById("loader");
            const detailsCard = document.getElementById("detailsCard");
            const errorAlert = document.getElementById("errorAlert");
            const fetchBtn = document.getElementById("fetchBtn");

            if (!urlInput) return;

            errorAlert.classList.add("hidden");
            detailsCard.classList.add("hidden");
            loader.classList.remove("hidden");
            fetchBtn.disabled = true;

            try {
                const response = await fetch(`/api/info?url=${encodeURIComponent(urlInput)}`);
                const result = await response.json();

                if (!response.ok || result.status !== "success") {
                    throw new Error(result.detail || "Unable to extract video details.");
                }

                document.getElementById("videoTitle").innerText = result.data.title;
                document.getElementById("videoThumb").src = result.data.thumbnail;
                document.getElementById("videoUploader").innerText = result.data.uploader;
                document.getElementById("videoViews").innerText = result.data.views_formatted;
                document.getElementById("videoDuration").innerText = result.data.duration_formatted;

                const qContainer = document.getElementById("qualityButtons");
                qContainer.innerHTML = "";

                result.data.downloads.forEach(dl => {
                    const a = document.createElement("a");
                    a.href = dl.url;
                    a.target = "_blank";
                    a.rel = "noreferrer";
                    a.className = "px-3.5 py-2 rounded-lg bg-[#182235] hover:bg-indigo-600/40 border border-gray-700 hover:border-indigo-500 text-xs font-medium text-white flex items-center gap-2 transition";
                    
                    let icon = "fa-video text-indigo-400";
                    if (dl.label.toLowerCase().includes("audio")) icon = "fa-music text-pink-400";
                    if (dl.label.includes("720p") || dl.label.includes("1080p")) icon = "fa-circle-play text-emerald-400";

                    a.innerHTML = `<i class="fa-solid ${icon}"></i> ${dl.label}`;
                    qContainer.appendChild(a);
                });

                detailsCard.classList.remove("hidden");

            } catch (err) {
                errorAlert.innerText = err.message;
                errorAlert.classList.remove("hidden");
            } finally {
                loader.classList.add("hidden");
                fetchBtn.disabled = false;
            }
        }
    </script>
</body>
</html>
    """


# ==========================================
# 2. MULTI-STRATEGY METADATA RESOLVER
# ==========================================
@app.get("/api/info")
def get_video_info(url: str = Query(..., description="YouTube video URL")):
    try:
        video_id = extract_video_id(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Strategy 1: Multi-Node Decentralized Resolvers
    for node_base in ACTIVE_MIRROR_NODES:
        try:
            req = urllib.request.Request(
                f"{node_base}{video_id}",
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    
                    downloads = []
                    # Combined Video + Audio formats
                    for s in data.get("formatStreams", []):
                        downloads.append({
                            "label": f"{s.get('qualityLabel', 'HD')} (MP4)",
                            "url": s.get("url")
                        })
                    
                    # Audio stream
                    for a in data.get("adaptiveFormats", []):
                        if "audio" in a.get("type", ""):
                            downloads.append({
                                "label": "Audio Only (M4A)",
                                "url": a.get("url")
                            })
                            break

                    if downloads:
                        return JSONResponse(content={
                            "status": "success",
                            "data": {
                                "id": video_id,
                                "title": data.get("title", "YouTube Video"),
                                "uploader": data.get("author", "YouTube Creator"),
                                "duration_seconds": data.get("lengthSeconds", 0),
                                "duration_formatted": format_duration(data.get("lengthSeconds", 0)),
                                "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                                "views": data.get("viewCount", 0),
                                "views_formatted": format_views(data.get("viewCount", 0)),
                                "downloads": downloads
                            }
                        })
        except Exception:
            continue

    # Strategy 2: Official YouTube oEmbed + Direct Client Stream Resolver
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                return JSONResponse(content={
                    "status": "success",
                    "data": {
                        "id": video_id,
                        "title": data.get("title"),
                        "uploader": data.get("author_name"),
                        "duration_seconds": 0,
                        "duration_formatted": "Ready",
                        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                        "views": 0,
                        "views_formatted": "N/A",
                        "downloads": [
                            {"label": "720p HD Video", "url": f"https://yt.artemislena.eu/latest_version?id={video_id}&itag=22"},
                            {"label": "360p Medium Video", "url": f"https://yt.artemislena.eu/latest_version?id={video_id}&itag=18"},
                            {"label": "Audio Stream (M4A)", "url": f"https://yt.artemislena.eu/latest_version?id={video_id}&itag=140"}
                        ]
                    }
                })
    except Exception:
        pass

    raise HTTPException(status_code=500, detail="All resolution channels are busy. Please retry in a moment.")
