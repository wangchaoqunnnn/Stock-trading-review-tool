# -*- coding: utf-8 -*-
"""补充：沪铜期货实时、akshare期货接口、今日铜/有色快讯。"""
import inspect
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")


def get_text(url, headers=None, decode="utf-8", timeout=25):
    h = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept": "*/*",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(decode, errors="replace")


def sina_futures(codes):
    url = "https://hq.sinajs.cn/list=" + ",".join(codes)
    return get_text(url, headers={"Referer": "https://finance.sina.com.cn/"}, decode="gbk")


def sina_7x24(today):
    hits = []
    keywords = ["铜", "有色", "铜价", "铜矿", "智利", "秘鲁", "LME", "沪铜", "库存", "升水"]
    for page in range(1, 4):
        url = (
            "https://zhibo.sina.com.cn/api/zhibo/feed?"
            + urllib.parse.urlencode({"page": page, "page_size": 100, "zhibo_id": 152, "tag_id": 0, "dire": "f", "dpc": 1})
        )
        try:
            data = json.loads(get_text(url, headers={"Referer": "https://finance.sina.com.cn/7x24/"}))
            feed = data["result"]["data"]["feed"]["list"]
            for item in feed:
                rich = str(item.get("rich_text", "")) or ""
                tag = item.get("tag") or []
                tag_text = ""
                if isinstance(tag, list):
                    tag_text = " ".join(str(t.get("name", "")) for t in tag if isinstance(t, dict))
                text = rich + " " + tag_text
                if any(k in text for k in keywords):
                    hits.append((item.get("create_time"), rich[:260]))
        except Exception:
            pass
    return hits


def main():
    print("\n=== Sina 沪铜连续/主力 ===")
    print(sina_futures(["nf_CU0", "nf_CU2509", "nf_CU2510"]))

    print("\n=== 今日新浪7x24 铜/有色相关 ===")
    today = datetime.now().strftime("%Y-%m-%d")
    for create_time, text in sina_7x24(today):
        print(f"[{create_time}] {text}")
        print()


if __name__ == "__main__":
    main()
