import sys
import yt_dlp

# Ensure UTF-8 output in Windows terminal for video titles with emojis
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def format_bytes(size):
    if not size:
        return "Unknown size"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def main():
    print("=" * 60)
    print(" 🎬 YouTube Format Extractor & Downloader (Android Engine)")
    print("=" * 60)
    
    url = input("\n👉 Enter YouTube URL: ").strip()
    if not url:
        print("❌ URL cannot be empty!")
        sys.exit(1)

    ydl_opts = {
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        },
        'quiet': True,
        'no_warnings': True,
    }

    print("\n⏳ Fetching formats (Bypassing bot check)...")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                print("❌ Failed to fetch video info.")
                return

            print("\n" + "=" * 60)
            print(f"📺 Title   : {info.get('title')}")
            print(f"👤 Channel : {info.get('uploader')}")
            print(f"⏱  Duration: {info.get('duration')}s")
            print("=" * 60)

            formats = info.get('formats', [])
            selectable_formats = []

            print("\n📋 Available Formats:")
            print(f"{'#':<4} {'Type':<8} {'Resolution/Quality':<20} {'Ext':<6} {'Size':<12} {'Format ID'}")
            print("-" * 65)

            index = 1
            seen = set()

            for f in formats:
                fid = f.get('format_id')
                ext = f.get('ext')
                filesize = f.get('filesize') or f.get('filesize_approx')
                size_str = format_bytes(filesize)
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')
                height = f.get('height')
                abr = f.get('abr')

                if vcodec != 'none':
                    res = f"{height}p" if height else "Video"
                    has_audio = "(+Audio)" if acodec != 'none' else "(Video Only)"
                    key = f"v_{height}_{ext}_{acodec != 'none'}"
                    if key not in seen and height:
                        seen.add(key)
                        selectable_formats.append((fid, f"{res} {has_audio}", ext))
                        print(f"{index:<4} {'Video':<8} {f'{res} {has_audio}':<20} {ext:<6} {size_str:<12} {fid}")
                        index += 1

                elif vcodec == 'none' and acodec != 'none':
                    qual = f"{int(abr)} kbps" if abr else "Audio"
                    key = f"a_{ext}_{abr}"
                    if key not in seen:
                        seen.add(key)
                        selectable_formats.append((fid, f"Audio ({qual})", ext))
                        print(f"{index:<4} {'Audio':<8} {f'Audio ({qual})':<20} {ext:<6} {size_str:<12} {fid}")
                        index += 1

            if not selectable_formats:
                print("❌ No downloadable formats found.")
                return

            print("\n" + "-" * 65)
            choice = input(f"\n👉 Select format number to download (1-{len(selectable_formats)}) or 'q' to quit: ").strip()

            if choice.lower() == 'q':
                print("Exiting.")
                return

            if not choice.isdigit() or not (1 <= int(choice) <= len(selectable_formats)):
                print("❌ Invalid selection.")
                return

            selected = selectable_formats[int(choice) - 1]
            selected_fid = selected[0]
            print(f"\n⬇️  Downloading '{selected[1]}' ({selected[2]})...")

            download_opts = {
                'format': f"{selected_fid}+bestaudio/best" if 'Video Only' in selected[1] else selected_fid,
                'outtmpl': '%(title)s [%(resolution)s].%(ext)s',
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'ios', 'web']
                    }
                }
            }

            with yt_dlp.YoutubeDL(download_opts) as dl:
                dl.download([url])

            print("\n✅ Download completed successfully!")

    except Exception as e:
        print(f"\n❌ Error occurred: {e}")

if __name__ == "__main__":
    main()
