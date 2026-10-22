# -*- coding: utf-8 -*-
"""本地启动：把 server.py 跑起来，让页面用上 Edge 神经语音（七海 / 庆太）。

为什么需要这个脚本：
    页面在加载时会探测 api/health。探测失败就整站退回浏览器自带的
    speechSynthesis —— 也就是 Windows 的 Microsoft Haruka Desktop 这类
    SAPI5 老语音（沙哑、句读机械）。本机同时装了 4 个 OneCore 日语声线，
    但 Chrome / Edge 的 speechSynthesis 只暴露 SAPI 那一套，用不上。
    所以「听起来怪」很多时候不是模型差，而是根本没连上神经语音。

用法：
    python serve.py            # 启动并打开浏览器
    python serve.py --no-open  # 只启动，不开浏览器
"""
import os
import sys
import threading
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8080
URL = 'http://localhost:%d/' % PORT


def check_dependency():
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print('[x] 缺少依赖 edge-tts。')
        print('    pip install -r requirements.txt')
        return False
    return True


def port_in_use():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(('127.0.0.1', PORT)) == 0


def main():
    if not check_dependency():
        return 1

    if port_in_use():
        print('[!] 端口 %d 已被占用。' % PORT)
        print('    如果页面已经在用神经语音，直接打开 %s 即可；' % URL)
        print('    否则先关掉占用的进程再运行本脚本。')
        return 1

    if '--no-open' not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(URL)).start()

    # 复用 server.py 的 handler，避免两份实现漂移
    sys.path.insert(0, HERE)
    import server  # noqa: E402

    from http.server import ThreadingHTTPServer
    ThreadingHTTPServer.allow_reuse_address = True
    with ThreadingHTTPServer(('', PORT), server.EducationalHTTPHandler) as httpd:
        print('=' * 56)
        print(' 日语朗读服务已启动')
        print(' 地址：%s' % URL)
        print(' 声线：ja-JP-NanamiNeural / ja-JP-KeitaNeural')
        print(' 音频缓存在 assets/audio/（按 md5 命名，可重复生成）')
        print('=' * 56)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n服务已停止')
    return 0


if __name__ == '__main__':
    sys.exit(main())
