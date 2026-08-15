# -*- coding: utf-8 -*-
"""TTL 内存缓存（线程安全）。"""
import threading
import time


class SnapshotCache:
    """按 TTL 缓存一次抓取结果，force=True 时强制刷新。"""

    def __init__(self, ttl=30, fetcher=None):
        self.ttl = ttl
        self.fetcher = fetcher
        self.lock = threading.Lock()
        self.ts = 0
        self.data = None

    def get(self, force=False):
        now = time.time()
        with self.lock:
            if force or self.data is None or (now - self.ts) > self.ttl:
                self.data = self.fetcher()
                self.ts = time.time()
            return self.data
