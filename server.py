# -*- coding: utf-8 -*-
"""A股每日复盘本地服务：实时抓取东方财富数据，前端每30秒自动刷新。

运行: python server.py [port]

历史演进：早期版本为单文件实现（约 1200 行），现已按职责拆分到
stockreview 包（见 stockreview/__init__.py 说明）；本文件仅保留
HTTP 路由、缓存实例与启动逻辑，对外 API 与页面路径保持不变。
"""
import json
import math
import os
import sys
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from stockreview.cache import SnapshotCache
from stockreview.breakout import fetch_breakout_scan
from stockreview.config import DEFAULT_PORT, STATIC_DIR
from stockreview.emotion_history import fetch_emotion_history
from stockreview.flow3 import fetch_flow3_scan
from stockreview.heatmap import fetch_heatmap_scan
from stockreview.hot import fetch_hot_scan
from stockreview.leaders import fetch_leaders_scan
from stockreview.limit20 import fetch_limit20_scan
from stockreview.pullback import fetch_pullback_scan
from stockreview.pullback_ma import fetch_pullback_ma_scan
from stockreview.realtime import fetch_realtime
from stockreview.snapshot import fetch_snapshot
from stockreview.speedrank import fetch_speedrank_scan
from stockreview.support_valid import fetch_support_valid_scan
from stockreview.trend3 import fetch_trend3_scan
from stockreview.volprice import fetch_volume_price_scan
from stockreview.ztpool import fetch_ztpool_detail

sys.stdout.reconfigure(encoding="utf-8")

