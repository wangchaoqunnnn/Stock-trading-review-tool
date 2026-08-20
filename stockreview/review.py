# -*- coding: utf-8 -*-
"""复盘总结模块：聚合当日真实行情数据，规则生成专业级大盘复盘内容。

- 数据全部来自本工具已接入的真实行情源（指数/成交额/涨跌分布/涨跌停池/
  板块行情/主力资金/情绪周期），由规则引擎客观推导结论，不编造数据。
- 北向资金：自 2024 年 8 月 19 日起沪深港通不再披露每日净买入额，本模块
  如实标注，并以全市场主力资金（东方财富口径）替代观测。
- 全部文字结论均附带当日可核验的数据支撑；数据不可得时如实标注为
  "暂不可得"，不臆测。
"""
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em
from .analysis import compute_emotion, zt_summary
from .emotion_history import emotion_level, emotion_score, fetch_emotion_history
from .net import http_get_json
from .snapshot import _prev_amount_at
from .utils import to_num

# 复盘要求的五大核心指数（按页面顺序）
INDEX_NAMES = ("上证指数", "深证成指", "创业板指", "科创50", "沪深300")
IDX_SECID = {name: secid for name, secid in em.INDICES}

RISK_TEXT = "本文仅为行情复盘参考，不构成任何投资建议。股市有风险，投资需谨慎。"


# ---------- 指数 ----------

def _pick_indices(indices):
    """按页面顺序取出五大核心指数（缺哪个就少哪个，不补默认值）。"""
    have = {x.get("name"): x for x in indices if x.get("name") in INDEX_NAMES}
    return [have[n] for n in INDEX_NAMES if n in have]


def _index_amounts():
    """五大指数成交额（亿，ulist f6）。失败返回 {}。"""
    try:
        secids = ",".join(IDX_SECID[n] for n in INDEX_NAMES if n in IDX_SECID)
        params = {"fltt": 2, "invt": 2, "fields": "f6,f12,f14", "secids": secids}
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
        return {
            r.get("f14"): round(to_num(r.get("f6")) / 100000000, 2)
            for r in (data.get("data", {}).get("diff") or []) if r.get("f14")
        }
    except Exception:
        return {}


def _indices_history(date):
    """历史回放：五大指数收盘口径由日K重构（open/close/high/low/pct）。"""
    out = []
    ds = date.replace("-", "")
    for name in INDEX_NAMES:
        secid = IDX_SECID.get(name)
        if not secid:
            continue
        try:
            hist = em.fetch_index_kline(secid, limit=6, end_date=date)
            if len(hist) < 2:
                continue
            last = hist[-1]
            prev_close = hist[-2]["close"]
            out.append({
                "name": name, "pre_close": prev_close, "current": last["close"],
                "pct": last.get("pct") or round((last["close"] / prev_close - 1) * 100, 2),
                "open": last.get("open"), "high": last.get("high"), "low": last.get("low"),
                "avg_price": None, "above_avg": None, "vs_avg_pct": None,
            })
        except Exception:
            continue
    return out


# ---------- 分时节奏 ----------

def _rhythm_live():
    """上证指数今日分时节奏：开盘点位、全天振幅、收盘位置、尾盘表现。"""
    try:
        params = {"secid": "1.000001", "ut": em.INDEX_UT, **em._TRENDS_PARAMS}
        url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get?" + urllib.parse.urlencode(params)
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})["data"]
        pre = float(data["preClose"])
        trends = data.get("trends") or []
        if len(trends) < 12:
            return None
        first = trends[0].split(",")
        last = trends[-1].split(",")
        o = float(first[1])
        c = float(last[2])
        hi = max(float(t.split(",")[3]) for t in trends)
        lo = min(float(t.split(",")[4]) for t in trends)
        tail_start = float(trends[-12].split(",")[2]) if len(trends) >= 12 else c
        return {
            "open_pct": round((o / pre - 1) * 100, 2) if pre else 0.0,
            "high_pct": round((hi / pre - 1) * 100, 2) if pre else 0.0,
            "low_pct": round((lo / pre - 1) * 100, 2) if pre else 0.0,
            "tail_pct": round((c / tail_start - 1) * 100, 2) if tail_start else 0.0,
            "position": round((c - lo) / (hi - lo) * 100, 1) if hi > lo else 50.0,
        }
    except Exception:
        return None


