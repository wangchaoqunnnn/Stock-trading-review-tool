# -*- coding: utf-8 -*-
"""A股每日复盘本地服务：实时抓取东方财富数据，前端每30秒自动刷新。

运行: python server.py [port]

历史演进：早期版本为单文件实现（约 1200 行），现已按职责拆分到
stockreview 包（见 stockreview/__init__.py 说明）；本文件仅保留
HTTP 路由、缓存实例与启动逻辑，对外 API 与页面路径保持不变。
"""
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from stockreview.cache import SnapshotCache
from stockreview.config import DEFAULT_PORT, STATIC_DIR
from stockreview.pullback import fetch_pullback_scan
from stockreview.realtime import fetch_realtime
from stockreview.snapshot import fetch_snapshot
from stockreview.volprice import fetch_volume_price_scan

sys.stdout.reconfigure(encoding="utf-8")

# 各数据快照缓存（TTL 与历史版本一致）
CACHE = SnapshotCache(ttl=30, fetcher=fetch_snapshot)
REALTIME_CACHE = SnapshotCache(ttl=30, fetcher=fetch_realtime)
VOLPRICE_CACHE = SnapshotCache(ttl=120, fetcher=fetch_volume_price_scan)
PULLBACK_CACHE = SnapshotCache(ttl=120, fetcher=fetch_pullback_scan)

# 静态资源 Content-Type 映射
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def _resolve_static(relpath):
    """把 /xxx 形式的相对路径安全地解析到 static 目录内，防目录穿越。"""
    base = os.path.realpath(STATIC_DIR)
    full = os.path.realpath(os.path.join(base, relpath.lstrip("/")))
    if full.startswith(base + os.sep) and os.path.isfile(full):
        return full
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/api/snapshot":
            self._send_json(CACHE.get())
        elif path == "/api/version":
            self._send_json({"version": 2, "rt": True})
        elif path == "/api/refresh":
            self._send_json(CACHE.get(force=True))
        elif path == "/api/realtime":
            self._send_json(REALTIME_CACHE.get())
        elif path == "/api/realtime_refresh":
            self._send_json(REALTIME_CACHE.get(force=True))
        elif path == "/api/volprice":
            self._send_json(VOLPRICE_CACHE.get())
        elif path == "/api/volprice_refresh":
            self._send_json(VOLPRICE_CACHE.get(force=True))
        elif path == "/api/pullback":
            self._send_json(PULLBACK_CACHE.get())
        elif path == "/api/pullback_refresh":
            self._send_json(PULLBACK_CACHE.get(force=True))
        elif path == "/" or path == "/index.html":
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        else:
            # 其余静态资源（/js/* 前端模块、/style.css 等）
            filepath = _resolve_static(path)
            if filepath is not None:
                ext = os.path.splitext(filepath)[1].lower()
                self._send_file(filepath, CONTENT_TYPES.get(ext, "application/octet-stream"))
            else:
                self.send_error(404)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"A股每日复盘服务已启动: http://127.0.0.1:{port}")
    print("首次数据抓取需要几秒，之后每30秒自动刷新。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