# 各数据快照缓存（TTL 与历史版本一致）
CACHE = SnapshotCache(ttl=30, fetcher=fetch_snapshot)
REALTIME_CACHE = SnapshotCache(ttl=30, fetcher=fetch_realtime)
VOLPRICE_CACHE = SnapshotCache(ttl=120, fetcher=fetch_volume_price_scan)
PULLBACK_CACHE = SnapshotCache(ttl=120, fetcher=fetch_pullback_scan)
# 新增策略扫描较慢，使用更长缓存
FLOW3_CACHE = SnapshotCache(ttl=600, fetcher=fetch_flow3_scan)
TREND3_CACHE = SnapshotCache(ttl=600, fetcher=fetch_trend3_scan)
LIMIT20_CACHE = SnapshotCache(ttl=600, fetcher=fetch_limit20_scan)
# 今日涨停面板：盘中实时口径，30s 缓存
ZTPOOL_CACHE = SnapshotCache(ttl=30, fetcher=fetch_ztpool_detail)
# 市场热度：同花顺热股榜日榜，5 分钟缓存
HOT_CACHE = SnapshotCache(ttl=300, fetcher=fetch_hot_scan)
# 突破新高扫描：K线核对较慢，10 分钟缓存
BREAKOUT_CACHE = SnapshotCache(ttl=600, fetcher=fetch_breakout_scan)
# 龙头股 / 热力图：盘中口径，60s 缓存
LEADERS_CACHE = SnapshotCache(ttl=60, fetcher=fetch_leaders_scan)
HEATMAP_CACHE = SnapshotCache(ttl=60, fetcher=fetch_heatmap_scan)
# 情绪周期表：多日历史数据，10 分钟缓存
EMOTION_HISTORY_CACHE = SnapshotCache(ttl=600, fetcher=fetch_emotion_history)
# 涨速榜：盘中实时口径，30s 缓存（配合前端 30s 自动刷新）
SPEEDRANK_CACHE = SnapshotCache(ttl=30, fetcher=fetch_speedrank_scan)
# 回踩支撑：K线核对较慢，10 分钟缓存
PULLBACK_MA_CACHE = SnapshotCache(ttl=600, fetcher=fetch_pullback_ma_scan)
# 支撑位有效：K线核对较慢，10 分钟缓存
SUPPORT_VALID_CACHE = SnapshotCache(ttl=600, fetcher=fetch_support_valid_scan)

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

    @staticmethod
    def _sanitize(obj):
        """把 NaN/Infinity 转为 None——它们不是合法 JSON，浏览器 JSON.parse 会抛错。"""
        if isinstance(obj, float):
            return None if (math.isnan(obj) or math.isinf(obj)) else obj
        if isinstance(obj, dict):
            return {k: Handler._sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [Handler._sanitize(v) for v in obj]
        return obj

    def _send_json(self, obj, status=200):
        body = json.dumps(self._sanitize(obj), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve(self, cache, date, force=False):
        """统一服务入口：date 非空时走历史回放（不缓存）；否则走缓存（force=强制刷新）。"""
        if date:
            try:
                data = cache.fetcher(date)
            except Exception as exc:
                data = {
                    "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "errors": [f"历史回放失败({date}): {type(exc).__name__}: {exc}"],
                }
            self._send_json(data)
        else:
            self._send_json(cache.get(force=force))

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
        # 历史回放日期参数（YYYY-MM-DD）
        query = urllib.parse.parse_qs(parsed.query)
        date = (query.get("date") or [None])[0]
        if path == "/api/snapshot":
            self._serve(CACHE, date)
        elif path == "/api/version":
            self._send_json({"version": 2, "rt": True})
        elif path == "/api/refresh" or path == "/api/snapshot_refresh":
            self._serve(CACHE, date, force=True)
        elif path == "/api/realtime":
            self._serve(REALTIME_CACHE, date)
        elif path == "/api/realtime_refresh":
            self._serve(REALTIME_CACHE, date, force=True)
        elif path == "/api/volprice":
            self._serve(VOLPRICE_CACHE, date)
        elif path == "/api/volprice_refresh":
            self._serve(VOLPRICE_CACHE, date, force=True)
        elif path == "/api/pullback":
            self._serve(PULLBACK_CACHE, date)
        elif path == "/api/pullback_refresh":
            self._serve(PULLBACK_CACHE, date, force=True)
        elif path == "/api/flow3":
            self._serve(FLOW3_CACHE, date)
        elif path == "/api/flow3_refresh":
            self._serve(FLOW3_CACHE, date, force=True)
        elif path == "/api/trend3":
            self._serve(TREND3_CACHE, date)
        elif path == "/api/trend3_refresh":
            self._serve(TREND3_CACHE, date, force=True)
        elif path == "/api/limit20":
            self._serve(LIMIT20_CACHE, date)
        elif path == "/api/limit20_refresh":
            self._serve(LIMIT20_CACHE, date, force=True)
        elif path == "/api/ztpool":
            self._serve(ZTPOOL_CACHE, date)
        elif path == "/api/ztpool_refresh":
            self._serve(ZTPOOL_CACHE, date, force=True)
        elif path == "/api/hot":
            self._serve(HOT_CACHE, date)
        elif path == "/api/hot_refresh":
            self._serve(HOT_CACHE, date, force=True)
        elif path == "/api/breakout":
            self._serve(BREAKOUT_CACHE, date)
        elif path == "/api/breakout_refresh":
            self._serve(BREAKOUT_CACHE, date, force=True)
        elif path == "/api/leaders":
            self._serve(LEADERS_CACHE, date)
        elif path == "/api/leaders_refresh":
            self._serve(LEADERS_CACHE, date, force=True)
        elif path == "/api/heatmap":
            self._serve(HEATMAP_CACHE, date)
        elif path == "/api/heatmap_refresh":
            self._serve(HEATMAP_CACHE, date, force=True)
        elif path == "/api/emotion_history":
            self._serve(EMOTION_HISTORY_CACHE, date)
        elif path == "/api/emotion_history_refresh":
            self._serve(EMOTION_HISTORY_CACHE, date, force=True)
        elif path == "/api/speedrank":
            self._serve(SPEEDRANK_CACHE, date)
        elif path == "/api/speedrank_refresh":
            self._serve(SPEEDRANK_CACHE, date, force=True)
        elif path == "/api/pullback_ma":
            self._serve(PULLBACK_MA_CACHE, date)
        elif path == "/api/pullback_ma_refresh":
            self._serve(PULLBACK_MA_CACHE, date, force=True)
        elif path == "/api/support_valid":
            self._serve(SUPPORT_VALID_CACHE, date)
        elif path == "/api/support_valid_refresh":
            self._serve(SUPPORT_VALID_CACHE, date, force=True)
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
