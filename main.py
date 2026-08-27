import os
import glob
import re
import shutil
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import yt_dlp

app = FastAPI(title="StreamVault - yt-dlp Engine", version="16.0.0")

DOWNLOADS_DIR = "/tmp/downloads"
COOKIES_SRC = "cookies.txt"
COOKIES_WRITABLE = "/tmp/cookies.txt"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def inspect_and_get_cookie_file():
    """Cookies ko inspect karta hai aur /tmp me copy karta hai."""
    if not os.path.exists(COOKIES_SRC):
        return None, "Missing cookies.txt", "amber"

    try:
        shutil.copy(COOKIES_SRC, COOKIES_WRITABLE)
        with open(COOKIES_WRITABLE, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        has_login = "LOGIN_INFO" in content or "SID" in content or "__Secure-3PAPISID" in content
        valid_lines = len([l for l in content.splitlines() if l.strip() and not l.startswith("#")])

        if has_login:
            return COOKIES_WRITABLE, f"Active: Authenticated Account ({valid_lines} cookies)", "emerald"
        else:
            return COOKIES_WRITABLE, f"Warning: Guest/Logged-Out Cookies ({valid_lines} cookies - May get blocked)", "rose"
    except Exception as e:
        return COOKIES_SRC, f"Error reading cookies: {e}", "amber"


def clean_url(url: str):
    url = url.strip()
    match = re.search(r'(?:youtu\.be\/|v\/|u\/\w\/|embed\/|watch\?v=|shorts\/)([^#\&\?\s]{11})', url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}", match.group(1)
    return url, url


def cleanup_file(filepath: str):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"[Cleanup] Deleted: {filepath}")
    except Exception as e:
        print(f"[Cleanup Error] {e}")


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


def get_base_ydl_opts(download: bool = False, quality: str = "best", video_id: str = ""):
    cookie_path, _, _ = inspect_and_get_cookie_file()

    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'compat_opts': ['no-youtube-prefer-oauth'],
        'http_headers': {'User-Agent': USER_AGENT},
        # mweb & web_creator bypass standard datacenter BotGuard checks with cookies
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb', 'web_creator', 'ios', 'tv_embedded']
            }
        }
    }

    if cookie_path and os.path.exists(cookie_path):
        opts['cookiefile'] = cookie_path

    if download:
        outtmpl_format = os.path.join(DOWNLOADS_DIR, f"{video_id}_%(resolution)s.%(ext)s")
        if quality == "audio":
            format_str = "bestaudio/best"
            merge_fmt = "m4a"
        elif quality == "best":
            format_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            merge_fmt = "mp4"
        else:
            height = quality.replace("p", "")
            format_str = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height}]+bestaudio/best"
            merge_fmt = "mp4"

        opts.update({
            'format': format_str,
            'outtmpl': outtmpl_format,
            'merge_output_format': merge_fmt
        })
    else:
        opts['skip_download'] = True

    return opts


