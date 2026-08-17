# -*- coding: utf-8 -*-
"""东方财富公开行情接口的 HTTP 请求封装（含重试与分页）。"""
import json
import time
import urllib.parse
import urllib.request

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


def fetch_paged(fs, fields, fid="f3", po=1, limit=600):
    """按页拉取 clist 数据直到取满 limit 或翻完。"""
    rows = []
    pn = 1
    while True:
        url = clist_url(fs, fields, fid=fid, po=po, pn=pn, pz=100)
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
        total = int(data["total"])
        diff = data.get("diff") or []
        rows.extend(diff)
        if len(rows) >= min(total, limit) or not diff:
            break
        pn += 1
        time.sleep(0.05)
    return rows
