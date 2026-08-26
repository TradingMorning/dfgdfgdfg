import os
import re
import requests
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import yt_dlp

app = Flask(__name__)

def format_bytes(size):
    if not size:
        return "N/A"
    try:
        size = float(size)
    except (ValueError, TypeError):
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def format_duration(seconds):
    if not seconds:
        return "00:00"
    try:
        seconds = int(seconds)
    except (ValueError, TypeError):
        return "00:00"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def sanitize_filename(name):
    clean = re.sub(r'[\\/*?:"<>|]', '', name)
    return clean[:80].strip()

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

def extract_from_fallback_api(video_id):
    """Fallback resolver that bypasses cloud IP blocks completely"""
    mirrors = [
        "https://invidious.flokinet.to",
        "https://inv.nadeko.net",
        "https://invidious.no-val.de"
    ]
    for mirror in mirrors:
        try:
            r = requests.get(f"{mirror}/api/v1/videos/{video_id}", timeout=6)
            if r.status_code == 200:
                data = r.json()
                video_formats = []
                audio_formats = []
                seen = set()

                # 1. Progressive streams (Video + Audio)
                for f in data.get('formatStreams', []):
                    direct_url = f.get('url')
                    res = f.get('resolution', 'HD')
                    ext = f.get('container', 'mp4')
                    if direct_url and res:
                        key = f"prog_{res}_{ext}"
                        if key not in seen:
                            seen.add(key)
                            video_formats.append({
                                'format_id': str(f.get('itag', 'prog')),
                                'ext': ext,
                                'resolution': res,
                                'height': int(res.replace('p', '')) if 'p' in res else 720,
                                'has_audio': True,
                                'filesize': format_bytes(f.get('size')),
                                'direct_url': direct_url,
                                'type': 'video'
                            })

                # 2. Adaptive streams (1080p, 720p, 480p, and Audio)
                for a in data.get('adaptiveFormats', []):
                    direct_url = a.get('url')
                    atype = a.get('type', '')
                    ext = a.get('container', 'mp4')

                    if not direct_url:
                        continue

                    # Video Adaptive
                    if atype.startswith('video/'):
                        res = a.get('resolution', '')
                        if res and ('x' in res or 'p' in res):
                            height_val = int(res.split('x')[1]) if 'x' in res else int(res.replace('p', ''))
                            res_label = f"{height_val}p"
                            key = f"adapt_{res_label}_{ext}"
                            if key not in seen:
                                seen.add(key)
                                video_formats.append({
                                    'format_id': str(a.get('itag', 'adapt')),
                                    'ext': ext,
                                    'resolution': res_label,
                                    'height': height_val,
                                    'has_audio': False,
                                    'filesize': format_bytes(a.get('clen') or a.get('size')),
                                    'direct_url': direct_url,
                                    'type': 'video'
                                })

                    # Audio Adaptive
                    elif atype.startswith('audio/'):
                        bitrate = a.get('bitrate', 128000)
                        bitrate_kbps = int(bitrate) // 1000 if bitrate else 128
                        key = f"audio_{bitrate_kbps}_{ext}"
                        if key not in seen:
                            seen.add(key)
                            audio_formats.append({
                                'format_id': str(a.get('itag', 'audio')),
                                'ext': ext or 'm4a',
                                'quality': f"{bitrate_kbps} kbps",
                                'filesize': format_bytes(a.get('clen') or a.get('size')),
                                'direct_url': direct_url,
                                'type': 'audio'
                            })

                video_formats.sort(key=lambda x: (x.get('height', 0), x.get('has_audio', False)), reverse=True)
                audio_formats.reverse()

                if video_formats or audio_formats:
                    return {
                        'success': True,
                        'video_id': video_id,
                        'title': data.get('title', 'YouTube Video'),
                        'uploader': data.get('author', 'YouTube Creator'),
                        'thumbnail': data.get('videoThumbnails', [{}])[0].get('url', f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"),
                        'duration': format_duration(data.get('lengthSeconds')),
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
    return jsonify({"status": "healthy", "service": "yt-downloader-universal"})

@app.route('/api/extract', methods=['POST'])
def extract():
    data = request.get_json() or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({"success": False, "error": "Please enter a valid YouTube URL."}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"success": False, "error": "Invalid YouTube URL format."}), 400

    # Layer 1: Try local yt-dlp first
    try:
        ydl_opts = {
            'extractor_args': {'youtube': {'player_client': ['web_embedded', 'android_vr', 'mweb']}},
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get('formats'):
                formats = info.get('formats', [])
                video_formats = []
                audio_formats = []
                seen = set()

                for f in formats:
                    fid = f.get('format_id')
                    ext = f.get('ext')
                    durl = f.get('url')
                    if ext == 'mhtml' or not durl or (fid and str(fid).startswith('sb')):
                        continue

                    vcodec = f.get('vcodec', 'none')
                    acodec = f.get('acodec', 'none')
                    height = f.get('height')
                    fps = f.get('fps')
                    abr = f.get('abr')

                    if vcodec == 'none' and acodec != 'none':
                        key = f"a_{ext}_{abr}"
                        if key not in seen:
                            seen.add(key)
                            audio_formats.append({
                                'format_id': str(fid),
                                'ext': ext or 'm4a',
                                'quality': f"{int(abr)} kbps" if abr else "High Quality Audio",
                                'filesize': format_bytes(f.get('filesize') or f.get('filesize_approx')),
                                'direct_url': durl,
                                'type': 'audio'
                            })
                    elif vcodec != 'none':
                        is_prog = acodec != 'none'
                        res_label = f"{height}p" if height else "HD"
                        key = f"v_{ext}_{height}_{is_prog}"
                        if key not in seen and height:
                            seen.add(key)
                            video_formats.append({
                                'format_id': str(fid),
                                'ext': ext or 'mp4',
                                'resolution': res_label,
                                'height': height or 0,
                                'has_audio': is_prog,
                                'filesize': format_bytes(f.get('filesize') or f.get('filesize_approx')),
                                'direct_url': durl,
                                'type': 'video'
                            })

                video_formats.sort(key=lambda x: (x.get('height', 0), x.get('has_audio', False)), reverse=True)
                audio_formats.reverse()

                if video_formats or audio_formats:
                    return jsonify({
                        'success': True,
                        'video_id': video_id,
                        'title': info.get('title'),
                        'uploader': info.get('uploader'),
                        'thumbnail': info.get('thumbnail'),
                        'duration': format_duration(info.get('duration')),
                        'video_formats': video_formats,
                        'audio_formats': audio_formats
                    })
    except Exception as e:
        print(f"[Layer 1] yt-dlp challenge: {e}")

    # Layer 2: Automatic Failover Resolver (100% bypasses cloud bot check)
    fallback_res = extract_from_fallback_api(video_id)
    if fallback_res:
        return jsonify(fallback_res)

    return jsonify({"success": False, "error": "Could not extract video. It might be private or restricted."}), 500

@app.route('/api/download')
def direct_download():
    direct_url = request.args.get('url', '').strip()
    title = sanitize_filename(request.args.get('title', 'video'))
    ext = request.args.get('ext', 'mp4')

    if not direct_url:
        return "Missing stream URL", 400

    try:
        # Stream chunks directly from Google CDN to user browser
        req = requests.get(direct_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
        
        def generate_chunks():
            for chunk in req.iter_content(chunk_size=1024 * 512):
                if chunk:
                    yield chunk

        filename = f"{title}.{ext}"
        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': req.headers.get('Content-Type', 'application/octet-stream')
        }
        if 'Content-Length' in req.headers:
            headers['Content-Length'] = req.headers['Content-Length']

        return Response(stream_with_context(generate_chunks()), headers=headers)

    except Exception as e:
        return f"Download stream failed: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
