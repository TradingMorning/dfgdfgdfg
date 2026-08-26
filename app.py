import os
import sys
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

def get_ytdl_options():
    # Bypass Web Botguard on Cloud Servers by targeting Embedded & VR clients
    return {
        'extractor_args': {
            'youtube': {
                'player_client': ['web_embedded', 'android_vr', 'tv_embedded', 'mweb']
            }
        },
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }

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

    ydl_opts = get_ytdl_options()

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({"success": False, "error": "Could not extract video metadata."}), 400

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

                # Skip internal storyboard/thumbnail formats
                if ext == 'mhtml' or (format_id and str(format_id).startswith('sb')):
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

            # Sort video formats by highest resolution first
            video_formats.sort(key=lambda x: (x.get('height', 0), x.get('has_audio', False)), reverse=True)
            audio_formats.reverse()

            return jsonify({
                'success': True,
                'title': info.get('title'),
                'uploader': info.get('uploader'),
                'channel_url': info.get('uploader_url'),
                'thumbnail': info.get('thumbnail'),
                'duration': format_duration(info.get('duration')),
                'views': f"{info.get('view_count', 0):,}" if info.get('view_count') else "N/A",
                'video_formats': video_formats,
                'audio_formats': audio_formats
            })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
