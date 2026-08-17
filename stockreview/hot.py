# -*- coding: utf-8 -*-
"""市场热度模块：同花顺热股榜（A股日榜）。

- 热度排名 TOP50：按榜单排名（order）取前 50。
- 热度上升最快 TOP50：按排名变化（hot_rank_chg，正数=排名上升）降序取前 50。
- 连续3日热度上升：服务端每日保存榜单快照（data/hot_history.json），
  用「今日实时排名 + 历史快照排名」判断连续 3 个交易日排名逐日上升；
  快照不足 2 个交易日时该子项处于数据积累状态。

附带每只股票：涨跌幅、热度值、概念标签、上榜原因等。
"""
import json
import os
import threading
from datetime import datetime, timedelta

from . import net
from .config import ROOT
from .market import fetch_market_context
from .utils import to_num

# 同花顺热股榜接口
HOT_URL = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"
HOT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://www.10jqka.com.cn/",
}

TOP_N = 50
# 连续热度上升天数
RISING_DAYS = 3
# 快照保留天数
SNAPSHOT_KEEP_DAYS = 10
# 快照目录（可被测试替换）
DATA_DIR = os.path.join(ROOT, "data")
SNAPSHOT_FILE = os.path.join(DATA_DIR, "hot_history.json")

_lock = threading.Lock()


def fetch_hot_rank_list(type_="day"):
    """抓取同花顺热股榜并规范化为行列表。"""
    url = f"{HOT_URL}?stock_type=a&type={type_}&list_type=normal"
    data = net.http_get_json(url, headers=HOT_HEADERS)
    lst = ((data.get("data") or {}).get("stock_list")) or []
    out = []
    for x in lst:
        tag = x.get("tag") or {}
        concepts = tag.get("concept_tag") or []
        out.append({
            "code": str(x.get("code") or ""),
            "name": x.get("name"),
            "rank": int(x.get("order") or 0),
            "rate": to_num(x.get("rate")),
            "rank_chg": int(x.get("hot_rank_chg") or 0),
            "pct": to_num(x.get("rise_and_fall")),
            "tags": concepts[:4],
            "popularity_tag": tag.get("popularity_tag") or "",
            "analyse_title": x.get("analyse_title") or "",
        })
    return out


# ---------- 每日快照（用于连续3日热度上升判定） ----------

def _load_history():
    try:
        with open(SNAPSHOT_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_snapshot(rows):
    """把当日榜单快照写入历史文件（同一天覆盖，保留最近 N 天）。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with _lock:
            history = _load_history()
            today = datetime.now().strftime("%Y-%m-%d")
            history[today] = {r["code"]: {"order": r["rank"], "chg": r["rank_chg"]} for r in rows}
            # 只保留最近 N 天
            keys = sorted(history.keys())
            for k in keys[:-SNAPSHOT_KEEP_DAYS]:
                history.pop(k, None)
            with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _compute_rising3(rows, history, today):
    """判定连续 3 个交易日排名逐日上升（order 越小排名越前）。"""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    before = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    hist_y = history.get(yesterday) or {}
    hist_b = history.get(before) or {}
    have_yesterday = bool(hist_y)

    out = []
    for r in rows:
        code = r["code"]
        r0 = r["rank"]
        # 昨日排名：优先真实快照，否则用今日 chg 反推
        if code in hist_y:
            r1 = hist_y[code]["order"]
        else:
            r1 = r0 + r["rank_chg"]
        # 前日排名：优先真实快照，否则用昨日快照的 chg 反推
        if code in hist_b:
            r2 = hist_b[code]["order"]
        elif code in hist_y and hist_y[code].get("chg") is not None:
            r2 = r1 + int(hist_y[code]["chg"])
        else:
            r2 = None
        if r2 is None:
            continue
        if r0 < r1 < r2:
            out.append(r)
    out.sort(key=lambda x: -x["rank_chg"])
    return out, have_yesterday


def fetch_hot_scan():
    """市场热度扫描主函数：热度排名TOP50 + 热度上升最快TOP50 + 连续3日热度上升。"""
    errors = []
    rows = []
    try:
        rows = fetch_hot_rank_list("day")
    except Exception as exc:
        errors.append(f"热股榜: {type(exc).__name__}: {exc}")

    context = fetch_market_context()
    errors.extend(context["errors"])

    top = sorted(rows, key=lambda x: x["rank"])[:TOP_N]
    rising = sorted(rows, key=lambda x: -x["rank_chg"])[:TOP_N]

    # 连续3日热度上升：保存今日快照 + 结合历史快照判定
    today = datetime.now().strftime("%Y-%m-%d")
    _save_snapshot(rows)
    history = _load_history()
    rising3, have_yesterday = _compute_rising3(rows, history, today)
    days_available = len([d for d in history if d <= today])
    if not have_yesterday:
        rising3 = []

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "indices": context["indices"],
            "breadth": context["breadth"],
            "emotion": context["emotion"],
            "amount_yi": context["amount_yi"],
        },
        "source": "同花顺热股榜（A股日榜）",
        "top": {"count": len(top), "stocks": top},
        "rising": {"count": len(rising), "stocks": rising},
        "rising3": {
            "count": len(rising3),
            "days": RISING_DAYS,
            "days_available": days_available,
            "ready": have_yesterday,
            "stocks": rising3[:TOP_N],
        },
        "errors": errors,
    }