def _rhythm_history(hist):
    """历史回放：由上证日K行描述当日节奏（开/收/振幅）。"""
    if len(hist) < 2:
        return None
    last, prev = hist[-1], hist[-2]
    pre = prev["close"]
    open_pct = round((last["open"] / pre - 1) * 100, 2) if pre else 0.0
    high_pct = round((last["high"] / pre - 1) * 100, 2) if pre else 0.0
    low_pct = round((last["low"] / pre - 1) * 100, 2) if pre else 0.0
    body = "收阳" if last["close"] >= last["open"] else "收阴"
    return {
        "open_pct": open_pct, "high_pct": high_pct, "low_pct": low_pct,
        "tail_pct": None, "position": None, "body": body,
    }


def _rhythm_text(r):
    if not r:
        return "分时节奏数据暂不可得（数据源超时），以上为收盘口径。"
    open_desc = "高开" if r["open_pct"] >= 0.15 else ("低开" if r["open_pct"] <= -0.15 else "平开")
    amp = round(r["high_pct"] - r["low_pct"], 2)
    if r.get("position") is not None:
        if r["position"] >= 70:
            pos_desc = "收于日内高位区"
        elif r["position"] <= 30:
            pos_desc = "收于日内低位区"
        else:
            pos_desc = "收于日内中位区"
        tail_desc = (
            "尾盘小幅拉升" if r["tail_pct"] >= 0.15
            else "尾盘小幅回落" if r["tail_pct"] <= -0.15
            else "尾盘平稳"
        )
        return (f"上证指数{open_desc}{abs(r['open_pct']):.2f}%，全天振幅约{amp:.2f}%"
                f"（{r['low_pct']:+.2f}%~{r['high_pct']:+.2f}%），{pos_desc}，{tail_desc}。")
    body = r.get("body", "收平")
    return (f"上证指数{open_desc}{abs(r['open_pct']):.2f}%，全天振幅约{amp:.2f}%，{body}。"
            "（历史回放：无分时数据，收盘口径）")


# ---------- 市场情绪 ----------

def _breadth_block(breadth):
    up = to_num(breadth.get("up") or 0)
    down = to_num(breadth.get("down") or 0)
    flat = to_num(breadth.get("flat") or 0)
    tot = up + down + flat
    up_pct = round(up / tot * 100, 1) if tot else 0.0
    down_pct = round(down / tot * 100, 1) if tot else 0.0
    flat_pct = round(flat / tot * 100, 1) if tot else 0.0
    if tot == 0:
        verdict = "涨跌家数数据暂不可得（历史回放/数据源超时）。"
    else:
        ratio = round(up / down, 2) if down else 99.0
        if ratio >= 2:
            mood = "普涨格局"
        elif ratio >= 1.2:
            mood = "涨多跌少"
        elif ratio <= 0.6:
            mood = "跌多涨少，普跌承压"
        elif ratio <= 0.8:
            mood = "偏弱震荡"
        else:
            mood = "多空均衡"
        verdict = (f"上涨 {up} 家（{up_pct}%）、下跌 {down} 家（{down_pct}%）、"
                   f"平盘 {flat} 家（{flat_pct}%）；涨跌比 {ratio}，{mood}。")
    return {
        "up": up, "down": down, "flat": flat,
        "up_pct": up_pct, "down_pct": down_pct, "flat_pct": flat_pct,
        "verdict": verdict,
    }


