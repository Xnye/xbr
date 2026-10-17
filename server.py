import http.server
import urllib.parse
import hashlib
import os
import asyncio
import sys
import re
import edge_tts

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

PORT = 8080
AUDIO_DIR = os.path.join(os.path.dirname(__file__), 'assets', 'audio')
os.makedirs(AUDIO_DIR, exist_ok=True)

async def generate_tts(text, voice, out_path):
    # rate slightly relaxed (-4%) for educational clarity
    comm = edge_tts.Communicate(text, voice, rate='-4%')
    await comm.save(out_path)

class EducationalHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS and caching headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        # Neural TTS API Endpoint: /api/tts?text=...&voice=...
        if parsed.path == '/api/tts':
            params = urllib.parse.parse_qs(parsed.query)
            text = params.get('text', [''])[0].strip()
            voice = params.get('voice', ['ja-JP-NanamiNeural'])[0].strip()

            if not text:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Missing text parameter')
                return

            # Clean markup tags and all whitespace/punctuation for unified cache hits
            text_clean = text.replace('<ruby>', '').replace('</ruby>', '').replace('<rt>', '').replace('</rt>', '')
            text_clean = re.sub(r'[!！\s　。、.?,?？]', '', text_clean).strip()

            # Check cache
            key = f"{voice}_{text_clean}"
            h = hashlib.md5(key.encode('utf-8')).hexdigest()
            cache_file = os.path.join(AUDIO_DIR, f"{h}.mp3")

            if not os.path.exists(cache_file) or os.path.getsize(cache_file) == 0:
                try:
                    asyncio.run(generate_tts(text_clean, voice, cache_file))
                except Exception as e:
                    print(f"TTS generation error for '{text_clean}': {e}", file=sys.stderr)
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"TTS generation failed: {e}".encode('utf-8'))
                    return

            try:
                with open(cache_file, 'rb') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'public, max-age=604800')
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error reading audio file: {e}".encode('utf-8'))
                return

        # Fallback to standard static file handler
        return super().do_GET()

if __name__ == '__main__':
    # 单线程 TCPServer 会被浏览器的一条 keep-alive 连接卡住，
    # 导致后续静态资源请求一直等待；改用 ThreadingHTTPServer。
    from http.server import ThreadingHTTPServer
    ThreadingHTTPServer.allow_reuse_address = True
    with ThreadingHTTPServer(('', PORT), EducationalHTTPHandler) as httpd:
        print("======================================================")
        print(" Standard Japanese Cognitive Reader Audio Server Ready")
        print(f" URL: http://localhost:{PORT}/")
        print(" Neural Voices: ja-JP-NanamiNeural / ja-JP-KeitaNeural")
        print("======================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止")
