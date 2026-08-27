import os
import glob
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import yt_dlp

app = FastAPI(title="YouTube Downloader & Info API", version="1.0.0")

DOWNLOADS_DIR = "/tmp/downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def cleanup_file(filepath: str):
    """Temporary file delete karta hai download complete hone ke baad taaki server disk fill na ho."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"[Cleanup] Deleted temporary file: {filepath}")
    except Exception as e:
        print(f"[Cleanup Error] {e}")


@app.get("/")
def root():
    return {
        "status": "online",
        "message": "YouTube Downloader API is running",
        "endpoints": {
            "get_info": "/api/info?url=<youtube_url>",
            "download_video": "/api/download?url=<youtube_url>&quality=<best|1080p|720p>"
        }
    }


@app.get("/api/info")
def get_video_info(url: str = Query(..., description="YouTube video URL")):
    """
    Video details fetch karta hai bina download kiye.
    """
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
            
            # Available qualities extract karna
            formats = info.get('formats', [])
            resolutions = set()
            for f in formats:
                if f.get('height'):
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
                "thumbnail": info.get("thumbnail"),
                "views": info.get("view_count"),
                "available_resolutions": sorted_resolutions
            })

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch video details: {str(e)}")


@app.get("/api/download")
def download_video(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="YouTube video URL"),
    quality: str = Query("best", description="Quality: 'best', '1080p', '720p', etc.")
):
    """
    Video download karta hai aur client ko send karta hai.
    """
    # Quality format selector setup
    if quality == "best":
        format_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    else:
        height = quality.replace("p", "")
        format_str = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height}]+bestaudio/best"

    outtmpl_format = os.path.join(DOWNLOADS_DIR, "%(id)s.%(ext)s")

    ydl_opts = {
        'format': format_str,
        'outtmpl': outtmpl_format,
        'merge_output_format': 'mp4',
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
            video_title = info.get("title", "video").replace("/", "_").replace("\\", "_")

            # Downloaded file find karna
            matched_files = glob.glob(os.path.join(DOWNLOADS_DIR, f"{video_id}.*"))
            if not matched_files:
                raise HTTPException(status_code=500, detail="Downloaded file not found.")

            downloaded_file = matched_files[0]

            # Background task add karna taaki user ko file send hone ke baad file delete ho jaye
            background_tasks.add_task(cleanup_file, downloaded_file)

            return FileResponse(
                path=downloaded_file,
                filename=f"{video_title}.mp4",
                media_type="video/mp4"
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")
