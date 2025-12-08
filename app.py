import os
import glob
import subprocess
import time
from flask import Flask, request, jsonify, send_from_directory
from ytmusicapi import YTMusic
import yt_dlp

app = Flask(__name__)
ytmusic = YTMusic()
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def cleanup_downloads():
    # Remove files older than 10 minutes to save space
    now = time.time()
    for f in glob.glob(os.path.join(DOWNLOAD_FOLDER, "*")):
        if os.stat(f).st_mtime < now - 600:
            try:
                os.remove(f)
            except:
                pass

@app.route('/downloads/<path:filename>')
def serve_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename)

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    try:
        results = ytmusic.search(query, filter='songs')
        mapped_results = []
        for item in results:
            if item['resultType'] == 'song':
                mapped_results.append({
                    'id': item['videoId'],
                    'name': item['title'],
                    'artists': {'primary': [{'name': a['name']} for a in item['artists']]},
                    'album': {'name': item['album']['name'] if 'album' in item and item['album'] else 'Unknown'},
                    'duration': item.get('duration_seconds', 0),
                    'image': item['thumbnails']
                })
        return jsonify(mapped_results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stream', methods=['GET'])
def stream():
    video_id = request.args.get('id')
    if not video_id:
        return jsonify({'error': 'No id provided'}), 400
        
    url = f"https://music.youtube.com/watch?v={video_id}"
    cleanup_downloads()
    
    # 1. Try SpotDL Download (Proxy Mode) - Requested by User
    # This is slower but bypasses "Client IP mismatch" and often Bot checks
    try:
        print(f"Attempting SpotDL download for {video_id}...")
        output_template = os.path.join(DOWNLOAD_FOLDER, f"{video_id}.mp3")
        
        # Check if already exists
        if os.path.exists(output_template):
            print("File already exists in cache.")
            return jsonify({'url': f"{request.host_url}downloads/{video_id}.mp3"})

        # Run SpotDL
        # Using the YouTube URL directly to skip Spotify search
        cmd = ["spotdl", url, "--output", output_template, "--overwrite", "force"]
        
        # Pass cookies if available
        cookie_file = 'cookies.txt'
        if os.path.exists(cookie_file):
            cmd.extend(["--cookie-file", cookie_file])
            
        subprocess.run(cmd, check=True, timeout=120)
        
        if os.path.exists(output_template):
             print("SpotDL download success!")
             return jsonify({'url': f"{request.host_url}downloads/{video_id}.mp3"})
             
    except Exception as e_spot:
        print(f"SpotDL failed: {e_spot}")

    # 2. Fallback: yt-dlp Direct Stream (Fast)
    try:
        # Check for cookies file
        cookie_file = 'cookies.txt'
        if not os.path.exists(cookie_file):
             cookie_file = os.path.join(os.getcwd(), 'cookies.txt')

        has_cookies = os.path.exists(cookie_file)
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'verbose': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['web']
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        }
        
        if has_cookies:
            # AUTO-SANITIZE
            try:
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                if '\r\n' in content:
                    content = content.replace('\r\n', '\n')
                    with open(cookie_file, 'w', encoding='utf-8') as f:
                        f.write(content)
            except: pass
            
            ydl_opts['cookiefile'] = cookie_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({'url': info['url']})
            
    except Exception as e:
        # 3. Fallback: Pytubefix
        try:
             from pytubefix import YouTube as PyTube
             yt = PyTube(url, client='ANDROID', use_po_token=True)
             stream = yt.streams.get_audio_only()
             if stream:
                 return jsonify({'url': stream.url})
        except:
             pass
             
        return jsonify({'error': str(e), 'spotdl_error': str(locals().get('e_spot', ''))}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
