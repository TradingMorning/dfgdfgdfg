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

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/health')
def health():
    return jsonify({"status": "healthy", "service": "yt-downloader-diagnostics"})

@app.route('/api/diagnose')
def diagnose():
    """Live Server Diagnostic to show EXACTLY why YouTube is blocking the server"""
    report = {}
    
    # 1. Check Server Public IP & Organization (AWS/Datacenter Check)
    try:
        ip_info = requests.get('https://ipapi.co/json/', timeout=5).json()
        report['server_ip'] = ip_info.get('ip')
        report['server_organization'] = ip_info.get('org')
        report['server_country'] = ip_info.get('country_name')
        report['is_datacenter_ip'] = any(
            x in ip_info.get('org', '').lower() 
            for x in ['amazon', 'google', 'digitalocean', 'hetzner', 'datacenter', 'oracle', 'microsoft']
        )
    except Exception as e:
        report['server_ip_error'] = str(e)

    # 2. Test YouTube Client Handshakes individually
    test_url = "https://www.youtube.com/watch?v=re0WlNMOfFU"
    client_tests = {}

    test_clients = ['web_embedded', 'android_vr', 'mweb', 'android', 'web']
    for client_name in test_clients:
        try:
            ydl_opts = {
                'extractor_args': {'youtube': {'player_client': [client_name]}},
                'quiet': True,
                'no_warnings': True,
                'skip_download': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(test_url, download=False)
                fmts = len(info.get('formats', []))
                client_tests[client_name] = f"SUCCESS ({fmts} formats extracted)"
        except Exception as err:
            client_tests[client_name] = f"FAILED: {str(err)}"

    report['client_test_results'] = client_tests

    # 3. Root Cause Explanation
    report['why_this_happens'] = (
        "YouTube firewall blocks AWS/Datacenter IPs from downloading videos without authentication. "
        "When running on local PC it works because of residential ISP (Jio/Airtel/Wi-Fi), but Render runs on AWS datacenters."
    )

    return jsonify(report)

@app.route('/api/extract', methods=['POST'])
def extract():
    data = request.get_json() or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({"success": False, "error": "Please enter a valid YouTube URL."}), 400

    # Auto-try clients in order of best datacenter bypass
    clients_to_try = [
        ['web_embedded', 'android_vr', 'mweb'],
        ['android_vr'],
        ['web_embedded'],
        ['android', 'ios']
    ]

    last_error = ""

    for client_combo in clients_to_try:
        ydl_opts = {
            'extractor_args': {
                'youtube': {
                    'player_client': client_combo
                }
            },
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    continue

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

                    if ext == 'mhtml' or (format_id and str(format_id).startswith('sb')) or not direct_url:
                        continue

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

                if video_formats or audio_formats:
                    return jsonify({
                        'success': True,
                        'video_id': info.get('id'),
                        'title': info.get('title'),
                        'uploader': info.get('uploader'),
                        'thumbnail': info.get('thumbnail'),
                        'duration': format_duration(info.get('duration')),
                        'video_formats': video_formats,
                        'audio_formats': audio_formats,
                        'used_client': client_combo
                    })

        except Exception as e:
            last_error = str(e)
            continue

    return jsonify({
        "success": False,
        "error": f"YouTube Challenge: {last_error}",
        "diagnostic_url": "/api/diagnose"
    }), 500

@app.route('/api/download')
def direct_download():
    video_id = request.args.get('id', '').strip()
    format_id = request.args.get('format_id', '').strip()
    media_type = request.args.get('type', 'video')

    if not video_id:
        return "Missing video ID", 400

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'extractor_args': {
            'youtube': {
                'player_client': ['web_embedded', 'android_vr', 'mweb']
            }
        },
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }

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
