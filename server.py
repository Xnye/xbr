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

# Edge 神经语音的语速下限实测为 -50%（再低不会更慢，只是重复同一段音频），
# 上限远高于 100%。超出范围的请求钳到这里，避免生成一堆一模一样的缓存文件。
RATE_MIN = -50
RATE_MAX = 100


def clamp_rate(value):
    """把前端传的百分比语速钳到 Edge 实际支持的区间；非法值回到 -4%。"""
    try:
        r = int(round(float(value)))
    except (TypeError, ValueError):
        return -4
    return max(RATE_MIN, min(RATE_MAX, r))


async def generate_tts(text, voice, out_path, rate=-4):
    # 语速交给神经语音合成（原生放慢/加快，音高与频谱都保得住）。
    # 前端再叠 playbackRate 只会把频谱涂糊：实测 0.5x 时谱质心从 1619Hz
    # 掉到 1240Hz，声音发闷。所以慢速必须在这里做。
    #
    # SSML 的 rate 必须带符号：'+50%' 合法，裸的 '50%' 会被服务端拒绝
    # （Invalid rate '50%'），负号本来就有，这里补上正号。
    r = clamp_rate(rate)
    spec = ('+%d%%' % r) if r >= 0 else ('%d%%' % r)
    # 微软接口偶发 503（限流/抖动），重试几次比直接把 500 抛给前台好
    last = None
    for attempt in range(3):
        try:
            await edge_tts.Communicate(text, voice, rate=spec).save(out_path)
            return
        except Exception as e:      # noqa: BLE001 - 统一重试，失败再上抛
            last = e
            await asyncio.sleep(0.6 * (attempt + 1))
    raise last

class EducationalHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS and caching headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        # Health probe: the frontend uses this to know whether neural TTS exists.
        if parsed.path == '/api/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(b'{"tts": true}')
            return

        # Neural TTS API Endpoint: /api/tts?text=...&voice=...
        if parsed.path == '/api/tts':
            params = urllib.parse.parse_qs(parsed.query)
            text = params.get('text', [''])[0].strip()
            voice = params.get('voice', ['ja-JP-NanamiNeural'])[0].strip()
            # 语速百分比，缺省 -4%（与原行为一致，老缓存继续命中）
            rate = clamp_rate(params.get('rate', ['-4'])[0])

            if not text:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Missing text parameter')
                return

            # 只清标记和空白；标点决定 TTS 的句读停顿，不能进清洗规则
            text_clean = re.sub(r'<rt[^>]*>.*?</rt>', '', text, flags=re.I | re.S)
            text_clean = re.sub(r'<[^>]*>', '', text_clean)
            text_clean = re.sub(r'[\s　]+', '', text_clean).strip()
            text_clean = text_clean.lstrip('*').strip()

            if not text_clean:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Empty text after cleaning')
                return

            # 缓存键必须带语速：不同 speed 的音频波形完全不同
            key = f"{voice}_{rate}_{text_clean}"
            h = hashlib.md5(key.encode('utf-8')).hexdigest()
            cache_file = os.path.join(AUDIO_DIR, f"{h}.mp3")

            if not os.path.exists(cache_file) or os.path.getsize(cache_file) == 0:
                try:
                    asyncio.run(generate_tts(text_clean, voice, cache_file, rate))
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
