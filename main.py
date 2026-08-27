import re
import json
import urllib.request
import urllib.error
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse

app = FastAPI(title="StreamVault - Universal YouTube Engine", version="10.0.0")

# Active High-Speed Cobalt API Clusters
COBALT_CLUSTERS = [
    "https://cobalt-api.kwiatekm.pl",
    "https://api.cobalt.tools",
    "https://cobalt.api.scip.io",
    "https://api.wuk.sh"
]


def extract_video_id(url: str) -> str:
    url = url.strip()
    match = re.search(r'(?:youtu\.be\/|v\/|u\/\w\/|embed\/|watch\?v=|shorts\/)([^#\&\?\s]{11})', url)
    if match:
        return match.group(1)
    raise ValueError("Invalid YouTube URL.")


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


def resolve_cobalt_download(video_url: str, quality: str = "1080", is_audio: bool = False) -> str:
    """Queries Cobalt cluster instances to get a direct high-speed download link."""
    payload = {
        "url": video_url,
        "videoQuality": quality if not is_audio else "720",
        "downloadMode": "audio" if is_audio else "auto",
        "audioFormat": "mp3"
    }
    req_body = json.dumps(payload).encode('utf-8')

    for base_url in COBALT_CLUSTERS:
        try:
            req = urllib.request.Request(
                f"{base_url}/",
                data=req_body,
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                }
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get("status") in ["stream", "redirect", "tunnel", "picker"] and data.get("url"):
                        return data.get("url")
                    if data.get("url"):
                        return data.get("url")
        except Exception:
            continue

    return ""


# ==========================================
# 1. FRONTEND UI
# ==========================================
@app.get("/", response_class=HTMLResponse)
def home_ui():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StreamVault - High Speed YouTube Downloader</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
    </style>
</head>
<body class="bg-[#090d16] text-gray-100 min-h-screen flex flex-col items-center justify-start p-4 sm:p-8">

    <header class="w-full max-w-3xl text-center my-8">
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-semibold mb-3">
            <i class="fa-solid fa-bolt"></i> High-Speed Direct CDN Active
        </div>
        <h1 class="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-500">
            YouTube StreamVault
        </h1>
        <p class="text-gray-400 mt-2 text-sm">Download 1080p, 720p, 360p & MP3 without SSL or Bot Errors</p>
    </header>

    <main class="w-full max-w-3xl space-y-6">
        <div class="bg-[#121826] p-3 rounded-2xl border border-gray-800 flex flex-col sm:flex-row gap-2 shadow-2xl">
            <input 
                type="text" 
                id="videoUrl" 
                placeholder="Paste YouTube Video URL (e.g. https://youtu.be/...)"
                class="w-full bg-[#090d16] text-white px-4 py-3.5 rounded-xl border border-gray-800 focus:outline-none focus:border-indigo-500 text-sm"
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
            <p class="text-gray-400 text-xs mt-2">Fetching direct video streams...</p>
        </div>

        <div id="errorAlert" class="hidden p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm"></div>

        <div id="detailsCard" class="hidden bg-[#121826] p-6 rounded-2xl border border-gray-800 shadow-2xl">
            <div class="flex flex-col md:flex-row gap-6">
                <div class="relative rounded-xl overflow-hidden md:w-5/12 flex-shrink-0 bg-black/50">
                    <img id="videoThumb" src="" alt="Thumbnail" class="w-full h-full object-cover rounded-xl" />
                </div>
                <div class="flex-grow flex flex-col justify-between">
                    <div>
                        <h2 id="videoTitle" class="text-lg font-bold text-white line-clamp-2"></h2>
                        <div class="flex items-center gap-4 mt-2 text-xs text-gray-400">
                            <span><i class="fa-solid fa-user text-indigo-400 mr-1"></i> <span id="videoUploader"></span></span>
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
                    throw new Error(result.detail || "Unable to fetch video details.");
                }

                document.getElementById("videoTitle").innerText = result.data.title;
                document.getElementById("videoThumb").src = result.data.thumbnail;
                document.getElementById("videoUploader").innerText = result.data.uploader;

                const qContainer = document.getElementById("qualityButtons");
                qContainer.innerHTML = "";

                // Formats list
                const formats = [
                    { label: "1080p Full HD", q: "1080", isAudio: false, icon: "fa-circle-play text-emerald-400" },
                    { label: "720p HD", q: "720", isAudio: false, icon: "fa-video text-indigo-400" },
                    { label: "360p Medium", q: "360", isAudio: false, icon: "fa-video text-blue-400" },
                    { label: "Audio (MP3)", q: "audio", isAudio: true, icon: "fa-music text-pink-400" }
                ];

                formats.forEach(f => {
                    const a = document.createElement("a");
                    a.href = `/api/download?url=${encodeURIComponent(urlInput)}&quality=${f.q}&audio=${f.isAudio}`;
                    a.target = "_blank";
                    a.className = "px-3.5 py-2 rounded-lg bg-[#1a2337] hover:bg-indigo-600/40 border border-gray-700 hover:border-indigo-500 text-xs font-medium text-white flex items-center gap-2 transition";
                    a.innerHTML = `<i class="fa-solid ${f.icon}"></i> ${f.label}`;
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
# 2. METADATA API (OFFICIAL OEMBED)
# ==========================================
@app.get("/api/info")
def get_video_info(url: str = Query(..., description="YouTube video URL")):
    try:
        video_id = extract_video_id(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    video_title = "YouTube Video"
    uploader = "YouTube Creator"
    thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                video_title = data.get("title", video_title)
                uploader = data.get("author_name", uploader)
                thumbnail = data.get("thumbnail_url", thumbnail)
    except Exception:
        pass

    return JSONResponse(content={
        "status": "success",
        "data": {
            "id": video_id,
            "title": video_title,
            "uploader": uploader,
            "thumbnail": thumbnail
        }
    })


# ==========================================
# 3. DIRECT DOWNLOAD HANDLER
# ==========================================
@app.get("/api/download")
def download_stream(
    url: str = Query(..., description="YouTube video URL"),
    quality: str = Query("1080"),
    audio: bool = Query(False)
):
    try:
        video_id = extract_video_id(url)
        clean_target_url = f"https://www.youtube.com/watch?v={video_id}"
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Resolve direct stream URL from Cobalt Cluster
    download_url = resolve_cobalt_download(clean_target_url, quality=quality, is_audio=audio)

    if download_url:
        return RedirectResponse(url=download_url)

    raise HTTPException(status_code=500, detail="Unable to generate direct stream link. Please retry.")
