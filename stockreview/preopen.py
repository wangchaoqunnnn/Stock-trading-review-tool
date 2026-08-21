# -*- coding: utf-8 -*-
"""开盘前瞻模块：隔夜美股 + 外围资产全景，用于 A 股开盘前参考。

数据源（均为公开行情接口）：
- 腾讯美股行情（qt.gtimg.cn）：五大美股指数、中概 ADR、中概 ETF、美债 TLT。
- 东方财富 push2delay：美股全市场 clist（涨跌分布/行业聚合/总成交）、
  美元指数、COMEX 黄金、离岸人民币。
- 新浪（hq.sinajs.cn）：纽约原油（hf_CL）。
- 腾讯美股日K（usfqkline）：道指技术形态。

口径说明（客观严谨，不编造）：
- 罗素2000 以 IWM ETF 代理；美债长端以 TLT ETF 代理（10 年期收益率数据源暂不可得）。
- 美股总成交为东财全市场个股成交额合计（不含 ETF，近似口径）。
- 美股行业板块由全市场个股按 GICS 一级行业等权聚合（成分数≥5 才纳入）。
- "盘前盘后异动"数据不可得，以当日 |涨跌幅|≥10% 家数作为异动强度近似。
- 美股个股成交额不可得，中概资金流向以中概 ETF 表现与涨跌结构近似。
"""
import re
import time
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .net import clist_url, http_get, http_get_json
from .utils import to_num

RISK_TEXT = "本文仅为隔夜外围行情复盘前瞻参考，不构成任何投资建议。股市有风险，投资需谨慎。"

# 五大美股指数（腾讯代码；罗素2000 用 IWM ETF 代理）
US_INDICES = [
    ("道琼斯工业", "usDJI", "道琼斯"),
    ("纳斯达克综合", "usIXIC", "纳斯达克"),
    ("标普500", "usINX", "标普500"),
    ("纳斯达克100", "usNDX", "纳斯达克100"),
    ("罗素2000", "usIWM", "罗素2000(IWM)"),
]

# 中概 ADR（腾讯代码），按方向分组
CN_ADRS = [
    ("usBABA", "阿里巴巴", "互联网"), ("usPDD", "拼多多", "互联网"), ("usJD", "京东", "互联网"),
    ("usNTES", "网易", "互联网"), ("usBIDU", "百度", "互联网"), ("usBILI", "哔哩哔哩", "互联网"),
    ("usTME", "腾讯音乐", "互联网"), ("usBEKE", "贝壳", "互联网"), ("usEDU", "新东方", "互联网"),
    ("usLI", "理想汽车", "新能源车"), ("usXPEV", "小鹏汽车", "新能源车"), ("usNIO", "蔚来", "新能源车"),
    ("usZLAB", "再鼎医药", "医药"), ("usFUTU", "富途控股", "金融科技"),
    ("usTIGR", "老虎证券", "金融科技"), ("usGDS", "万国数据", "科技"),
]
CN_ETFS = [("usKWEB", "中概互联网ETF"), ("usFXI", "中国大盘股ETF"), ("usYINN", "3倍做多富时中国ETF")]

# 外围资产（东财 ulist secid）
EM_FX = [
    ("美元指数", "100.UDI"),
    ("COMEX黄金", "101.GC00Y"),
    ("离岸人民币(USDCNH)", "133.USDCNH"),
]

# GICS 一级行业 → A 股对应方向（情绪传导参考）
SECTOR_TO_A = {
    "信息技术": "半导体/AI算力/软件",
    "通信服务": "通信/传媒/游戏",
    "金融": "券商/银行",
    "能源": "油气/煤炭",
    "原材料": "有色/化工",
    "医疗保健": "医药/创新药",
    "工业": "机械/军工/高端制造",
    "非日常生活消费品": "汽车/家电/免税",
    "日常消费品": "食品饮料/农业",
    "房地产": "地产链",
    "公用事业": "电力/公用",
}


# ---------- 腾讯行情 ----------

