import os 
import glob
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import yt_dlp

app = FastAPI(title="YouTube Downloader & Info API", version="2.0.0")

DOWNLOADS_DIR = "/tmp/downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def cleanup_file(filepath: str):
    """File user ko send hone ke baad delete karta hai taaki server storage clean rahe."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"[Cleanup] Deleted: {filepath}")
    except Exception as e:
        print(f"[Cleanup Error] {e}")


def format_views(views):
    if not views:
        return "N/A"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M views"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K views"
    return f"{views} views"


def format_duration(seconds):
    if not seconds:
        return "00:00"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ==========================================
# 1. EMBEDDED MODERN UI (HOME PAGE)
# ==========================================
@app.get("/", response_class=HTMLResponse)
def home_ui():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StreamVault - Modern YouTube Downloader</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- FontAwesome Icons -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
        .glass-panel {
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .gradient-text {
            background: linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .glow-btn {
            box-shadow: 0 0 25px -5px rgba(99, 102, 241, 0.5);
        }
    </style>
</head>
<body class="bg-[#0b0f19] text-gray-100 min-h-screen flex flex-col items-center justify-start p-4 sm:p-8">

    <!-- Header -->
    <header class="w-full max-w-4xl text-center my-8">
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-sm font-medium mb-4">
            <i class="fa-solid fa-bolt"></i> High-Speed Cloud Server Engine
        </div>
        <h1 class="text-4xl sm:text-6xl font-extrabold tracking-tight">
            YouTube <span class="gradient-text">StreamVault</span>
        </h1>
        <p class="text-gray-400 mt-3 text-sm sm:text-base max-w-lg mx-auto">
            Extract high-definition video details & download MP4 in 4K, 1080p, 720p or MP3 without speed throttling.
        </p>
    </header>

    <!-- Main Card -->
    <main class="w-full max-w-3xl">
        <!-- Input Form -->
        <div class="glass-panel p-3 sm:p-4 rounded-2xl shadow-2xl flex flex-col sm:flex-row gap-2">
            <div class="relative flex-grow flex items-center">
                <i class="fa-brands fa-youtube text-red-500 absolute left-4 text-xl"></i>
                <input 
                    type="text" 
                    id="videoUrl" 
                    placeholder="Paste YouTube Video URL here (e.g. https://youtu.be/...)"
                    class="w-full bg-[#131927] text-white pl-12 pr-4 py-3.5 rounded-xl border border-gray-800 focus:outline-none focus:border-indigo-500 transition text-sm sm:text-base placeholder-gray-500"
                />
            </div>
            <button 
                onclick="fetchVideoDetails()" 
                id="fetchBtn"
                class="bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white px-6 py-3.5 rounded-xl font-semibold transition flex items-center justify-center gap-2 glow-btn text-sm sm:text-base whitespace-nowrap"
            >
                <i class="fa-solid fa-magnifying-glass"></i>
                <span>Fetch Details</span>
            </button>
        </div>

        <!-- Loader Spinner -->
        <div id="loader" class="hidden my-12 text-center">
            <div class="inline-block animate-spin rounded-full h-10 w-10 border-4 border-indigo-500 border-t-transparent"></div>
            <p class="text-gray-400 text-sm mt-3 animate-pulse">Extracting metadata from YouTube servers...</p>
        </div>

        <!-- Error Alert -->
        <div id="errorAlert" class="hidden mt-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-3">
            <i class="fa-solid fa-circle-exclamation text-lg"></i>
            <span id="errorMessage">Failed to fetch video details. Please check the URL.</span>
        </div>

        <!-- Video Details Card (Hidden by default) -->
        <div id="detailsCard" class="hidden mt-8 glass-panel p-6 rounded-2xl border border-gray-800 shadow-2xl">
            <div class="flex flex-col md:flex-row gap-6">
                <!-- Thumbnail with Duration -->
                <div class="relative rounded-xl overflow-hidden md:w-5/12 flex-shrink-0 bg-black/40">
                    <img id="videoThumb" src="" alt="Thumbnail" class="w-full h-full object-cover rounded-xl" />
                    <span id="videoDuration" class="absolute bottom-2 right-2 bg-black/80 px-2 py-1 text-xs font-semibold rounded text-white"></span>
                </div>

                <!-- Info Column -->
                <div class="flex-grow flex flex-col justify-between">
                    <div>
                        <h2 id="videoTitle" class="text-lg sm:text-xl font-bold leading-snug line-clamp-2 text-white"></h2>
                        <div class="flex items-center gap-4 mt-2 text-xs sm:text-sm text-gray-400">
                            <span class="flex items-center gap-1.5"><i class="fa-solid fa-user-circle text-indigo-400"></i> <span id="videoUploader"></span></span>
                            <span class="flex items-center gap-1.5"><i class="fa-solid fa-eye text-purple-400"></i> <span id="videoViews"></span></span>
                        </div>
                    </div>

                    <!-- Quality / Download Options -->
                    <div class="mt-6">
                        <label class="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2 block">
                            Select Quality to Download:
                        </label>
                        <div id="qualityButtons" class="flex flex-wrap gap-2">
                            <!-- Dynamic Quality Buttons injected here -->
                        </div>
                    </div>
                </div>
            </div>

            <!-- Download Status Banner -->
            <div id="downloadStatus" class="hidden mt-6 p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-sm flex items-center justify-between">
                <div class="flex items-center gap-2.5">
                    <i class="fa-solid fa-arrow-down animate-bounce"></i>
                    <span>Processing download on server, please wait...</span>
                </div>
                <span class="text-xs text-gray-400 font-mono">Format: MP4</span>
            </div>
        </div>
    </main>

    <!-- Footer -->
    <footer class="mt-auto py-8 text-center text-xs text-gray-600">
        <p>Built with FastAPI & yt-dlp • Designed for Cloud Deployment</p>
    </footer>

    <!-- Script Logic -->
    <script>
        let currentVideoUrl = "";

        async function fetchVideoDetails() {
            const urlInput = document.getElementById("videoUrl").value.trim();
            const loader = document.getElementById("loader");
            const detailsCard = document.getElementById("detailsCard");
            const errorAlert = document.getElementById("errorAlert");
            const fetchBtn = document.getElementById("fetchBtn");

            if (!urlInput) {
                showError("Please paste a valid YouTube video link.");
                return;
            }

            // UI Reset
            errorAlert.classList.add("hidden");
            detailsCard.classList.add("hidden");
            loader.classList.remove("hidden");
            fetchBtn.disabled = true;
            fetchBtn.classList.add("opacity-50");

            currentVideoUrl = urlInput;

            try {
                const response = await fetch(`/api/info?url=${encodeURIComponent(urlInput)}`);
                const data = await response.json();

                if (!response.ok || data.status !== "success") {
                    throw new Error(data.detail || "Unable to extract video information.");
                }

                // Populate Data
                document.getElementById("videoTitle").innerText = data.title;
                document.getElementById("videoThumb").src = data.thumbnail;
                document.getElementById("videoUploader").innerText = data.uploader || "Unknown";
                document.getElementById("videoViews").innerText = data.views_formatted;
                document.getElementById("videoDuration").innerText = data.duration_formatted;

                // Render Quality Buttons
                const container = document.getElementById("qualityButtons");
                container.innerHTML = "";

                // Best Quality Button
                addQualityButton(container, "Best Quality (Auto)", "best", "fa-star text-yellow-400");

                // Specific Resolutions
                data.available_resolutions.forEach(res => {
                    addQualityButton(container, res, res, "fa-video text-indigo-400");
                });

                // Audio Only Button
                addQualityButton(container, "Audio Only", "audio", "fa-music text-pink-400");

                detailsCard.classList.remove("hidden");

            } catch (err) {
                showError(err.message || "Failed to load video details.");
            } finally {
                loader.classList.add("hidden");
                fetchBtn.disabled = false;
                fetchBtn.classList.remove("opacity-50");
            }
        }

        function addQualityButton(container, label, qualityKey, iconClass) {
            const btn = document.createElement("button");
            btn.className = "px-3.5 py-2 rounded-lg bg-[#182032] hover:bg-indigo-600/30 border border-gray-700 hover:border-indigo-500 text-xs sm:text-sm font-medium transition flex items-center gap-2";
            btn.innerHTML = `<i class="fa-solid ${iconClass}"></i> ${label}`;
            btn.onclick = () => triggerDownload(qualityKey);
            container.appendChild(btn);
        }

        function triggerDownload(quality) {
            const downloadStatus = document.getElementById("downloadStatus");
            downloadStatus.classList.remove("hidden");

            const downloadUrl = `/api/download?url=${encodeURIComponent(currentVideoUrl)}&quality=${quality}`;
            
            // Trigger direct file download in browser
            window.location.href = downloadUrl;

            setTimeout(() => {
                downloadStatus.classList.add("hidden");
            }, 8000);
        }

        function showError(msg) {
            const errorAlert = document.getElementById("errorAlert");
            document.getElementById("errorMessage").innerText = msg;
            errorAlert.classList.remove("hidden");
        }

        // Enter Key Listener
        document.getElementById("videoUrl").addEventListener("keypress", function(event) {
            if (event.key === "Enter") {
                event.preventDefault();
                fetchVideoDetails();
            }
        });
    </script>
</body>
</html>
    """


