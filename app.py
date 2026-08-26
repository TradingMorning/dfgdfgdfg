import os
import re
import requests
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
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

def sanitize_filename(name):
    clean = re.sub(r'[\\/*?:"<>|]', '', name)
    return clean[:80].strip()

def get_ytdl_options():
    return {
        'extractor_args': {
            'youtube': {
                'player_client': ['web_embedded', 'android_vr', 'mweb', 'web']
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
    return jsonify({"status": "healthy", "service": "yt-downloader-pro"})

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

                # Skip storyboard images
                if ext == 'mhtml' or (format_id and str(format_id).startswith('sb')) or not direct_url:
                    continue

                # Audio Only Streams
                if vcodec == 'none' and acodec != 'none':
                    key = f"audio_{ext}_{abr}"
                    if key not in seen_formats:
                        seen_formats.add(key)
                        audio_formats.append({
                            'format_id': format_id,
                            'ext': ext or 'm4a',
                            'quality': f"{int(abr)} kbps" if abr else "High Quality Audio",
                            'filesize': filesize_str,
                            'type': 'audio'
                        })

                # Video Streams
                elif vcodec != 'none':
                    is_progressive = acodec != 'none'
                    res_label = f"{height}p" if height else "HD"
                    if fps and fps > 30:
                        res_label += f"{int(fps)}"

                    key = f"video_{ext}_{height}_{is_progressive}"
                    if key not in seen_formats and height:
                        seen_formats.add(key)
                        video_formats.append({
                            'format_id': format_id,
                            'ext': ext or 'mp4',
                            'resolution': res_label,
                            'height': height or 0,
                            'has_audio': is_progressive,
                            'filesize': filesize_str,
                            'type': 'video'
                        })

            video_formats.sort(key=lambda x: (x.get('height', 0), x.get('has_audio', False)), reverse=True)
            audio_formats.reverse()

            return jsonify({
                'success': True,
                'video_id': info.get('id'),
                'title': info.get('title'),
                'uploader': info.get('uploader'),
                'thumbnail': info.get('thumbnail'),
                'duration': format_duration(info.get('duration')),
                'video_formats': video_formats,
                'audio_formats': audio_formats
            })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/download')
def direct_download():
    video_id = request.args.get('id', '').strip()
    format_id = request.args.get('format_id', '').strip()
    media_type = request.args.get('type', 'video')

    if not video_id:
        return "Missing video ID", 400

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = get_ytdl_options()

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = sanitize_filename(info.get('title', 'youtube_video'))
            formats = info.get('formats', [])

            target_stream = None

            if format_id:
                for f in formats:
                    if str(f.get('format_id')) == str(format_id) and f.get('url'):
                        target_stream = f
                        break

            if not target_stream:
                if media_type == 'audio':
                    audio_list = [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and f.get('url')]
                    if audio_list:
                        target_stream = audio_list[-1]
                else:
                    video_list = [f for f in formats if f.get('vcodec') != 'none' and f.get('url')]
                    if video_list:
                        target_stream = video_list[-1]

            if not target_stream or not target_stream.get('url'):
                return "Direct stream not found. Please try another quality.", 404

            stream_url = target_stream['url']
            ext = target_stream.get('ext', 'mp4')
            filename = f"{title}.{ext}"

            # Stream direct binary chunks from Google CDN to user browser
            # Zero redirects, zero ads, instant native file download
            req = requests.get(stream_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            
            def generate_chunks():
                for chunk in req.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        yield chunk

            headers = {
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': req.headers.get('Content-Type', 'application/octet-stream')
            }
            if 'Content-Length' in req.headers:
                headers['Content-Length'] = req.headers['Content-Length']

            return Response(stream_with_context(generate_chunks()), headers=headers)

    except Exception as e:
        return f"Download failed: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
