# -*- coding: utf-8 -*-
"""东方财富公开行情接口的 HTTP 请求封装（含重试与分页）。"""
import json
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import EM_UT, UA

# ---------- 基础数据短 TTL 共享缓存（盘中 15s，实时盘口分区内页面共享，避免重复全市场扫描） ----------
_TTL_CACHE = {}
_TTL_LOCK = threading.Lock()


def ttl_cache(seconds):
    """函数级 TTL 缓存装饰器（线程安全，按 参数 缓存）。"""
    def deco(fn):
        sig = fn.__module__ + "." + fn.__name__

        def wrapper(*args, **kwargs):
            key = (sig, args, tuple(sorted(kwargs.items())))
            now = time.time()
            with _TTL_LOCK:
                hit = _TTL_CACHE.get(key)
                if hit and now - hit[0] < seconds:
                    return hit[1]
                if len(_TTL_CACHE) > 5000:
                    _TTL_CACHE.clear()
            val = fn(*args, **kwargs)
            with _TTL_LOCK:
                _TTL_CACHE[key] = (now, val)
            # 浅拷贝，避免调用方修改污染共享缓存
            if isinstance(val, list):
                return list(val)
            if isinstance(val, dict):
                return dict(val)
            return val

        return wrapper

    return deco


def http_get(url, headers=None, decode="utf-8", timeout=18, tries=3):
    """GET 请求文本，失败自动重试，最后抛出异常。"""
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode(decode, errors="replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(0.8)


def http_get_json(url, headers=None, tries=3, timeout=None):
    """GET 请求并解析 JSON。"""
    return json.loads(http_get(url, headers=headers, tries=tries, timeout=timeout or 18))


def race_fns(fns, prefer=None, wait=0.8):
    """主备数据源并发请求：同时执行多个抓取函数，谁先成功返回用谁。

    - fns: 无参函数列表，各自内部捕获异常，失败返回 None。
    - prefer: 优先源下标（如东财）；该源成功时优先使用其结果（最多等待 wait 秒），
      否则使用第一个成功的备源——体现"东财优先"的同时不阻塞备源结果。
    - 返回第一个成功结果，全部失败返回 None。慢源在后台结束，不阻塞调用方。
    """
    ex = ThreadPoolExecutor(max_workers=len(fns))
    futs = {ex.submit(fn): i for i, fn in enumerate(fns)}
    try:
        first_ok = None
        first_ok_idx = None
        deadline = time.time() + wait
        for f in as_completed(futs):
            i = futs[f]
            try:
                r = f.result()
            except Exception:
                continue
            if r is None:
                continue
            if prefer is not None and i == prefer:
                return r  # 主源成功，直接返回
            if first_ok is None:
                first_ok, first_ok_idx = r, i
                if prefer is None:
                    return r
                # 备源先成功：给主源一个等待窗，超时用备源
                for f2 in as_completed(futs):
                    j = futs[f2]
                    if j == prefer:
                        try:
                            pr = f2.result()
                            if pr is not None:
                                return pr
                        except Exception:
                            pass
                        return first_ok
                    if time.time() > deadline:
                        return first_ok
        if first_ok is not None:
            return first_ok
        return None
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def clist_url(fs, fields, fid="f3", po=1, pn=1, pz=100):
    """构造东方财富 clist 分页接口 URL。"""
    params = {
        "pn": pn, "pz": pz, "po": po, "np": 1, "ut": EM_UT,
        "fltt": 2, "invt": 2, "fid": fid, "fs": fs, "fields": fields,
    }
    return "https://push2delay.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)


@ttl_cache(15)
def fetch_paged(fs, fields, fid="f3", po=1, limit=600, workers=12):
    """按页拉取 clist 数据直到取满 limit 或翻完。

    翻页并行化（IO 密集，线程并发 ≈ 异步提速）：先取第 1 页拿 total，
    剩余页并行抓取，显著降低大 limit（如全市场 6000 只 = 60 页）的耗时。
    """
    def one(pn):
        try:
            d = http_get_json(clist_url(fs, fields, fid=fid, po=po, pn=pn, pz=100),
                              headers={"Referer": "https://quote.eastmoney.com/"})
            return (d.get("data") or {}).get("diff") or []
        except Exception:
            return []

    first = http_get_json(clist_url(fs, fields, fid=fid, po=po, pn=1, pz=100),
                          headers={"Referer": "https://quote.eastmoney.com/"})
    data = first.get("data") or {}
    total = int(data.get("total") or 0)
    rows = list(data.get("diff") or [])
    need = min(total, limit)
    pages = (need + 99) // 100
    if pages <= 1 or len(rows) >= need:
        return rows[:need]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for part in ex.map(one, range(2, pages + 1)):
            rows.extend(part)
    return rows[:need]
