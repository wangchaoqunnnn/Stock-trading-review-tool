# -*- coding: utf-8 -*-
"""实时板块变动：领涨领跌板块 / 5分钟板块涨速榜 / 异动板块时间线 / 大盘涨跌归因。

数据源（均为实时行情）：
- 东财板块行情（行业+概念）：当前涨跌幅、主力资金、领涨龙头、成交额。
- 东财全市场个股 clist f22（5分钟涨速）：按个股行业(f100)聚合 → 板块 5 分钟涨速与异动。
- 东财两市成交额：板块权重 = 板块成交额 / 两市成交额。

归因口径：板块贡献度 = 板块涨跌幅 × 板块成交额占两市比重（成交额加权近似）。
异动时间线：模块级缓冲保存最近检测到的异动板块（带时间戳），每次刷新追加。
"""
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em, net
from .config import ALL_A_FS
from .utils import to_num

RISK_TEXT = "本文为行情监控参考，不构成任何投资建议。市场有风险，投资需谨慎。"

# 异动时间线缓冲（进程内共享，最近 50 条）
_TIMELINE = []

# 个股涨速榜抓取数量
SPEED_TOP_N = 300
SURGE_SPEED = 1.0      # 板块异动阈值：成分股 5 分钟涨速 ≥1%
SURGE_MIN_COUNT = 2    # 板块内异动股数下限（过滤噪声）


def _stocks_by_speed():
    """全市场个股按 5 分钟涨速（f22）取涨/跌两个方向的榜。"""
    fields = "f2,f3,f6,f12,f14,f22,f100"
    out = []
    for po in (1, 0):
        try:
            rows = net.fetch_paged(ALL_A_FS, fields, fid="f22", po=po, limit=SPEED_TOP_N)
            out.extend(rows)
        except Exception:
            continue
    return out


def _aggregate_speed(rows):
    """按个股行业(f100)聚合涨速：返回 {板块: {up_count, down_count, speeds, pct_sum, amount}}。"""
    groups = defaultdict(lambda: {"up": 0, "down": 0, "speeds": [], "pcts": [], "amount": 0.0})
    for r in rows:
        ind = r.get("f100")
        if not ind or ind == "-":
            continue
        sp = to_num(r.get("f22"))
        if sp != sp or sp == 0:
            continue
        g = groups[ind]
        g["speeds"].append(sp)
        g["pcts"].append(to_num(r.get("f3")))
        if sp > 0:
            g["up"] += 1
        else:
            g["down"] += 1
        amt = to_num(r.get("f6"))
        if amt == amt:
            g["amount"] += amt
    return groups


def _speed_boards(groups, n=5):
    """按聚合结果算板块 5 分钟涨速榜：上涨/下跌各前 n。"""
    up_list, down_list = [], []
    for name, g in groups.items():
        avg = sum(g["speeds"]) / len(g["speeds"])
        item = {
            "name": name,
            "speed": round(avg, 2),
            "up_stocks": g["up"], "down_stocks": g["down"],
            "leader_pct": round(sum(g["pcts"]) / len(g["pcts"]), 2),
            "amount_yi": round(g["amount"] / 100000000, 2),
        }
        if avg >= 0.1 and g["up"] >= SURGE_MIN_COUNT:
            up_list.append(item)
        elif avg <= -0.1 and g["down"] >= SURGE_MIN_COUNT:
            down_list.append(item)
    up_list.sort(key=lambda x: -x["speed"])
    down_list.sort(key=lambda x: x["speed"])
    return up_list[:n], down_list[:n]


def _surge_boards(groups, as_of):
    """当前异动板块：成分股涨速超阈值的板块（方向+幅度+异动股数）。"""
    surges = []
    for name, g in groups.items():
        hot = [s for s in g["speeds"] if s >= SURGE_SPEED]
        cold = [s for s in g["speeds"] if s <= -SURGE_SPEED]
        if len(hot) >= SURGE_MIN_COUNT and len(hot) > len(cold):
            surges.append({"name": name, "direction": "up", "speed": round(sum(hot) / len(hot), 2),
                           "count": len(hot), "time": as_of})
        elif len(cold) >= SURGE_MIN_COUNT and len(cold) > len(hot):
            surges.append({"name": name, "direction": "down", "speed": round(sum(cold) / len(cold), 2),
                           "count": len(cold), "time": as_of})
    surges.sort(key=lambda x: -abs(x["speed"]))
    return surges[:6]