def _tencent_quotes(codes):
    """批量腾讯美股行情（gbk 编码，~ 分隔）。失败项跳过。"""
    out = {}
    for i in range(0, len(codes), 20):
        chunk = codes[i:i + 20]
        try:
            raw = http_get("https://qt.gtimg.cn/q=" + ",".join(chunk), decode="gbk", tries=2)
        except Exception:
            continue
        for m in re.finditer(r'v_(\w+)="([^"]*)"', raw):
            code, payload = m.group(1), m.group(2)
            p = payload.split("~")
            if len(p) < 35:
                continue
            out[code] = {
                "name": p[1], "price": to_num(p[3]), "pre_close": to_num(p[4]),
                "open": to_num(p[5]), "vol": to_num(p[6]), "amount": to_num(p[26]),
                "change": to_num(p[31]), "pct": to_num(p[32]),
                "high": to_num(p[33]), "low": to_num(p[34]),
            }
    return out


# ---------- 东财美股全市场（涨跌分布 + 行业聚合 + 总成交） ----------

_US_FIELDS = "f2,f3,f6,f12,f14,f100"


def _us_universe():
    """美股全市场（东财 m:105）并行翻页，返回原始行列表。

    注意：美股 clist 单页上限为 100 行（pz 传 200 也只返回 100），
    必须按 total/100 翻页，否则会漏掉一半（全部下跌股）。
    """
    page_size = 100
    first = http_get_json(clist_url("m:105", _US_FIELDS, fid="f3", po=1, pn=1, pz=page_size),
                          headers={"Referer": "https://quote.eastmoney.com/"})
    data = first.get("data") or {}
    total = int(data.get("total") or 0)
    rows = list(data.get("diff") or [])
    pages = max(1, (total + page_size - 1) // page_size)

    def one(pn):
        for attempt in range(3):
            try:
                d = http_get_json(clist_url("m:105", _US_FIELDS, fid="f3", po=1, pn=pn, pz=page_size),
                                  headers={"Referer": "https://quote.eastmoney.com/"})
                diff = (d.get("data") or {}).get("diff") or []
                if diff:
                    return diff
            except Exception:
                pass
            time.sleep(0.2)
        return []

    with ThreadPoolExecutor(max_workers=8) as ex:
        for part in ex.map(one, range(2, pages + 1)):
            rows.extend(part)
    return rows


def _us_breadth(rows):
    """美股涨跌分布：涨跌平家数、大涨(≥5%)、大跌(≤-5%)、异动(|pct|≥10%)、个股成交合计。"""
    up = down = flat = big_up = big_dn = wild = 0
    amt = 0.0
    for r in rows:
        p = to_num(r.get("f3"))
        if p != p:  # 无涨跌幅数据的停牌/新股不计入分布
            continue
        v = to_num(r.get("f6"))
        if v == v:
            amt += v
        if p > 0:
            up += 1
        elif p < 0:
            down += 1
        else:
            flat += 1
        if p >= 5:
            big_up += 1
        if p <= -5:
            big_dn += 1
        if abs(p) >= 10:
            wild += 1
    tot = up + down + flat
    up_pct = round(up / tot * 100, 1) if tot else 0.0
    down_pct = round(down / tot * 100, 1) if tot else 0.0
    flat_pct = round(flat / tot * 100, 1) if tot else 0.0
    if tot == 0:
        verdict = "美股涨跌分布数据暂不可得。"
    else:
        ratio = round(up / down, 2) if down else 99.0
        if ratio >= 1.5:
            mood = "普涨格局"
        elif ratio >= 1.1:
            mood = "涨多跌少"
        elif ratio <= 0.6:
            mood = "普跌承压"
        elif ratio <= 0.85:
            mood = "偏弱震荡"
        else:
            mood = "多空均衡"
        verdict = (f"上涨 {up} 家（{up_pct}%）、下跌 {down} 家（{down_pct}%）、平盘 {flat} 家（{flat_pct}%）；"
                   f"涨跌比 {ratio}，{mood}。大涨(≥+5%) {big_up} 家、大跌(≤-5%) {big_dn} 家、"
                   f"大幅异动(|≥10%|) {wild} 家。")
    return {
        "up": up, "down": down, "flat": flat,
        "up_pct": up_pct, "down_pct": down_pct, "flat_pct": flat_pct,
        "big_up": big_up, "big_dn": big_dn, "wild": wild,
        "total_amt_yi": round(amt / 100000000, 2),
        "verdict": verdict,
    }


def _us_sectors(rows):
    """美股行业板块（GICS 一级行业聚合，成分数≥5；涨幅取剔除极端值后的等权均值）。"""
    groups = defaultdict(list)
    for r in rows:
        ind = r.get("f100")
        if not ind or ind == "-":
            continue
        p = to_num(r.get("f3"))
        if p != p:
            continue
        groups[ind].append((p, r))
    out = []
    for ind, items in groups.items():
        if len(items) < 5:
            continue
        # 剔除 |涨跌幅|>50 的异常值（多为不流动微盘股/权证），避免单只扭曲板块
        valid = [(p, r) for p, r in items if abs(p) <= 50] or items
        pcts = [p for p, _ in valid]
        leader = max(valid, key=lambda x: x[0])
        up = sum(1 for p in pcts if p > 0)
        amt = 0.0
        for _, r in valid:
            v = to_num(r.get("f6"))
            if v == v:
                amt += v
        out.append({
            "name": ind, "pct": round(sum(pcts) / len(pcts), 2),
            "up": up, "down": len(valid) - up, "count": len(valid),
            "leader": leader[1].get("f14"), "leader_pct": round(leader[0], 2),
            "amount_yi": round(amt / 100000000, 2),
        })
    out.sort(key=lambda x: -x["pct"])
    return out


def _us_rating(spx_pct, b, sectors):
    """美股赚钱效应评级：极寒/偏冷/温和/火热。"""
    score = 0
    parts = []
    if spx_pct >= 0.5:
        score += 1
        parts.append(f"标普500 涨 {spx_pct:+.2f}%")
    elif spx_pct <= -0.5:
        score -= 1
        parts.append(f"标普500 跌 {spx_pct:+.2f}%")
    if b["up"] and b["down"]:
        ratio = b["up"] / b["down"]
        if ratio >= 1.5:
            score += 1
            parts.append(f"涨跌比 {ratio:.2f} 普涨")
        elif ratio <= 0.6:
            score -= 1
            parts.append(f"涨跌比 {ratio:.2f} 普跌")
    tech = next((s for s in sectors if s["name"] == "信息技术"), None)
    if tech is not None:
        if tech["pct"] >= 0.5:
            score += 1
            parts.append(f"科技(信息技术) {tech['pct']:+.2f}% 领涨")
        elif tech["pct"] <= -0.5:
            score -= 1
            parts.append(f"科技(信息技术) {tech['pct']:+.2f}% 杀跌")
    if b["big_up"] >= 100:
        score += 1
        parts.append(f"大涨股 {b['big_up']} 家")
    if b["big_dn"] >= 100:
        score -= 1
        parts.append(f"大跌股 {b['big_dn']} 家")
    rating = "火热" if score >= 3 else "温和" if score >= 1 else "偏冷" if score >= -1 else "极寒"
    return rating, f"{'；'.join(parts)}。综合评级：{rating}。"


# ---------- 东财 ulist（美元/黄金/离岸人民币） ----------

def _em_ulist(secids):
    params = {"fltt": 2, "invt": 2, "fields": "f2,f3,f12,f14,f17,f18", "secids": ",".join(secids)}
    url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get?" + urllib.parse.urlencode(params)
    try:
        data = http_get_json(url, headers={"Referer": "https://quote.eastmoney.com/"})
        return (data.get("data") or {}).get("diff") or []
    except Exception:
        return []


# ---------- 新浪原油 ----------

def _sina_oil():
    """纽约原油主力（新浪 hf_CL）。返回 dict 或 None。"""
    try:
        raw = http_get("https://hq.sinajs.cn/list=hf_CL",
                       headers={"Referer": "https://finance.sina.com.cn"}, decode="gbk", tries=2)
        m = re.search(r'="([^"]*)"', raw)
        if not m:
            return None
        p = m.group(1).split(",")
        if len(p) < 6 or not p[0]:
            return None
        price = to_num(p[0])
        pre = to_num(p[3])
        return {
            "name": p[13] if len(p) > 13 else "纽约原油",
            "price": price,
            "pre_close": pre,
            "high": to_num(p[4]), "low": to_num(p[5]),
            "pct": round((price / pre - 1) * 100, 2) if pre else 0.0,
        }
    except Exception:
        return None


# ---------- 指数节奏 / 技术形态 ----------

def _index_rhythm(q):
    if not q or not q["pre_close"] or not q["open"]:
        return None
    open_pct = (q["open"] / q["pre_close"] - 1) * 100
    intraday = (q["price"] / q["open"] - 1) * 100
    pos = (q["price"] - q["low"]) / (q["high"] - q["low"]) * 100 if q["high"] > q["low"] else 50.0
    return {"open_pct": round(open_pct, 2), "intraday_pct": round(intraday, 2), "position": round(pos, 1)}


def _rhythm_text(r, name="标普500"):
    if not r:
        return "美股分时节奏数据暂不可得，以上为收盘口径。"
    open_desc = "高开" if r["open_pct"] >= 0.15 else ("低开" if r["open_pct"] <= -0.15 else "平开")
    intraday_desc = (
        "盘中震荡上行" if r["intraday_pct"] >= 0.3
        else "盘中震荡回落" if r["intraday_pct"] <= -0.3
        else "盘中窄幅震荡"
    )
    pos_desc = "收于日内高位区" if r["position"] >= 70 else ("收于日内低位区" if r["position"] <= 30 else "收于日内中位区")
    return f"{name}{open_desc} {abs(r['open_pct']):.2f}%，{intraday_desc}（相对开盘 {r['intraday_pct']:+.2f}%），{pos_desc}。"


def _ma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def _dow_kline():
    """道指日K（腾讯 usfqkline），失败返回 []。"""
    try:
        param = "usDJI,day,,,70,qfq"
        url = "https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get?" + urllib.parse.urlencode({"param": param})
        data = http_get_json(url, headers={"Referer": "https://gu.qq.com/"}, tries=2)
        node = (data.get("data") or {}).get("usDJI") or {}
        return node.get("qfqday") or node.get("day") or []
    except Exception:
        return []


def _us_stage(indices, kline, b, rating, spx_pct):
    """美股行情阶段：道指技术形态 + 量价 + 情绪。"""
    closes = [to_num(r[2]) for r in kline if len(r) >= 3]
    if len(closes) < 20:
        return {
            "phase": "数据不足，暂不判定",
            "tech": "道指日K数据暂不可得，无法进行技术形态判断。",
            "drivers": "核心驱动数据暂不可得。",
            "contradiction": "暂无法判断核心矛盾。",
            "focus": "建议待数据恢复后查看。",
        }
    close = closes[-1]
    ma5 = _ma(closes, 5)
    ma10 = _ma(closes, 10)
    ma20 = _ma(closes, 20)
    ma60 = _ma(closes, 60)
    ma20_prev = _ma(closes[:-5], 20)
    ma20_up = ma20_prev is not None and ma20 is not None and ma20 > ma20_prev
    highs = [to_num(r[3]) for r in kline[-20:] if len(r) >= 5]
    lows = [to_num(r[4]) for r in kline[-20:] if len(r) >= 5]
    win_high = max(highs) if highs else close
    win_low = min(lows) if lows else close
    vol_now = to_num(kline[-1][5]) if len(kline[-1]) > 5 else 0.0
    vol_prev = to_num(kline[-2][5]) if len(kline) >= 2 and len(kline[-2]) > 5 else 0.0
    vol_ratio = round(vol_now / vol_prev, 2) if vol_prev else None

    tech_parts = []
    above = [n for n, m in (("MA5", ma5), ("MA10", ma10), ("MA20", ma20)) if m is not None and close >= m]
    below = [n for n, m in (("MA5", ma5), ("MA10", ma10), ("MA20", ma20)) if m is not None and close < m]
    if above and below:
        tech_parts.append(f"道指收于{'、'.join(above)}上方，上方受{'、'.join(below)}压制")
    elif above:
        tech_parts.append(f"道指收于{'、'.join(above)}上方")
    elif below:
        tech_parts.append(f"道指收于主要均线下方，上方受{'、'.join(below)}压制")
    else:
        tech_parts.append("道指均线关系数据不足")
    tech_parts.append(f"MA20 {'向上' if ma20_up else '走平/向下'}")
    if ma60 is not None:
        tech_parts.append(f"MA60 位于 {ma60:.0f} 点构成{'中期支撑' if close >= ma60 else '中期压力'}")
    tech_parts.append(f"近20日压力位约 {win_high:.0f} 点、支撑位约 {win_low:.0f} 点")
    if vol_ratio is not None:
        tech_parts.append(f"成交量较前一交易日{'放量' if vol_ratio > 1.05 else '缩量' if vol_ratio < 0.95 else '基本持平'}（{vol_ratio:.2f}倍）")
    tech = "；".join(tech_parts) + "。"

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
    if spx_pct >= 0.5:
        pos += 1
    elif spx_pct <= -0.5:
        pos -= 1
    if rating in ("火热", "温和"):
        pos += 1
    elif rating in ("偏冷", "极寒"):
        pos -= 1
    phase = (
        "多头趋势延续" if pos >= 4
        else "震荡偏强" if pos == 3
        else "高位震荡" if pos == 2
        else "震荡整理" if pos in (0, 1)
        else "技术调整/转弱" if pos >= -2
        else "弱势调整"
    )

    amount_desc = f"美股个股成交合计约 {b['total_amt_yi']} 亿美元（东财全市场近似口径）" if b["total_amt_yi"] else "美股总成交数据暂不可得"
    drivers = f"资金面：{amount_desc}；情绪面：评级「{rating}」、涨跌比 {round(b['up'] / b['down'], 2) if b['down'] else '—'}；技术面：{tech_parts[0]}。"

    # 核心矛盾
    contradiction = "暂无法判断核心矛盾"
    d = {n: idx.get("pct") for n, idx in indices.items()}
    nas, dow = d.get("纳斯达克综合"), d.get("道琼斯工业")
    if nas is not None and dow is not None:
        if nas - dow >= 0.4:
            contradiction = "科技成长强于传统价值，市场风险偏好回升但结构分化明显。"
        elif dow - nas >= 0.4:
            contradiction = "价值/防御强于成长，资金避险情绪主导。"
    if b["up"] and b["down"] and spx_pct > 0.3 and b["up"] / b["down"] < 0.9:
        contradiction += " 指数上行但涨跌比偏低，权重拉动与普涨不足并存。"
    if not contradiction.startswith("暂无法"):
        pass
    if vol_ratio is not None and vol_ratio > 1.1 and spx_pct < 0:
        contradiction = "放量下跌：抛压增强，短线或有惯性下探。"
    focus = _focus_text(d, contradiction)

    return {"phase": phase, "tech": tech, "drivers": drivers, "contradiction": contradiction, "focus": focus}


def _focus_text(d, contradiction):
    items = []
    if "科技" in contradiction or "成长" in contradiction:
        items.append("纳指/科技股开盘方向，A股半导体与AI链联动")
    if "避险" in contradiction:
        items.append("防御板块持续性，A股高股息/公用事业承接")
    items.append("中概与港股 ADR 开盘表现（互联网情绪传导）")
    items.append("离岸人民币与北向资金动向")
    return "开盘重点观察：" + "；".join(items) + "。"


# ---------- 主线与传导 ----------

def _us_feature(sectors, indices):
    parts = []
    top = sectors[:5]
    bottom = sectors[-5:]
    if top and top[0]["pct"] >= 0.5:
        if top[0]["name"] in ("信息技术", "通信服务"):
            parts.append("科技成长领涨，科技抱团特征明显")
        else:
            parts.append(f"{top[0]['name']}板块领涨")
    if any(s["name"] in ("公用事业", "房地产", "医疗保健", "日常消费品") and s["pct"] > 0 for s in top):
        parts.append("防御/避险板块走强")
    if bottom and bottom[0]["pct"] <= -0.5 and bottom[0]["name"] in ("信息技术", "非日常生活消费品", "通信服务"):
        parts.append("成长方向杀跌")
    elif bottom and bottom[0]["pct"] <= -0.5:
        parts.append(f"{bottom[0]['name']}板块垫底")
    d = {n: idx.get("pct") for n, idx in indices.items()}
    nas, dow, rut = d.get("纳斯达克综合"), d.get("道琼斯工业"), d.get("罗素2000")
    if nas is not None and dow is not None and nas - dow >= 0.4:
        parts.append("纳指显著强于道指，成长风格占优")
    elif dow is not None and nas is not None and dow - nas >= 0.4:
        parts.append("道指显著强于纳指，价值/防御占优")
    if rut is not None and nas is not None and rut - nas >= 0.5:
        parts.append("小盘跑赢大盘，风险偏好回升")
    return "；".join(parts) if parts else "板块轮动特征不显著"


def _mainline(sectors, indices, cn_groups, cn_etfs, tlt_pct):
    top = sectors[:10] if sectors else []
    main = top[0] if top else None
    if main is None:
        return {
            "main": "数据不足，暂无法判定", "logic": "美股板块数据暂不可得。",
            "persist": "待数据恢复后更新。", "side": [], "weak": [], "style": "风格数据暂不可得。",
            "impact_a": "对 A 股影响暂无法判断。",
        }
    logic = (f"板块等权涨幅 {main['pct']:+.2f}%（{main['count']} 只成分股，涨 {main['up']} / 跌 {main['down']}），"
             f"领涨 {main['leader']}（{main['leader_pct']:+.2f}%），板块成交约 {main['amount_yi']} 亿美元。")
    # 持续性：以板块成分股近月走势不可得，以当日强度与量能近似
    persist = "持续性待观察（美股板块历史K线数据暂不可得）。"
    side = [{"name": s["name"], "pct": s["pct"]} for s in top[1:4]]
    weak = [{"name": s["name"], "pct": s["pct"]} for s in sectors[-3:]] if sectors else []
    d = {n: idx.get("pct") for n, idx in indices.items()}
    nas, dow = d.get("纳斯达克综合"), d.get("道琼斯工业")
    if nas is not None and dow is not None:
        if nas - dow >= 0.4:
            style = "科技成长风格占优（纳指强于道指）。"
        elif dow - nas >= 0.4:
            style = "大盘价值/防御风格占优（道指强于纳指）。"
        elif nas >= 0.3 and dow >= 0.3:
            style = "普涨格局，风格均衡。"
        else:
            style = "市场整体承压，风格差异不显著。"
    else:
        style = "风格数据暂不可得。"
    impact_a = _impact_a(indices, cn_groups, cn_etfs, tlt_pct, sectors)
    return {"main": main["name"], "logic": logic, "persist": persist,
            "side": side, "weak": weak, "style": style, "impact_a": impact_a}


def _impact_a(indices, cn_groups, cn_etfs, tlt_pct, sectors):
    """美股情绪 → 今日 A 股开盘传导（客观描述，不含个股）。"""
    parts = []
    d = {n: idx.get("pct") for n, idx in indices.items()}
    nas, dow = d.get("纳斯达克综合"), d.get("道琼斯工业")
    if nas is not None and dow is not None:
        if nas <= -0.5 and dow >= -0.3:
            parts.append("美股科技杀跌、道指抗跌：A股成长/科技方向开盘或承压，权重与低估值相对抗跌")
        elif nas >= 0.5:
            parts.append("纳指走强：A股科技成长方向开盘情绪偏暖")
    cn_avg = None
    if cn_groups:
        vals = [g["avg_pct"] for g in cn_groups]
        cn_avg = round(sum(vals) / len(vals), 2)
    if cn_avg is not None:
        if cn_avg <= -1:
            parts.append(f"中概普跌（均值 {cn_avg:+.2f}%）：A股互联网/港股科技情绪传导偏负面，关注低开后承接")
        elif cn_avg >= 0.5:
            parts.append(f"中概普涨（均值 {cn_avg:+.2f}%）：A股互联网/港股科技情绪传导偏正面")
    top = sectors[:3] if sectors else []
    if top and top[0]["name"] in SECTOR_TO_A:
        parts.append(f"美股主线「{top[0]['name']}」走强：对A股{SECTOR_TO_A[top[0]['name']]}或有映射")
    if tlt_pct is not None and tlt_pct <= -0.4:
        parts.append("美债长端回落（TLT 走强）：美债收益率下行，对成长股估值形成支撑")
    elif tlt_pct is not None and tlt_pct >= 0.4:
        parts.append("美债长端走弱（TLT 下跌）：收益率上行，对高估值成长股估值形成压制")
    return "；".join(parts) if parts else "隔夜外围对 A 股开盘的传导信号暂不显著。"


# ---------- 主函数 ----------

def fetch_preopen(date=None):
    """开盘前瞻主函数。date 参数忽略（美股为隔夜最新收盘口径，不支持历史回放）。"""
    errors = []
    if date:
        errors.append("美股/外围为隔夜最新收盘口径，不支持历史回放（date 参数已忽略）")

    qs = _tencent_quotes([c for _, c, _ in US_INDICES] + [c for c, _, _ in CN_ADRS] + [c for c, _ in CN_ETFS] + ["usTLT"])
    indices = {}
    for name, code, label in US_INDICES:
        q = qs.get(code)
        if not q:
            continue
        indices[name] = {
            "name": name, "label": label, "price": q["price"], "pct": q["pct"],
            "open": q["open"], "pre_close": q["pre_close"],
            "high": q["high"], "low": q["low"],
            "amount": q["amount"] or None,
        }

    rows = []
    try:
        rows = _us_universe()
    except Exception as exc:
        errors.append(f"美股全市场数据: {type(exc).__name__}: {exc}")
    b = _us_breadth(rows)
    sectors = _us_sectors(rows)
    spx_pct = indices.get("标普500", {}).get("pct", 0.0)
    rating, rating_reason = _us_rating(spx_pct, b, sectors)

    # 中概
    cn_stocks = []
    for code, name, grp in CN_ADRS:
        q = qs.get(code)
        if q:
            cn_stocks.append({"name": name, "group": grp, "pct": q["pct"], "price": q["price"]})
    cn_groups = []
    by_grp = defaultdict(list)
    for s in cn_stocks:
        by_grp[s["group"]].append(s)
    for g, rs in by_grp.items():
        avg = round(sum(r["pct"] for r in rs) / len(rs), 2)
        rs_sorted = sorted(rs, key=lambda x: -x["pct"])
        cn_groups.append({"group": g, "avg_pct": avg, "stocks": rs_sorted})
    cn_groups.sort(key=lambda x: -x["avg_pct"])
    cn_etfs = [{"name": n, "pct": qs.get(c, {}).get("pct"), "price": qs.get(c, {}).get("price")} for c, n in CN_ETFS]
    cn_etfs = [e for e in cn_etfs if e["pct"] is not None]
    cn_verdict = "中概 ADR 数据暂不可得"
    if cn_stocks:
        avg = round(sum(s["pct"] for s in cn_stocks) / len(cn_stocks), 2)
        best = max(cn_stocks, key=lambda x: x["pct"])
        worst = min(cn_stocks, key=lambda x: x["pct"])
        etf_desc = "、".join(f"{e['name']} {e['pct']:+.2f}%" for e in cn_etfs) if cn_etfs else "暂缺"
        cn_verdict = (f"中概样本均值 {avg:+.2f}%，领涨 {best['name']}（{best['pct']:+.2f}%）、"
                      f"领跌 {worst['name']}（{worst['pct']:+.2f}%）。"
                      f"个股成交额数据不可得，资金方向以中概ETF表现近似（{etf_desc}）。")

    # 外围资产
    fx_rows = []
    for name, secid in EM_FX:
        for r in _em_ulist([secid]):
            if r.get("f14"):
                fx_rows.append({
                    "name": name, "price": r.get("f2"), "pct": r.get("f3"),
                    "pre_close": r.get("f18"), "note": "",
                })
    oil = _sina_oil()
    if oil:
        fx_rows.append({"name": oil["name"], "price": oil["price"], "pct": oil["pct"],
                        "pre_close": oil["pre_close"], "note": "新浪外盘"})
    tlt = qs.get("usTLT")
    if tlt:
        fx_rows.append({"name": "美债20年+(TLT)", "price": tlt["price"], "pct": tlt["pct"],
                        "pre_close": tlt["pre_close"], "note": "10年期收益率数据源暂不可得，以TLT代理长端方向"})

    fx_verdict = _fx_verdict(fx_rows, indices)

    # 指数节奏（用标普500）
    rhythm = _rhythm_text(_index_rhythm(qs.get("usINX")), "标普500")

    kline = _dow_kline()
    stage = _us_stage(indices, kline, b, rating, spx_pct)
    feature = _us_feature(sectors, indices)
    mainline = _mainline(sectors, indices, cn_groups, cn_etfs, tlt["pct"] if tlt else None)

    summary = _summary(indices, b, rating, mainline, stage)
    as_of = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "as_of": as_of,
        "indices": list(indices.values()),
        "rhythm": rhythm,
        "market": {
            "total_amt_yi": b["total_amt_yi"],
            "total_verdict": f"美股个股成交合计约 {b['total_amt_yi']} 亿美元（东财全市场近似口径，不含ETF；环比数据暂不可得）。" if b["total_amt_yi"] else "美股总成交数据暂不可得。",
            "breadth": b,
            "rating": {"level": rating, "reason": rating_reason},
        },
        "sectors": {
            "top": [{k: s.get(k) for k in ("name", "pct", "up", "down", "count", "leader", "leader_pct", "amount_yi")} for s in sectors[:10]],
            "bottom": [{k: s.get(k) for k in ("name", "pct", "up", "down", "count", "leader", "leader_pct", "amount_yi")} for s in sectors[-10:]],
            "feature": feature,
        },
        "cn": {"stocks": cn_stocks, "groups": cn_groups, "etfs": cn_etfs, "verdict": cn_verdict},
        "fx": {"rows": fx_rows, "verdict": fx_verdict},
        "mainline": mainline,
        "stage": stage,
        "summary": summary,
        "risk": RISK_TEXT,
        "errors": errors,
    }


