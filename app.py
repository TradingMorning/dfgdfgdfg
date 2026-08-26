import os
import re
import requests
from flask import Flask, render_template, request, jsonify
import yt_dlp

app = Flask(__name__)

def format_bytes(size):
    if not size:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def format_duration(seconds):
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def extract_video_id(url):
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/|v\/|shorts\/)([0-9A-Za-z_-]{11})',
        r'youtu\.be\/([0-9A-Za-z_-]{11})'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def extract_with_ytdlp(url):
    ydl_opts = {
        'extractor_args': {
            'youtube': {
                'player_client': ['web_embedded', 'android_vr', 'android_creator']
            }
        },
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            return None

        formats = info.get('formats', [])
        video_formats = []
        audio_formats = []
        seen_formats = set()

        for f in formats:
            format_id = f.get('format_id')
            ext = f.get('ext')
            direct_url = f.get('url')
            filesize = f.get('filesize') or f.get('filesize_approx')
            filesize_str = format_bytes(filesize)
            
            vcodec = f.get('vcodec', 'none')
            acodec = f.get('acodec', 'none')
            height = f.get('height')
            fps = f.get('fps')
            abr = f.get('abr')

            # Skip internal storyboard/thumbnails
            if ext == 'mhtml' or (format_id and str(format_id).startswith('sb')) or not direct_url:
                continue

            # Audio Streams
            if vcodec == 'none' and acodec != 'none':
                key = f"audio_{ext}_{abr}"
                if key not in seen_formats:
                    seen_formats.add(key)
                    audio_formats.append({
                        'format_id': format_id,
                        'ext': ext,
                        'quality': f"{int(abr)} kbps" if abr else "Standard Audio",
                        'filesize': filesize_str,
                        'download_url': direct_url,
                        'type': 'audio'
                    })

            # Video Streams
            elif vcodec != 'none':
                is_progressive = acodec != 'none'
                res_label = f"{height}p" if height else f.get('resolution', 'Unknown')
                if fps and fps > 30:
                    res_label += f"{int(fps)}"

                key = f"video_{ext}_{height}_{is_progressive}"
                if key not in seen_formats and height:
                    seen_formats.add(key)
                    video_formats.append({
                        'format_id': format_id,
                        'ext': ext,
                        'resolution': res_label,
                        'height': height or 0,
                        'has_audio': is_progressive,
                        'filesize': filesize_str,
                        'download_url': direct_url,
                        'type': 'video'
                    })

        video_formats.sort(key=lambda x: (x.get('height', 0), x.get('has_audio', False)), reverse=True)
        audio_formats.reverse()

        return {
            'success': True,
            'title': info.get('title'),
            'uploader': info.get('uploader'),
            'channel_url': info.get('uploader_url'),
            'thumbnail': info.get('thumbnail'),
            'duration': format_duration(info.get('duration')),
            'views': f"{info.get('view_count', 0):,}" if info.get('view_count') else "N/A",
            'video_formats': video_formats,
            'audio_formats': audio_formats
        }

def extract_with_invidious_fallback(video_id):
    instances = [
        "https://inv.tux.pizza",
        "https://invidious.nerdvpn.de",
        "https://vid.priv.au",
        "https://invidious.jing.rocks"
    ]
    
    for instance in instances:
        try:
            r = requests.get(f"{instance}/api/v1/videos/{video_id}", timeout=6)
            if r.status_code == 200:
                data = r.json()
                video_formats = []
                audio_formats = []

                for f in data.get('formatStreams', []):
                    video_formats.append({
                        'format_id': f.get('itag'),
                        'ext': f.get('container', 'mp4'),
                        'resolution': f.get('resolution', 'HD'),
                        'height': int(f.get('resolution', '720p').replace('p', '')) if 'p' in f.get('resolution', '') else 720,
                        'has_audio': True,
                        'filesize': format_bytes(f.get('size')),
                        'download_url': f.get('url'),
                        'type': 'video'
                    })

                for a in data.get('adaptiveFormats', []):
                    if a.get('type', '').startswith('audio/'):
                        audio_formats.append({
                            'format_id': a.get('itag'),
                            'ext': a.get('container', 'm4a'),
                            'quality': f"{a.get('bitrate', 128000)//1000} kbps",
                            'filesize': format_bytes(a.get('size')),
                            'download_url': a.get('url'),
                            'type': 'audio'
                        })

                return {
                    'success': True,
                    'title': data.get('title'),
                    'uploader': data.get('author'),
                    'channel_url': f"https://www.youtube.com{data.get('authorUrl', '')}",
                    'thumbnail': data.get('videoThumbnails', [{}])[0].get('url', ''),
                    'duration': format_duration(data.get('lengthSeconds')),
                    'views': f"{data.get('viewCount', 0):,}",
                    'video_formats': video_formats,
                    'audio_formats': audio_formats
                }
        except Exception:
            continue
    return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/health')
def health():
    return jsonify({"status": "healthy", "service": "yt-downloader"})

@app.route('/api/extract', methods=['POST'])
def extract():
    data = request.get_json() or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({"success": False, "error": "Please enter a valid YouTube URL."}), 400

    # Layer 1: Primary extraction via embedded & VR client
    try:
        result = extract_with_ytdlp(url)
        if result and (result['video_formats'] or result['audio_formats']):
            return jsonify(result)
    except Exception as e:
        print(f"[Warning] yt-dlp primary failed: {e}")

    # Layer 2: Automatic Fallback
    video_id = extract_video_id(url)
    if video_id:
        fallback_res = extract_with_invidious_fallback(video_id)
        if fallback_res:
            return jsonify(fallback_res)

    return jsonify({"success": False, "error": "Could not extract stream formats. Video might be restricted or private."}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
    