def _rating(zt, zb_rate, dt, max_lb, up, down):
    """赚钱效应综合评级：极寒 / 偏冷 / 温和 / 火热。"""
    score = 0
    parts = []
    if zt >= 100:
        score += 2
        parts.append(f"涨停 {zt} 家（≥100）")
    elif zt >= 60:
        score += 1
        parts.append(f"涨停 {zt} 家（≥60）")
    else:
        parts.append(f"涨停仅 {zt} 家")
    if zb_rate <= 15:
        score += 1
        parts.append(f"炸板率 {zb_rate}% 很低")
    elif zb_rate <= 25:
        parts.append(f"炸板率 {zb_rate}% 可控")
    elif zb_rate >= 40:
        score -= 2
        parts.append(f"炸板率 {zb_rate}% 偏高")
    else:
        score -= 1
        parts.append(f"炸板率 {zb_rate}% 偏高")
    if up and down:
        r = up / down
        if r >= 2:
            score += 1
            parts.append(f"涨跌比 {r:.2f} 普涨")
        elif r <= 0.6:
            score -= 1
            parts.append(f"涨跌比 {r:.2f} 普跌")
    if max_lb >= 7:
        score += 1
        parts.append(f"最高 {max_lb} 板")
    elif max_lb <= 2:
        score -= 1
        parts.append(f"最高仅 {max_lb} 板")
    if dt >= 15:
        score -= 1
        parts.append(f"跌停 {dt} 家偏多")
    rating = "火热" if score >= 4 else "温和" if score >= 1 else "偏冷" if score >= -2 else "极寒"
    return rating, f"{'；'.join(parts)}。综合评级：{rating}（赚钱效应{'强' if rating == '火热' else '较好' if rating == '温和' else '弱' if rating == '偏冷' else '极弱'}）。"


def _limit_block(zt, zb, dt, breadth):
    zt_tc = zt["tc"] or len(zt["pool"])
    zb_tc = zb["tc"] or 0
    dt_tc = dt["tc"] or 0
    zb_rate = round(zb_tc / (zt_tc + zb_tc) * 100, 1) if (zt_tc + zb_tc) else 0.0
    pool = zt.get("pool") or []
    max_lb = max((int(x.get("lbc") or 0) for x in pool), default=0)
    ladder = Counter(int(x.get("lbc") or 0) for x in pool)
    rating, reason = _rating(
        zt_tc, zb_rate, dt_tc, max_lb,
        to_num(breadth.get("up") or 0), to_num(breadth.get("down") or 0),
    )
    return {
        "zt": zt_tc, "zb": zb_tc, "dt": dt_tc, "zb_rate": zb_rate,
        "max_lb": max_lb,
        "ladder": [{"board": k, "count": v} for k, v in sorted(ladder.items())],
        "rating": rating, "reason": reason,
    }


# ---------- 板块轮动 ----------

def _merge_boards(industry, concept):
    out = []
    for b in industry:
        out.append({**b, "type": "行业"})
    for b in concept:
        out.append({**b, "type": "概念"})
    return [b for b in out if b.get("pct") == b.get("pct")]


def _rotation_feature(top, bottom):
    """当日板块轮动核心特征（客观数据推导）。"""
    parts = []
    if top:
        top_types = Counter(b["type"] for b in top)
        if top[0]["pct"] >= 1.5:
            if top_types.get("概念", 0) >= 5:
                parts.append("题材轮动活跃，概念板块领涨")
            elif top_types.get("行业", 0) >= 7:
                parts.append("行业板块普涨，权重搭台")
        avg_flow = sum(b["flow_yi"] for b in top) / len(top)
        if avg_flow < 0:
            parts.append("领涨板块主力资金净流出，反弹缺乏资金支撑")
        elif avg_flow > 5:
            parts.append("领涨板块获主力资金明显加仓")
    weight_names = {"银行", "证券", "保险", "白酒", "煤炭", "石油", "电力", "房地产", "建筑"}
    if any(b["name"] in weight_names and b["pct"] > 0 for b in top[:4]):
        parts.append("权重护盘特征明显")
    if bottom and any(b["type"] == "概念" for b in bottom[:4]):
        parts.append("前期热门概念退潮，高低切换迹象")
    return "；".join(parts) if parts else "板块轮动特征不显著"


def _boards_block(industry, concept):
    merged = _merge_boards(industry, concept)
    top = sorted(merged, key=lambda x: -x["pct"])[:10]
    bottom = sorted(merged, key=lambda x: x["pct"])[:10]
    feature = _rotation_feature(top, bottom)
    return {
        "top": [{k: b.get(k) for k in ("code", "name", "type", "pct", "flow_yi", "leader", "leader_pct", "up", "down")} for b in top],
        "bottom": [{k: b.get(k) for k in ("code", "name", "type", "pct", "flow_yi", "leader", "leader_pct", "up", "down")} for b in bottom],
        "feature": feature,
    }


