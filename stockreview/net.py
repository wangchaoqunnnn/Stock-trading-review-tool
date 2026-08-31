# -*- coding: utf-8 -*-
"""东方财富公开行情接口的 HTTP 请求封装（含重试与分页）。"""
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .config import EM_UT, UA


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


def http_get_json(url, headers=None, tries=3):
    """GET 请求并解析 JSON。"""
    return json.loads(http_get(url, headers=headers, tries=tries))


def clist_url(fs, fields, fid="f3", po=1, pn=1, pz=100):
    """构造东方财富 clist 分页接口 URL。"""
    params = {
        "pn": pn, "pz": pz, "po": po, "np": 1, "ut": EM_UT,
        "fltt": 2, "invt": 2, "fid": fid, "fs": fs, "fields": fields,
    }
    return "https://push2delay.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)


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
