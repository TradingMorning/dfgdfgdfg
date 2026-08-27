import os
import glob
import re
import json
import urllib.request
import urllib.error
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import yt_dlp

app = FastAPI(title="YouTube Downloader API", version="6.0.0")

DOWNLOADS_DIR = "/tmp/downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def extract_video_id(url: str) -> str:
    url = url.strip()
    match = re.search(r'(?:youtu\.be\/|v\/|u\/\w\/|embed\/|watch\?v=|shorts\/)([^#\&\?\s]{11})', url)
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
    <title>StreamVault - YouTube Engine</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
    </style>
</head>
<body class="bg-[#0a0e17] text-gray-100 min-h-screen flex flex-col items-center justify-start p-4 sm:p-8">

    <header class="w-full max-w-3xl text-center my-8">
        <h1 class="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-500">
            YouTube StreamVault
        </h1>
        <p class="text-gray-400 mt-2 text-sm">Direct YouTube Extraction Engine</p>
    </header>

    <main class="w-full max-w-3xl space-y-6">
        <div class="bg-[#131927] p-3 rounded-2xl border border-gray-800 flex flex-col sm:flex-row gap-2">
            <input 
                type="text" 
                id="videoUrl" 
                placeholder="Paste YouTube Video URL here..."
                class="w-full bg-[#0a0e17] text-white px-4 py-3.5 rounded-xl border border-gray-800 focus:outline-none focus:border-indigo-500 text-sm"
            />
            <button 
                onclick="fetchDetails()" 
                id="fetchBtn"
                class="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-3.5 rounded-xl font-bold transition flex items-center justify-center gap-2 text-sm whitespace-nowrap"
            >
                <i class="fa-solid fa-bolt"></i>
                <span>Fetch Video</span>
            </button>
        </div>

        <div id="loader" class="hidden my-8 text-center">
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-500 border-t-transparent"></div>
            <p class="text-gray-400 text-xs mt-2">Extracting video streams...</p>
        </div>

        <div id="errorAlert" class="hidden p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm"></div>

        <div id="detailsCard" class="hidden bg-[#131927] p-6 rounded-2xl border border-gray-800">
            <div class="flex flex-col md:flex-row gap-6">
                <div class="relative rounded-xl overflow-hidden md:w-5/12 flex-shrink-0 bg-black/50">
                    <img id="videoThumb" src="" alt="Thumbnail" class="w-full h-full object-cover rounded-xl" />
                    <span id="videoDuration" class="absolute bottom-2 right-2 bg-black/80 px-2 py-1 text-xs font-semibold rounded text-white font-mono"></span>
                </div>
                <div class="flex-grow flex flex-col justify-between">
                    <div>
                        <h2 id="videoTitle" class="text-lg font-bold text-white"></h2>
                        <div class="flex items-center gap-4 mt-2 text-xs text-gray-400">
                            <span id="videoUploader"></span>
                            <span id="videoViews"></span>
                        </div>
                    </div>
                    <div class="mt-6">
                        <label class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2 block">Download Streams:</label>
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
                    throw new Error(result.detail || "Failed to extract video details.");
                }

                document.getElementById("videoTitle").innerText = result.data.title;
                document.getElementById("videoThumb").src = result.data.thumbnail;
                document.getElementById("videoUploader").innerText = result.data.uploader;
                document.getElementById("videoViews").innerText = result.data.views_formatted;
                document.getElementById("videoDuration").innerText = result.data.duration_formatted;

                const qContainer = document.getElementById("qualityButtons");
                qContainer.innerHTML = "";

                if (result.data.formats && result.data.formats.length > 0) {
                    result.data.formats.forEach(f => {
                        const a = document.createElement("a");
                        a.href = f.url;
                        a.target = "_blank";
                        a.rel = "noreferrer";
                        a.className = "px-3.5 py-2 rounded-lg bg-indigo-600/30 hover:bg-indigo-600 border border-indigo-500 text-xs font-medium text-white flex items-center gap-2";
                        a.innerHTML = `<i class="fa-solid fa-download"></i> ${f.label}`;
                        qContainer.appendChild(a);
                    });
                } else {
                    const btn = document.createElement("a");
                    btn.href = `/api/download?url=${encodeURIComponent(urlInput)}&quality=best`;
                    btn.className = "px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white";
                    btn.innerText = "Download Best (MP4)";
                    qContainer.appendChild(btn);
                }

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
# 2. METADATA EXTRACTION
# ==========================================
@app.get("/api/info")
def get_video_info(url: str = Query(..., description="YouTube video URL")):
    try:
        video_id = extract_video_id(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 1. Primary Method: YouTube oEmbed + InnerTube Web Embedded
    video_title = "YouTube Video"
    uploader = "YouTube Creator"
    thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status == 200:
                oembed_data = json.loads(resp.read().decode('utf-8'))
                video_title = oembed_data.get("title", video_title)
                uploader = oembed_data.get("author_name", uploader)
                thumbnail = oembed_data.get("thumbnail_url", thumbnail)
    except Exception:
        pass

    # 2. Extract Streams using Embedded Innertube Clients
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['web_embedded', 'tv_embedded', 'android_embedded']
            }
        }
    }

    formats_list = []
    duration = 0
    views = 0

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            video_title = info.get("title", video_title)
            uploader = info.get("uploader", uploader)
            duration = info.get("duration", 0)
            views = info.get("view_count", 0)
            thumbnail = info.get("thumbnail", thumbnail)

            for f in info.get("formats", []):
                if f.get("url") and f.get("vcodec") != "none" and f.get("acodec") != "none":
                    height = f.get("height", "HD")
                    formats_list.append({
                        "label": f"{height}p (MP4)",
                        "url": f.get("url")
                    })
    except Exception:
        pass

    # Direct streams fallback if yt-dlp gets throttled
    if not formats_list:
        formats_list = [
            {"label": "720p HD Stream", "url": f"https://inv.tux.pizza/latest_version?id={video_id}&itag=22"},
            {"label": "360p Medium Stream", "url": f"https://inv.tux.pizza/latest_version?id={video_id}&itag=18"},
            {"label": "Audio Only (M4A)", "url": f"https://inv.tux.pizza/latest_version?id={video_id}&itag=140"}
        ]

    return JSONResponse(content={
        "status": "success",
        "data": {
            "id": video_id,
            "title": video_title,
            "uploader": uploader,
            "duration_seconds": duration,
            "duration_formatted": format_duration(duration),
            "thumbnail": thumbnail,
            "views": views,
            "views_formatted": format_views(views),
            "formats": formats_list[:4]
        }
    })


# ==========================================
# 3. DOWNLOAD HANDLER
# ==========================================
@app.get("/api/download")
def download_video(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="YouTube video URL"),
    quality: str = Query("best")
):
    try:
        video_id = extract_video_id(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    outtmpl_format = os.path.join(DOWNLOADS_DIR, f"{video_id}.%(ext)s")
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': outtmpl_format,
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['web_embedded', 'tv_embedded', 'android_embedded']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            matched_files = glob.glob(os.path.join(DOWNLOADS_DIR, f"{video_id}.*"))
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