# ---------- 资金动向（北向口径说明 + 主力资金替代） ----------

def _north_block(inflow, outflow, boards):
    board_in = sorted([b for b in boards if b["flow_yi"] > 0], key=lambda x: -x["flow_yi"])
    board_out = sorted([b for b in boards if b["flow_yi"] < 0], key=lambda x: x["flow_yi"])
    # 板块口径有行业/概念双重覆盖，只取主要板块 TOP 合计，避免重复计算虚大
    in_sum = round(sum(b["flow_yi"] for b in board_in[:10]), 2)
    out_sum = round(sum(-b["flow_yi"] for b in board_out[:10]), 2)
    st_in = [
        {"name": s.get("name"), "pct": s.get("pct"), "flow_yi": s.get("flow_yi")}
        for s in (inflow or [])[:3]
    ]
    st_out = [
        {"name": s.get("name"), "pct": s.get("pct"), "flow_yi": s.get("flow_yi")}
        for s in (outflow or [])[:3]
    ]
    if board_in or board_out:
        in_dir = "、".join(b["name"] for b in board_in[:3]) or "无"
        out_dir = "、".join(b["name"] for b in board_out[:3]) or "无"
        verdict = (f"板块层面（行业+概念 TOP10 口径）主力净流入合计约 {in_sum} 亿"
                   f"（主要方向：{in_dir}），净流出合计约 {out_sum} 亿（主要方向：{out_dir}）。")
    else:
        verdict = "板块主力资金数据暂不可得。"
    return {
        "status": "stopped",
        "note": "自 2024 年 8 月 19 日起，沪深港通不再实时披露北向资金当日净买入额"
                "（仅按季度披露持股），故本页不展示北向资金净流入数据，"
                "以全市场主力资金（东方财富口径）替代观测。",
        "verdict": verdict,
        "stock_in": st_in,
        "stock_out": st_out,
    }


# ---------- 主线与强弱 ----------

def _persist(code, date):
    """主线持续性：板块近5日K线日均涨幅。"""
    try:
        hist = em.fetch_board_kline(code, limit=8, end_date=date)
        if len(hist) < 5:
            return "持续性待观察（K线数据不足）。"
        pcts = [to_num(r.get("pct")) or 0 for r in hist[-5:]]
        avg = sum(pcts) / len(pcts)
        if avg >= 0.8:
            return f"近5日板块持续走强（日均涨 {avg:.2f}%），趋势延续性较好。"
        if avg <= -0.5:
            return "近5日板块总体走弱，持续性存疑。"
        return f"近5日板块温和运行（日均 {avg:+.2f}%），延续性中性。"
    except Exception:
        return "持续性待观察（K线数据暂不可得）。"


def _mainline_block(zt, top, date):
    zt_boards = zt_summary(zt)["by_board"]
    zt_names = {b["name"] for b in zt_boards[:4]}
    main = None
    for b in top:
        if b["flow_yi"] > 0 and b["name"] in zt_names:
            main = b
            break
    if main is None:
        main = next((b for b in top if b["flow_yi"] > 0), None) or (top[0] if top else None)
    if main is None:
        return {
            "main": "数据不足，暂无法判定", "logic": "板块数据暂不可得。",
            "persist": "待数据恢复后更新。", "side": [], "weak": [],
            "style": "风格数据暂不可得。",
        }
    zt_cnt = next((b["count"] for b in zt_boards if b["name"] == main["name"]), 0)
    logic = (f"板块涨幅 {main['pct']:+.2f}%、主力净流入 {main['flow_yi']} 亿、"
             f"领涨 {main['leader'] or '—'}（{main['leader_pct']:+.2f}%）、板块内 "
             f"{main.get('up') or 0} 家上涨；涨停股集中于该方向 {zt_cnt} 家。")
    side = [{"name": b["name"], "pct": b["pct"], "flow_yi": b["flow_yi"]}
            for b in top if b is not main and 1 <= b["pct"] <= 4][:3]
    weak = [{"name": b["name"], "pct": b["pct"], "flow_yi": b["flow_yi"]}
            for b in sorted(top, key=lambda x: x["pct"]) if b["pct"] <= -1][:3]
    return {
        "main": main["name"],
        "logic": logic,
        "persist": _persist(main["code"], date),
        "side": side,
        "weak": weak,
        "style": "见下方指数风格对比（由指数与板块结构推导）。",
    }