def _fx_verdict(fx_rows, indices):
    d = {r["name"]: r for r in fx_rows}
    parts = []
    gold = d.get("COMEX黄金")
    oil = next((r for r in fx_rows if "原油" in r["name"]), None)
    cnh = d.get("离岸人民币(USDCNH)")
    usd = d.get("美元指数")
    tlt = d.get("美债20年+(TLT)")
    if gold:
        if gold["pct"] >= 0.2:
            parts.append(f"黄金走强（{gold['pct']:+.2f}%）→ A股贵金属板块或有映射")
        elif gold["pct"] <= -0.2:
            parts.append(f"黄金走弱（{gold['pct']:+.2f}%）→ A股贵金属板块情绪偏弱")
    if oil:
        if oil["pct"] <= -0.5:
            parts.append("原油走弱 → 利好航空/化工成本端，油气链承压")
        elif oil["pct"] >= 0.5:
            parts.append("原油走强 → A股油气/油服板块情绪偏暖")
    if cnh:
        if cnh["pct"] <= -0.1:
            parts.append("离岸人民币升值 → 外资风险偏好回升，对北向资金偏正面")
        elif cnh["pct"] >= 0.1:
            parts.append("离岸人民币贬值 → 对外资流入略偏负面")
    if usd:
        if usd["pct"] <= -0.1:
            parts.append("美元指数回落 → 对新兴市场资产偏正面")
    if tlt:
        if tlt["pct"] <= -0.4:
            parts.append("美债长端回落（TLT 走强）→ 收益率下行支撑成长估值")
        elif tlt["pct"] >= 0.4:
            parts.append("美债长端收益率上行 → 对高估值成长股形成压制")
    return "；".join(parts) if parts else "外围资产传导信号暂不显著。"


def _summary(indices, b, rating, mainline, stage):
    spx = indices.get("标普500")
    idx_part = f"标普500 {spx['price']:.2f}（{spx['pct']:+.2f}%）" if spx else "指数数据暂缺"
    amt_part = f"个股成交约 {b['total_amt_yi']} 亿美元" if b["total_amt_yi"] else "成交数据暂缺"
    main_part = f"主线「{mainline['main']}」" if mainline["main"] and "数据不足" not in mainline["main"] else "主线暂不明朗"
    return (f"隔夜美股：{idx_part}，{amt_part}，涨跌比 {round(b['up'] / b['down'], 2) if b['down'] else '—'}，"
            f"赚钱效应「{rating}」；{main_part}；阶段判断：{stage['phase']}。")
