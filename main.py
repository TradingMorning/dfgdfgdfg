import re
import json
import urllib.request
import urllib.error
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse

app = FastAPI(title="StreamVault - Universal YouTube Engine", version="11.0.0")

# 1. Active Piped Nodes (Direct GoogleVideo CDN Stream URLs)
PIPED_NODES = [
    "https://pipedapi.kavin.rocks/streams/",
    "https://piped-api.lunar.icu/streams/",
    "https://api.piped.privacydev.net/streams/",
    "https://pipedapi.tokhmi.xyz/streams/"
]

# 2. Active Cobalt Clusters
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


def resolve_stream_url(video_id: str, quality: str = "1080", is_audio: bool = False) -> str:
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Method 1: Direct GoogleVideo CDN Resolver via Piped Nodes
    for p_node in PIPED_NODES:
        try:
            req = urllib.request.Request(
                f"{p_node}{video_id}",
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=4.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    
                    if is_audio:
                        audio_streams = data.get("audioStreams", [])
                        if audio_streams and audio_streams[0].get("url"):
                            print(f"[Resolver Success] Resolved audio from Piped: {p_node}")
                            return audio_streams[0]["url"]
                    else:
                        video_streams = data.get("videoStreams", [])
                        # Try to match requested quality
                        for st in video_streams:
                            if st.get("videoOnly") is False and (quality in st.get("quality", "") or quality == "best"):
                                print(f"[Resolver Success] Resolved {st.get('quality')} from Piped: {p_node}")
                                return st["url"]
                        
                        # Fallback to any progressive combined stream
                        for st in video_streams:
                            if st.get("videoOnly") is False and st.get("url"):
                                print(f"[Resolver Success] Resolved fallback stream from Piped: {p_node}")
                                return st["url"]
        except Exception as e:
            print(f"[Piped Node Warning] {p_node} error: {e}")
            continue

    # Method 2: Cobalt Cluster with required headers
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
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                    'Origin': 'https://cobalt.tools',
                    'Referer': 'https://cobalt.tools/'
                }
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode('utf-8'))
                    if data.get("url"):
                        print(f"[Cobalt Success] Resolved from {base_url}")
                        return data["url"]
        except Exception as e:
            print(f"[Cobalt Warning] {base_url} error: {e}")
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
            <i class="fa-solid fa-bolt"></i> Direct Google CDN Stream Engine
        </div>
        <h1 class="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-500">
            YouTube StreamVault
        </h1>
        <p class="text-gray-400 mt-2 text-sm">Download 1080p, 720p, 360p & MP3 Audio directly</p>
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
            <p class="text-gray-400 text-xs mt-2">Fetching video information...</p>
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
                    throw new Error(result.detail || "Unable to fetch video details.");
                }

                document.getElementById("videoTitle").innerText = result.data.title;
                document.getElementById("videoThumb").src = result.data.thumbnail;
                document.getElementById("videoUploader").innerText = result.data.uploader;

                const qContainer = document.getElementById("qualityButtons");
                qContainer.innerHTML = "";

                const formats = [
                    { label: "1080p Full HD", q: "1080", isAudio: false, icon: "fa-circle-play text-emerald-400" },
                    { label: "720p HD", q: "720", isAudio: false, icon: "fa-video text-indigo-400" },
                    { label: "360p Medium", q: "360", isAudio: false, icon: "fa-video text-blue-400" },
                    { label: "Audio Only (MP3)", q: "audio", isAudio: true, icon: "fa-music text-pink-400" }
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
# 2. METADATA API
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    stream_url = resolve_stream_url(video_id, quality=quality, is_audio=audio)

    if stream_url:
        return RedirectResponse(url=stream_url)

    raise HTTPException(status_code=500, detail="Could not resolve video stream. Please retry in a moment.")
