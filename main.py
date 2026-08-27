import os
import glob
import re
import json
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import yt_dlp

app = FastAPI(title="YouTube Cloud Downloader", version="5.0.0")

DOWNLOADS_DIR = "/tmp/downloads"
TOKEN_FILE = "/tmp/yt_oauth_token.json"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def clean_url(url: str):
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


def get_ydl_options(download: bool = False, quality: str = "best", video_id: str = ""):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        # Force OAuth2 device login minted for this server's IP
        'username': 'oauth2',
        'password': '',
        'cachedir': '/tmp/yt_cache',
        'extractor_args': {
            'youtubetab': ['skip=authcheck'],
            'youtube': {
                'player_client': ['tv', 'web', 'android']
            }
        }
    }

    if download:
        outtmpl_format = os.path.join(DOWNLOADS_DIR, "%(id)s_%(resolution)s.%(ext)s")
        if quality == "best":
            format_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        else:
            height = quality.replace("p", "")
            format_str = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height}]+bestaudio/best"
        
        opts.update({
            'format': format_str,
            'outtmpl': outtmpl_format,
            'merge_output_format': 'mp4'
        })
    else:
        opts['skip_download'] = True

    return opts


# ==========================================
# 1. UI INTERFACE
# ==========================================
@app.get("/", response_class=HTMLResponse)
def home_ui():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StreamVault Cloud Downloader</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
    </style>
</head>
<body class="bg-[#0b0f19] text-gray-100 min-h-screen flex flex-col items-center justify-start p-4 sm:p-8">

    <header class="w-full max-w-3xl text-center my-8">
        <h1 class="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-500">
            StreamVault Server Engine
        </h1>
        <p class="text-gray-400 mt-2 text-sm">Server-Authenticated YouTube Stream Extractor</p>
    </header>

    <main class="w-full max-w-3xl space-y-6">
        <div class="bg-[#131927] p-3 rounded-2xl border border-gray-800 flex flex-col sm:flex-row gap-2">
            <input 
                type="text" 
                id="videoUrl" 
                placeholder="Paste YouTube Video URL here..."
                class="w-full bg-[#0b0f19] text-white px-4 py-3.5 rounded-xl border border-gray-800 focus:outline-none focus:border-indigo-500 text-sm"
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
            <p class="text-gray-400 text-xs mt-2">Processing request through server session...</p>
        </div>

        <div id="errorAlert" class="hidden p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm"></div>

        <div id="detailsCard" class="hidden bg-[#131927] p-6 rounded-2xl border border-gray-800">
            <div class="flex flex-col md:flex-row gap-6">
                <div class="relative rounded-xl overflow-hidden md:w-5/12 flex-shrink-0">
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
                    throw new Error(result.detail || "Failed to process video.");
                }

                document.getElementById("videoTitle").innerText = result.title;
                document.getElementById("videoThumb").src = result.thumbnail;
                document.getElementById("videoUploader").innerText = result.uploader;
                document.getElementById("videoViews").innerText = result.views_formatted;
                document.getElementById("videoDuration").innerText = result.duration_formatted;

                const qContainer = document.getElementById("qualityButtons");
                qContainer.innerHTML = "";

                const bestBtn = document.createElement("a");
                bestBtn.href = `/api/download?url=${encodeURIComponent(urlInput)}&quality=best`;
                bestBtn.className = "px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white";
                bestBtn.innerText = "Download Best MP4";
                qContainer.appendChild(bestBtn);

                result.available_resolutions.forEach(res => {
                    const btn = document.createElement("a");
                    btn.href = `/api/download?url=${encodeURIComponent(urlInput)}&quality=${res}`;
                    btn.className = "px-3.5 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-xs font-medium text-gray-200";
                    btn.innerText = res;
                    qContainer.appendChild(btn);
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
    clean_target_url, video_id = clean_url(url)
    ydl_opts = get_ydl_options(download=False, video_id=video_id)

    try:
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

            return JSONResponse(content={
                "status": "success",
                "id": video_id,
                "title": info.get("title"),
                "uploader": info.get("uploader"),
                "duration_seconds": info.get("duration"),
                "duration_formatted": format_duration(info.get("duration")),
                "thumbnail": info.get("thumbnail"),
                "views": info.get("view_count"),
                "views_formatted": format_views(info.get("view_count")),
                "available_resolutions": sorted_resolutions
            })

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    ydl_opts = get_ydl_options(download=True, quality=quality, video_id=video_id)

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