# ==========================================
# 1. FRONTEND UI
# ==========================================
@app.get("/", response_class=HTMLResponse)
def home_ui():
    _, status_msg, color = inspect_and_get_cookie_file()
    badge_style = f"bg-{color}-500/10 border-{color}-500/20 text-{color}-400"

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StreamVault - YouTube Downloader</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    </style>
</head>
<body class="bg-[#080c14] text-gray-100 min-h-screen flex flex-col items-center justify-start p-4 sm:p-8">

    <header class="w-full max-w-3xl text-center my-8">
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full {badge_style} border text-xs font-semibold mb-3">
            <i class="fa-solid fa-cookie-bite"></i> {status_msg}
        </div>
        <h1 class="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-500">
            YouTube StreamVault
        </h1>
        <p class="text-gray-400 mt-2 text-sm">Download 1080p, 720p, 360p & MP3 via yt-dlp</p>
    </header>

    <main class="w-full max-w-3xl space-y-6">
        <div class="bg-[#121826] p-3 rounded-2xl border border-gray-800 flex flex-col sm:flex-row gap-2 shadow-2xl">
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
                <i class="fa-solid fa-bolt"></i>
                <span>Fetch Video</span>
            </button>
        </div>

        <div id="loader" class="hidden my-8 text-center">
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-500 border-t-transparent"></div>
            <p class="text-gray-400 text-xs mt-2">Extracting video metadata...</p>
        </div>

        <div id="errorAlert" class="hidden p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm"></div>

        <div id="detailsCard" class="hidden bg-[#121826] p-6 rounded-2xl border border-gray-800 shadow-2xl">
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
                        <label class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2 block">Available Download Formats:</label>
                        <div id="qualityButtons" class="flex flex-wrap gap-2"></div>
                    </div>
                </div>
            </div>
            
            <div id="downloadNotice" class="hidden mt-4 p-3 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs flex items-center gap-2">
                <i class="fa-solid fa-arrow-down animate-bounce"></i>
                <span>Server is preparing download...</span>
            </div>
        </div>
    </main>

    <script>
        let currentUrl = "";

        async function fetchDetails() {{
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
            currentUrl = urlInput;

            try {{
                const response = await fetch(`/api/info?url=${{encodeURIComponent(urlInput)}}`);
                const result = await response.json();

                if (!response.ok || result.status !== "success") {{
                    throw new Error(result.detail || "Unable to extract video details.");
                }}

                document.getElementById("videoTitle").innerText = result.data.title;
                document.getElementById("videoThumb").src = result.data.thumbnail;
                document.getElementById("videoUploader").innerText = result.data.uploader;
                document.getElementById("videoViews").innerText = result.data.views_formatted;
                document.getElementById("videoDuration").innerText = result.data.duration_formatted;

                const qContainer = document.getElementById("qualityButtons");
                qContainer.innerHTML = "";

                addDownloadBtn(qContainer, "Best Quality (Auto MP4)", "best", "fa-star text-yellow-400", true);

                result.data.available_resolutions.forEach(res => {{
                    addDownloadBtn(qContainer, res, res, "fa-video text-indigo-400", false);
                }});

                addDownloadBtn(qContainer, "Audio Only (M4A)", "audio", "fa-music text-pink-400", false);

                detailsCard.classList.remove("hidden");

            }} catch (err) {{
                errorAlert.innerText = err.message;
                errorAlert.classList.remove("hidden");
            }} finally {{
                loader.classList.add("hidden");
                fetchBtn.disabled = false;
            }}
        }}

        function addDownloadBtn(container, label, qualityKey, iconClass, isPrimary) {{
            const a = document.createElement("a");
            a.href = `/api/download?url=${{encodeURIComponent(currentUrl)}}&quality=${{qualityKey}}`;
            a.className = isPrimary
                ? "px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold text-white flex items-center gap-2 transition shadow-md"
                : "px-3.5 py-2 rounded-lg bg-[#1a2337] hover:bg-gray-800 border border-gray-700 text-xs font-medium text-gray-200 flex items-center gap-2 transition";
            a.innerHTML = `<i class="fa-solid ${{iconClass}}"></i> ${{label}}`;
            a.onclick = () => {{
                document.getElementById("downloadNotice").classList.remove("hidden");
            }};
            container.appendChild(a);
        }}

        document.getElementById("videoUrl").addEventListener("keypress", (e) => {{
            if (e.key === "Enter") fetchDetails();
        }});
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
    ydl_opts = get_base_ydl_opts(download=False, video_id=video_id)

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
                "data": {
                    "id": video_id,
                    "title": info.get("title"),
                    "uploader": info.get("uploader"),
                    "duration_seconds": info.get("duration", 0),
                    "duration_formatted": format_duration(info.get("duration", 0)),
                    "thumbnail": info.get("thumbnail"),
                    "views": info.get("view_count", 0),
                    "views_formatted": format_views(info.get("view_count", 0)),
                    "available_resolutions": sorted_resolutions
                }
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
    ydl_opts = get_base_ydl_opts(download=True, quality=quality, video_id=video_id)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_target_url, download=True)
            matched_files = glob.glob(os.path.join(DOWNLOADS_DIR, f"{video_id}_*"))
            if not matched_files:
                raise HTTPException(status_code=500, detail="Downloaded media file not found.")

            downloaded_file = matched_files[0]
            extension = downloaded_file.split(".")[-1]
            raw_title = info.get("title", "video")
            safe_title = "".join(c for c in raw_title if c.isalnum() or c in (' ', '-', '_')).rstrip()

            background_tasks.add_task(cleanup_file, downloaded_file)

            return FileResponse(
                path=downloaded_file,
                filename=f"{safe_title}.{extension}",
                media_type="video/mp4" if extension == "mp4" else "audio/mp4"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")