# ==========================================
# 2. METADATA API ENDPOINT
# ==========================================
@app.get("/api/info")
def get_video_info(url: str = Query(..., description="YouTube video URL")):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded', 'ios', 'android', 'web']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

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
                "id": info.get("id"),
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
        raise HTTPException(status_code=400, detail=f"Failed to fetch video details: {str(e)}")


# ==========================================
# 3. DOWNLOAD & STREAM ENDPOINT
# ==========================================
@app.get("/api/download")
def download_video(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="YouTube video URL"),
    quality: str = Query("best", description="Quality: 'best', '1080p', '720p', 'audio'")
):
    outtmpl_format = os.path.join(DOWNLOADS_DIR, "%(id)s_%(resolution)s.%(ext)s")

    if quality == "audio":
        format_str = "bestaudio/best"
        merge_fmt = "m4a"
        media_type = "audio/mp4"
    elif quality == "best":
        format_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        merge_fmt = "mp4"
        media_type = "video/mp4"
    else:
        height = quality.replace("p", "")
        format_str = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height}]+bestaudio/best"
        merge_fmt = "mp4"
        media_type = "video/mp4"

    ydl_opts = {
        'format': format_str,
        'outtmpl': outtmpl_format,
        'merge_output_format': merge_fmt,
        'noplaylist': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded', 'ios', 'android', 'web']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id")
            raw_title = info.get("title", "video")
            safe_title = "".join(c for c in raw_title if c.isalnum() or c in (' ', '-', '_')).rstrip()

            matched_files = glob.glob(os.path.join(DOWNLOADS_DIR, f"{video_id}_*"))
            if not matched_files:
                raise HTTPException(status_code=500, detail="Downloaded media file not found on server.")

            downloaded_file = matched_files[0]
            extension = downloaded_file.split(".")[-1]

            # Background cleanup to free disk space
            background_tasks.add_task(cleanup_file, downloaded_file)

            return FileResponse(
                path=downloaded_file,
                filename=f"{safe_title}.{extension}",
                media_type=media_type
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")