def _attribution(industry, total_amount, indices):
    """大盘涨跌归因：板块贡献度 = 涨跌幅 × 成交额权重。"""
    if not industry or not total_amount:
        return None
    rows = []
    for b in industry:
        pct = to_num(b.get("pct"))
        amt_yi = to_num(b.get("amount_yi"))  # 板块成交额（亿）
        if pct != pct or amt_yi != amt_yi or amt_yi <= 0:
            continue
        weight = amt_yi / total_amount
        contrib = pct * weight
        rows.append({"name": b.get("name"), "pct": round(pct, 2),
                     "weight": round(weight * 100, 2), "contrib": round(contrib, 3)})
    rows.sort(key=lambda x: -x["contrib"])
    up = rows[:6]
    down = rows[-6:]
    d = {i.get("name"): i.get("pct") for i in indices}
    sh = d.get("上证指数")
    index_name = "上证指数"
    idx_pct = sh if sh is not None else (d.get("深证成指"))
    if sh is None and idx_pct is None:
        idx_pct = 0.0
    up_sum = round(sum(r["contrib"] for r in up if r["contrib"] > 0), 2)
    down_sum = round(sum(r["contrib"] for r in down if r["contrib"] < 0), 2)
    up_txt = "、".join(f"{r['name']}(+{r['contrib']:.2f}%)" for r in up if r["contrib"] > 0) or "无"
    down_txt = "、".join(f"{r['name']}({r['contrib']:.2f}%)" for r in down if r["contrib"] < 0) or "无"
    direction = "上涨" if (idx_pct or 0) > 0 else "下跌" if (idx_pct or 0) < 0 else "平盘"
    summary = (f"{index_name} {direction} {(idx_pct or 0):+.2f}%（成交额加权归因）："
               f"拉动板块贡献 {up_sum:+.2f}%【{up_txt}】；"
               f"拖累板块贡献 {down_sum:+.2f}%【{down_txt}】。")
    return {"index": index_name, "pct": idx_pct, "up": up, "down": down, "summary": summary}


def _leaders(industry, concept):
    """当前领涨/领跌板块（行业+概念合并，按涨跌幅）。"""
    merged = []
    for b in industry:
        merged.append({**b, "type": "行业"})
    for b in concept:
        merged.append({**b, "type": "概念"})
    merged = [b for b in merged if b.get("pct") == b.get("pct")]
    merged.sort(key=lambda x: -x["pct"])
    top = merged[:10]
    bottom = merged[-10:][::-1]
    return top, bottom


def fetch_sector_momentum(date=None):
    """实时板块变动主函数。date 忽略（板块行情为实时口径）。"""
    errors = []
    if date:
        errors.append("板块变动为盘中实时口径，不支持历史回放（date 参数已忽略）")

    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=5) as ex:
        f_ind = ex.submit(safe, "industry", em.fetch_industry_boards)
        f_con = ex.submit(safe, "concept", em.fetch_concept_boards)
        f_speed = ex.submit(safe, "speed", _stocks_by_speed)
        f_amount = ex.submit(safe, "amount", em.fetch_market_amount)
        f_idx = ex.submit(safe, "indices", em.fetch_indices)
        r_ind = f_ind.result()[1]
        r_con = f_con.result()[1]
        r_speed = f_speed.result()[1]
        r_amount = f_amount.result()[1]
        r_idx = f_idx.result()[1]

    for r in (r_ind, r_con, r_speed, r_amount, r_idx):
        if isinstance(r, dict) and "error" in r:
            errors.append(r.get("error"))

    industry = r_ind if not isinstance(r_ind, dict) else []
    concept = r_con if not isinstance(r_con, dict) else []
    speed_rows = r_speed if not isinstance(r_speed, dict) else []
    total_amount = r_amount if not isinstance(r_amount, dict) else None
    indices = r_idx if not isinstance(r_idx, dict) else []

    top, bottom = _leaders(industry, concept)
    groups = _aggregate_speed(speed_rows)
    speed_up, speed_down = _speed_boards(groups, 5)
    as_of = datetime.now().strftime("%H:%M:%S")
    surges = _surge_boards(groups, as_of)

    # 时间线：当前异动 append 到缓冲（去重：同板块 10 分钟内不重复记录）
    now_ts = time.time()
    for s in surges:
        recent = [t for t in _TIMELINE if t["name"] == s["name"] and now_ts - t["ts"] < 600]
        if not recent:
            _TIMELINE.append({**s, "ts": now_ts})
    while len(_TIMELINE) > 50:
        _TIMELINE.pop(0)
    timeline = [{"time": t["time"], "name": t["name"], "direction": t["direction"],
                 "speed": t["speed"], "count": t["count"]} for t in _TIMELINE[-20:]]

    attribution = _attribution(industry, total_amount, indices)

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "leaders": {
            "top": [{k: b.get(k) for k in ("name", "type", "pct", "flow_yi", "leader", "leader_pct", "amount_yi")} for b in top],
            "bottom": [{k: b.get(k) for k in ("name", "type", "pct", "flow_yi", "leader", "leader_pct", "amount_yi")} for b in bottom],
        },
        "speed5": {"up": speed_up, "down": speed_down},
        "surge": surges,
        "timeline": timeline,
        "attribution": attribution,
        "risk": RISK_TEXT,
        "errors": errors,
    }