def _style_text(pick):
    d = {x.get("name"): to_num(x.get("pct")) for x in pick}
    sh = d.get("上证指数", 0.0)
    cy = d.get("创业板指", 0.0)
    kc = d.get("科创50", 0.0)
    if max(sh, cy, kc) < 0:
        return "市场整体承压，风格差异不显著（普跌）。"
    if (cy - sh >= 0.3 and kc - sh >= -0.5) or (kc - sh >= 0.3 and cy - sh >= 0):
        return "成长风格占优（创业板/科创强于上证），小盘题材相对活跃。"
    if sh - cy >= 0.3:
        return "权重价值占优（上证强于创业板），资金偏向防御/大盘价值。"
    if sh >= 0 and cy >= 0:
        return "大小盘共振上行，风格相对均衡。"
    return "指数涨跌互现，风格分化不明显。"


# ---------- 行情阶段 ----------

def _ma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _stage_block(indices_pick, kline, amount, amount_prev, emotion_metrics, eh_rows):
    closes = [to_num(r.get("close")) for r in kline if r.get("close") == r.get("close")]
    if len(closes) < 20:
        return {
            "phase": "数据不足，暂不判定",
            "tech": "指数K线数据暂不可得，无法进行技术形态判断。",
            "drivers": "核心驱动数据暂不可得。",
            "contradiction": "暂无法判断核心矛盾。",
            "outlook": "建议待数据恢复后查看。",
        }
    close = closes[-1]
    ma5 = _ma(closes, 5)
    ma10 = _ma(closes, 10)
    ma20 = _ma(closes, 20)
    ma60 = _ma(closes, 60)
    ma20_prev = _ma(closes[:-5], 20)
    ma20_up = ma20_prev is not None and ma20 is not None and ma20 > ma20_prev
    win_high = max(to_num(r.get("high")) for r in kline[-20:] if r.get("high"))
    win_low = min(to_num(r.get("low")) for r in kline[-20:] if r.get("low"))

    tech_parts = []
    above = [n for n, m in (("MA5", ma5), ("MA10", ma10), ("MA20", ma20)) if m is not None and close >= m]
    below = [n for n, m in (("MA5", ma5), ("MA10", ma10), ("MA20", ma20)) if m is not None and close < m]
    if above and below:
        tech_parts.append(f"上证指数收于{'、'.join(above)}上方，上方受{'、'.join(below)}压制")
    elif above:
        tech_parts.append(f"上证指数收于{'、'.join(above)}上方")
    elif below:
        tech_parts.append(f"上证指数收于主要均线下方，上方受{'、'.join(below)}压制")
    else:
        tech_parts.append("上证指数均线关系数据不足")
    tech_parts.append(f"MA20 {'向上' if ma20_up else '走平/向下'}（{'多头发散' if above and ma20_up else '趋势未修复' if not ma20_up else '中性'}）")
    if ma60 is not None:
        tech_parts.append(f"MA60 位于 {ma60:.0f} 点构成{'中期支撑' if close >= ma60 else '中期压力'}")
    tech_parts.append(f"近20日压力位约 {win_high:.0f} 点、支撑位约 {win_low:.0f} 点")
    tech = "；".join(tech_parts) + "。"

    # 量价
    amount_desc = "量能数据暂不可得"
    if amount is not None and amount_prev:
        diff = round((amount / amount_prev - 1) * 100, 2) if amount_prev else 0.0
        amount_desc = f"两市成交 {amount} 亿，较前一交易日同时段{'放量' if diff > 0 else '缩量'} {abs(diff):.2f}%"
    elif amount is not None:
        amount_desc = f"两市成交 {amount} 亿（环比口径暂不可得）"

    # 情绪
    score = emotion_metrics.get("score")
    level = emotion_metrics.get("level", "数据不足")
    emo_desc = f"市场情绪分 {score}（{level}）" if score is not None else "市场情绪数据暂不可得"

    # 情绪周期趋势（近6个交易日）
    cycle_desc = ""
    if len(eh_rows) >= 2:
        scores = [r["score"] for r in eh_rows]
        if scores[-1] - scores[0] >= 10:
            cycle_desc = f"近{len(scores)}日情绪分上行 {scores[0]} → {scores[-1]}，情绪处于修复/升温通道"
        elif scores[0] - scores[-1] >= 10:
            cycle_desc = f"近{len(scores)}日情绪分回落 {scores[0]} → {scores[-1]}，情绪处于退潮通道"
        else:
            cycle_desc = f"近{len(scores)}日情绪分在 {min(scores)}~{max(scores)} 区间震荡，方向不明"
    drivers = f"资金面：{amount_desc}；情绪面：{emo_desc}；技术面：{tech_parts[0]}。"

    # 阶段判定
    sh_pct = next((to_num(x.get("pct")) for x in indices_pick if x.get("name") == "上证指数"), 0.0)
    cy_pct = next((to_num(x.get("pct")) for x in indices_pick if x.get("name") == "创业板指"), 0.0)
    pos = 0
    if ma20 is not None and close >= ma20:
        pos += 1
    elif ma20 is not None:
        pos -= 1
    if ma20_up:
        pos += 1
    else:
        pos -= 1
    if ma60 is not None and close >= ma60:
        pos += 1
    if score is not None and level in ("冰点", "低迷"):
        pos += 1
    if score is not None and level == "亢奋":
        pos -= 1
    if amount is not None and amount_prev and amount > amount_prev and sh_pct < 0:
        pos -= 1  # 放量下跌
    if sh_pct >= 0.5 and cy_pct < -0.3:
        pos -= 1  # 权重护盘、成长杀跌
    if pos >= 3:
        phase = "反弹途中"
    elif pos == 2:
        phase = "震荡修复（偏多）"
    elif pos == 1 or pos == 0:
        phase = "震荡整理"
    elif pos == -1:
        phase = "震荡筑底"
    else:
        phase = "弱势调整（情绪退潮）"

    # 核心矛盾
    contradiction = "暂无法判断核心矛盾"
    if sh_pct > 0.2 and cy_pct < -0.2:
        contradiction = "指数分化：权重护盘与成长杀跌并存，赚钱效应集中于权重。"
    elif score is not None and level in ("亢奋", "活跃") and amount is not None and amount_prev and amount < amount_prev:
        contradiction = "情绪偏热但量能未跟上，反弹高度受制于增量资金。"
    elif amount is not None and amount_prev and amount > amount_prev and sh_pct < 0:
        contradiction = "放量下跌：抛压与承接并存，多空分歧加大。"
    elif score is not None and level in ("冰点", "低迷"):
        contradiction = "情绪处于冰点/低迷区，超跌反弹随时可能触发但持续性待观察。"
    elif ma20 is not None:
        contradiction = f"指数围绕MA20（{ma20:.0f}点）拉锯，方向选择临近。"
    if amount is not None and amount_prev and amount > amount_prev:
        drivers += " 量能放大说明资金参与度提升。"
    elif amount is not None and amount_prev:
        drivers += " 量能萎缩说明场外资金观望。"
    if cycle_desc:
        drivers += f" {cycle_desc}。"

    # 短期推演
    if phase in ("反弹途中", "震荡修复（偏多）"):
        outlook = (f"短期趋势延续需量能配合：若指数在 {win_high:.0f} 点附近放量滞涨需防回踩，"
                   f"下方 {win_low:.0f} 点一线具备支撑；关注主线板块的持续性。")
    elif phase == "震荡整理":
        outlook = (f"方向选择临近：放量突破 {win_high:.0f} 点则反弹空间打开，"
                   f"跌破 {win_low:.0f} 点则需防二次探底。")
    elif phase == "震荡筑底":
        outlook = (f"短期或维持区间震荡，关注 {win_low:.0f} 点附近支撑的有效性与量能能否持续放大，"
                   f"情绪修复是底部确认的前提。")
    else:
        outlook = (f"情绪退潮期亏钱效应上升，高位股补跌风险较大，"
                   f"宜控制仓位、等待情绪冰点后的修复信号。")
    outlook += " 以上为基于当日数据的客观推演，不构成任何投资建议。"

    return {
        "phase": phase,
        "tech": tech,
        "drivers": drivers,
        "contradiction": contradiction,
        "outlook": outlook,
    }


# ---------- 主函数 ----------

def _summary_text(date, indices_pick, amount, amount_prev, breadth, limit, boards, mainline, stage):
    sh = next((x for x in indices_pick if x.get("name") == "上证指数"), None)
    idx_part = f"上证指数 {sh['current']} 点（{sh['pct']:+.2f}%）" if sh else "指数数据暂缺"
    if amount is not None and amount_prev:
        diff = round((amount / amount_prev - 1) * 100, 2) if amount_prev else 0.0
        amt_part = f"两市成交 {amount} 亿（{'放量' if diff > 0 else '缩量'} {abs(diff):.2f}%）"
    elif amount is not None:
        amt_part = f"两市成交 {amount} 亿"
    else:
        amt_part = "成交额数据暂缺"
    main_part = f"主线集中于「{mainline['main']}」" if mainline["main"] and "数据不足" not in mainline["main"] else "主线暂不明朗"
    return (f"{date} 复盘：{idx_part}，{amt_part}；涨停 {limit['zt']} 家、炸板率 {limit['zb_rate']}%、"
            f"最高 {limit['max_lb']} 板，赚钱效应评级「{limit['rating']}」；{main_part}；"
            f"阶段判断：{stage['phase']}。")


def fetch_review(date=None):
    """复盘总结主函数。date 非空时为历史回放（该日收盘口径）。"""
    ds = date.replace("-", "") if date else None

    def safe(name, fn):
        try:
            return name, fn()
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {
            "indices": ex.submit(safe, "indices", lambda: em.fetch_indices() if not date else _indices_history(date)),
            "amount": ex.submit(safe, "amount", lambda: em.fetch_market_amount() if not date else None),
            "breadth": ex.submit(safe, "breadth", lambda: em.fetch_breadth(date=ds) if not date else {"up": 0, "down": 0, "flat": 0}),
            "zt": ex.submit(safe, "zt", lambda: em.fetch_ex_pool("getTopicZTPool", date=ds) if ds else em.fetch_zt_pool()),
            "zb": ex.submit(safe, "zb", lambda: em.fetch_ex_pool("getTopicZBPool", date=ds) if ds else em.fetch_zb_pool()),
            "dt": ex.submit(safe, "dt", lambda: em.fetch_ex_pool("getTopicDTPool", date=ds) if ds else em.fetch_dt_pool()),
            "industry": ex.submit(safe, "industry", em.fetch_industry_boards),
            "concept": ex.submit(safe, "concept", em.fetch_concept_boards),
            "inflow": ex.submit(safe, "inflow", lambda: em.fetch_stock_flow_top(po=1, pz=5) if not date else []),
            "outflow": ex.submit(safe, "outflow", lambda: em.fetch_stock_flow_top(po=0, pz=5) if not date else []),
            "idx_amount": ex.submit(safe, "idx_amount", lambda: _index_amounts() if not date else {}),
            "kline": ex.submit(safe, "kline", lambda: em.fetch_index_kline("1.000001", limit=70, end_date=date)),
            "eh": ex.submit(safe, "eh", lambda: fetch_emotion_history(date, days=6)),
            "rhythm": ex.submit(safe, "rhythm", lambda: _rhythm_live() if not date else None),
        }
        results = {k: f.result() for k, f in futures.items()}

    errors = [str(v.get("error")) for k, v in results.items() if isinstance(v, dict) and "error" in v]
    if date:
        errors.append(f"历史回放({date})：涨跌家数/主力资金为实时数据源，该部分以收盘K线口径呈现")

    indices = results["indices"][1] if not isinstance(results["indices"], dict) else []
    amount = results["amount"][1] if not isinstance(results["amount"], dict) else None
    breadth_raw = results["breadth"][1] if not isinstance(results["breadth"], dict) else {"up": 0, "down": 0, "flat": 0}
    zt = results["zt"][1] if not isinstance(results["zt"], dict) else {"tc": 0, "pool": []}
    zb = results["zb"][1] if not isinstance(results["zb"], dict) else {"tc": 0, "pool": []}
    dt = results["dt"][1] if not isinstance(results["dt"], dict) else {"tc": 0, "pool": []}
    industry = results["industry"][1] if not isinstance(results["industry"], dict) else []
    concept = results["concept"][1] if not isinstance(results["concept"], dict) else []
    inflow = results["inflow"][1] if not isinstance(results["inflow"], dict) else []
    outflow = results["outflow"][1] if not isinstance(results["outflow"], dict) else []
    idx_amount = results["idx_amount"][1] if not isinstance(results["idx_amount"], dict) else {}
    kline = results["kline"][1] if not isinstance(results["kline"], dict) else []
    eh = results["eh"][1] if not isinstance(results["eh"], dict) else {"rows": []}
    rhythm = results["rhythm"][1] if not isinstance(results["rhythm"], dict) else None
    if date and rhythm is None and kline:
        rhythm = _rhythm_history(kline)

    pick = _pick_indices(indices)
    idx_amount_map = {x["name"]: x for x in pick}
    for name, ay in idx_amount.items():
        if name in idx_amount_map and ay:
            idx_amount_map[name]["amount_yi"] = ay

    # 环比成交额：实时口径取前一交易日同时段；历史模式不适用
    amount_prev = _prev_amount_at(datetime.now().strftime("%Y-%m-%d %H:%M")) if not date else None

    breadth = _breadth_block(breadth_raw)
    limit = _limit_block(zt, zb, dt, breadth_raw)
    emotion_metrics = emotion_score(zt, zb, dt, breadth_raw) if not (isinstance(results["zt"], dict) and "error" in results["zt"]) else {"score": None, "level": "数据不足"}
    boards = _boards_block(industry, concept)
    north = _north_block(inflow, outflow, boards and _merge_boards(industry, concept) or [])
    mainline = _mainline_block(zt, boards["top"], date)
    mainline["style"] = _style_text(pick)
    stage = _stage_block(pick, kline, amount, amount_prev, emotion_metrics, eh.get("rows") or [])
    date_label = date or datetime.now().strftime("%Y-%m-%d")
    summary = _summary_text(date_label, pick, amount, amount_prev, breadth, limit, boards, mainline, stage)

    cycle_rows = eh.get("rows") or []
    cycle_desc = ""
    if len(cycle_rows) >= 2:
        scores = [r["score"] for r in cycle_rows]
        if scores[-1] - scores[0] >= 10:
            cycle_desc = f"近{len(scores)}个交易日情绪分上行（{scores[0]} → {scores[-1]}），处于修复/升温通道。"
        elif scores[0] - scores[-1] >= 10:
            cycle_desc = f"近{len(scores)}个交易日情绪分回落（{scores[0]} → {scores[-1]}），处于退潮通道。"
        else:
            cycle_desc = f"近{len(scores)}个交易日情绪分在 {min(scores)}~{max(scores)} 区间震荡，方向不明。"
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "history_date": date,
        "date_label": date_label,
        "indices": pick,
        "rhythm": _rhythm_text(rhythm),
        "amount": {
            "total_yi": amount,
            "prev_yi": amount_prev,
            "diff_pct": round((amount / amount_prev - 1) * 100, 2) if amount is not None and amount_prev else None,
            "verdict": _amount_verdict(amount, amount_prev, date),
        },
        "breadth": breadth,
        "limit": limit,
        "emotion": emotion_metrics,
        "cycle": {"rows": cycle_rows, "desc": cycle_desc},
        "boards": boards,
        "north": north,
        "mainline": mainline,
        "stage": stage,
        "summary": summary,
        "risk": RISK_TEXT,
        "errors": errors,
    }


def _amount_verdict(amount, amount_prev, date):
    if date:
        return "历史回放：成交额环比为盘中实时口径，不适用。"
    if amount is None:
        return "两市成交额数据暂不可得。"
    if amount_prev:
        diff = round((amount / amount_prev - 1) * 100, 2)
        return f"两市成交 {amount} 亿，较前一交易日同时段{'放量' if diff > 0 else '缩量'} {abs(diff):.2f}%。"
    return f"两市成交 {amount} 亿（环比口径暂不可得）。"
