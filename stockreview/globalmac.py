# -*- coding: utf-8 -*-
"""全球宏观模块：全球股指 / 外汇 / 债券 / 贵金属大宗 / 跨资产联动全景。

数据源（均为公开行情接口，客观严谨、如实标注口径）：
- 东财 push2delay：全球股指（恒生/日经/KOSPI/富时100/DAX/CAC40/A50）、
  外汇（美元指数/美元日元/欧元美元/英镑美元/离岸人民币）、COMEX 贵金属与铜。
- 腾讯美股行情：道指/纳指/标普500。
- 新浪：在岸人民币、WTI/布伦特原油、伦铜/美铜、碳酸锂主力、10年国债期货。

口径说明：
- 富时中国A50 期货主力合约数据源暂不可得，以富时中国A50 现货指数（XIN9）代理。
- 美债 10Y/2Y 收益率实时数据源暂不可得，以 7-10 年（IEF）/1-3 年（SHY）美债
  ETF 方向近似，利差以两者相对强弱近似描述。
- 中国 10 年期国债收益率以 10 年国债期货主力（nf_T0）价格代理（收益率与价格反向）。
- 日本 10 年期国债收益率暂无公开实时接口，如实标注暂不可得。
- 宏观数据与事件日历暂无公开实时接口，本页聚焦行情联动，数据/事件以官方公布为准。
"""
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import em
from .net import http_get, http_get_json, clist_url
from .preopen import _em_ulist, _tencent_quotes
from .utils import to_num

RISK_TEXT = "本文仅为宏观行情复盘参考，不构成任何投资建议。市场有风险，投资需谨慎。"

# 全球股指（东财 secid；名称与东财返回严格一致）
EU_INDICES = [
    ("英国富时100", "100.FTSE"),
    ("德国DAX30", "100.GDAXI"),
    ("法国CAC40", "100.FCHI"),
]
APAC_INDICES = [
    ("日经225", "100.N225"),
    ("韩国KOSPI", "100.KS11"),
    ("恒生指数", "100.HSI"),
]
GLOBAL_INDICES = EU_INDICES + APAC_INDICES
US_INDICES = [
    ("道琼斯", "usDJI"),
    ("标普500", "usINX"),
    ("纳斯达克", "usIXIC"),
]
FX_EM = [
    ("美元指数", "100.UDI", "美元指数"),
    ("美元/日元", "119.USDJPY", "美元兑日元"),
    ("欧元/美元", "119.EURUSD", "欧元兑美元"),
    ("英镑/美元", "119.GBPUSD", "英镑兑美元"),
    ("离岸人民币(USD/CNH)", "133.USDCNH", "美元兑离岸人民币"),
]
COMM_EM = [
    ("COMEX黄金", "101.GC00Y", "美元/盎司"),
    ("COMEX白银", "101.SI00Y", "美元/盎司"),
    ("COMEX铜", "101.HG00Y", "美元/磅"),
]


# ---------- 新浪解析 ----------

def _sina_raw(codes):
    try:
        return http_get("https://hq.sinajs.cn/list=" + codes,
                        headers={"Referer": "https://finance.sina.com.cn"}, decode="gbk", tries=2)
    except Exception:
        return None


def _sina_fx(code, name):
    """新浪外汇（fx_susdcny 等）：字段 1=现价 5=昨收 6=今开 7=最低 8=最高。"""
    raw = _sina_raw(code)
    if not raw:
        return None
    m = re.search(r'="([^"]*)"', raw)
    if not m:
        return None
    p = m.group(1).split(",")
    if len(p) < 9 or not p[1]:
        return None
    price = to_num(p[1])
    prev = to_num(p[5])
    return {
        "name": name, "price": price, "pre_close": prev,
        "open": to_num(p[6]), "low": to_num(p[7]), "high": to_num(p[8]),
        "pct": round((price / prev - 1) * 100, 3) if prev else 0.0,
    }


def _sina_nf(code, name):
    """新浪国内期货（nf_ 系列）自适应解析。

    中金所格式（nf_T0）：0=现价 1-3=盘口 9=最高 10=最低 13=昨结 14=今开
    广期所格式（nf_LC0）：0=名称 1=时间 2=现价 3=最高 4=最低 6=今开 7=昨收
    """
    raw = _sina_raw(code)
    if not raw:
        return None
    m = re.search(r'="([^"]*)"', raw)
    if not m:
        return None
    p = m.group(1).split(",")
    if not p or not p[0]:
        return None
    first = to_num(p[0])
    if first == first and len(p) >= 15:
        # 中金所格式
        price = first
        prev = to_num(p[13])
        return {
            "name": name, "price": price, "pre_close": prev,
            "open": to_num(p[14]), "high": to_num(p[9]), "low": to_num(p[10]),
            "pct": round((price / prev - 1) * 100, 2) if prev else 0.0,
        }
    if len(p) >= 8:
        # 广期所格式（名称开头）
        price = to_num(p[2])
        prev = to_num(p[7])
        return {
            "name": p[0] or name, "price": price, "pre_close": prev,
            "open": to_num(p[6]), "high": to_num(p[3]), "low": to_num(p[4]),
            "pct": round((price / prev - 1) * 100, 2) if prev else 0.0,
        }
    return None


def _sina_hf(code, name):
    """新浪外盘期货（hf_ 系列）：字段 0=现价 2=今开 3=昨收 4=最高 5=最低 13=名称。"""
    raw = _sina_raw(code)
    if not raw:
        return None
    m = re.search(r'="([^"]*)"', raw)
    if not m:
        return None
    p = m.group(1).split(",")
    if len(p) < 6 or not p[0]:
        return None
    price = to_num(p[0])
    prev = to_num(p[3])
    return {
        "name": name, "price": price, "pre_close": prev,
        "open": to_num(p[2]), "high": to_num(p[4]), "low": to_num(p[5]),
        "pct": round((price / prev - 1) * 100, 2) if prev else 0.0,
    }


# ---------- 组合 ----------

def _collect():
    """并行抓取全部数据，返回原始字段。"""
    out = {"em_fx": [], "global_idx": [], "us_idx": {}, "comm": [], "sina": {}}

    def safe(fn):
        try:
            return fn()
        except Exception:
            return None

    # 东财 ulist 按市场分组抓（混合市场的请求会整体失败）
    em_fx_groups = {}
    for _, secid, _ in FX_EM:
        market = secid.split(".")[0]
        em_fx_groups.setdefault(market, []).append(secid)
    global_secids = [s for _, s in GLOBAL_INDICES]
    comm_secids = [s for _, s, _ in COMM_EM]

    with ThreadPoolExecutor(max_workers=8) as ex:
        f1a = [ex.submit(safe, lambda g=g: _em_ulist(g)) for g in em_fx_groups.values()]
        f2 = ex.submit(safe, lambda: _em_ulist(global_secids))
        f3 = ex.submit(safe, lambda: _em_ulist(comm_secids))
        f4 = ex.submit(safe, lambda: _tencent_quotes([c for _, c in US_INDICES]))
        f5 = ex.submit(safe, lambda: _sina_fx("fx_susdcny", "在岸人民币(USD/CNY)"))
        f6 = ex.submit(safe, lambda: _sina_nf("nf_T0", "中国10年国债期货主力"))
        f7 = ex.submit(safe, lambda: _sina_nf("nf_LC0", "碳酸锂主力(元/吨)"))
        f8 = ex.submit(safe, lambda: _sina_hf("hf_CL", "WTI原油"))
        f9 = ex.submit(safe, lambda: _sina_hf("hf_OIL", "布伦特原油"))
        f10 = ex.submit(safe, lambda: _sina_hf("hf_CAD", "LME铜(美元/吨)"))
        f11 = ex.submit(safe, lambda: _em_ulist(["105.SHY", "105.IEF", "105.TLT", "100.XIN9"]))
        out["em_fx"] = [r for f in f1a for r in (f.result() or [])]
        out["global_idx"] = f2.result() or []
        out["comm"] = f3.result() or []
        out["us_idx"] = f4.result() or {}
        out["sina_cny"] = f5.result()
        out["sina_t0"] = f6.result()
        out["sina_lc"] = f7.result()
        out["sina_cl"] = f8.result()
        out["sina_oil"] = f9.result()
        out["sina_cad"] = f10.result()
        out["bond_etf"] = f11.result() or []
    return out


def _row(d, name, key=None):
    """从东财 ulist diff 中取指定名称的行。"""
    for r in d:
        if r.get("f14") == name:
            return {"name": name, "price": r.get("f2"), "pre_close": r.get("f18"),
                    "open": r.get("f17"), "pct": r.get("f3")}
    return None


def _fx_verdict(rows):
    """外汇市场核心主线（客观推导）。"""
    d = {r["name"]: r for r in rows}
    parts = []
    usd = d.get("美元指数")
    cnh = d.get("离岸人民币(USD/CNH)")
    cny = d.get("在岸人民币(USD/CNY)")
    jpy = d.get("美元/日元")
    eur = d.get("欧元/美元")
    gbp = d.get("英镑/美元")
    if usd:
        if usd["pct"] <= -0.1:
            parts.append(f"美元指数走弱（{usd['pct']:+.2f}%），非美货币整体偏强")
        elif usd["pct"] >= 0.1:
            parts.append(f"美元指数走强（{usd['pct']:+.2f}%），非美货币承压")
        else:
            parts.append(f"美元指数基本走平（{usd['pct']:+.2f}%）")
    for name, label in (("在岸人民币(USD/CNY)", "人民币升值"), ("离岸人民币(USD/CNH)", "人民币升值")):
        r = d.get(name)
        if r and r["pct"] is not None:
            if r["pct"] <= -0.05:
                parts.append(f"{name.replace('(USD/CNY)', '').replace('(USD/CNH)', '')}走强（{r['pct']:+.3f}%）")
            elif r["pct"] >= 0.05:
                parts.append(f"{name.replace('(USD/CNY)', '').replace('(USD/CNH)', '')}走弱（{r['pct']:+.3f}%）")
    if jpy and jpy["pct"] is not None:
        if jpy["pct"] >= 0.15:
            parts.append(f"日元走弱（USD/JPY {jpy['pct']:+.2f}%）")
        elif jpy["pct"] <= -0.15:
            parts.append(f"日元走强（USD/JPY {jpy['pct']:+.2f}%）")
    if eur and gbp:
        parts.append(f"欧元 {eur['pct']:+.2f}%、英镑 {gbp['pct']:+.2f}%")
    return "；".join(parts) if parts else "外汇数据暂不可得。"


def _bonds_block(bond_etf, t0):
    """债券市场：美债 ETF 方向 + 中国国债期货。"""
    def pick(names):
        for r in bond_etf:
            if r.get("f14") in names:
                return {"name": r.get("f14"), "price": r.get("f2"), "pct": r.get("f3")}
        return None

    shy = pick(("美国国债1-3年ETF-iShares",))
    ief = pick(("美国国债7-10年ETF-iShares",))
    tlt = pick(("美国国债20年+ETF-iShares",))
    rows = []
    if ief:
        rows.append({"name": "美债10Y(以7-10年ETF代理)", "price": ief["price"], "pct": ief["pct"],
                     "note": "ETF 上涨≈收益率下行；10Y 收益率绝对水平数据源暂不可得"})
    if shy:
        rows.append({"name": "美债2Y(以1-3年ETF代理)", "price": shy["price"], "pct": shy["pct"],
                     "note": "短端方向代理"})
    if tlt:
        rows.append({"name": "美债20Y+(TLT)", "price": tlt["price"], "pct": tlt["pct"], "note": "长端方向代理"})
    if t0:
        rows.append({"name": "中国10Y国债期货主力", "price": t0["price"], "pct": t0["pct"],
                     "note": "收益率与价格反向（昨结代理）"})

    # 2Y/10Y 利差方向：IEF 与 SHY 相对强弱
    spread_desc = "利差数据暂不可得"
    if ief and shy and ief["pct"] is not None and shy["pct"] is not None:
        if ief["pct"] > shy["pct"]:
            spread_desc = "长端 ETF 强于短端（隐含长端收益率下行更多，曲线或趋平）"
        elif ief["pct"] < shy["pct"]:
            spread_desc = "短端 ETF 强于长端（短端收益率下行更多，曲线或趋陡）"
        else:
            spread_desc = "长短端方向一致"

    verdict = _bond_verdict(ief, shy, tlt)
    return {
        "rows": rows,
        "note": "美债 10Y/2Y 收益率实时数据源暂不可得，以短/中/长端美债 ETF 方向代理（ETF 涨≈收益率跌）；"
                "中国 10Y 以国债期货主力价格代理（价格与收益率反向）；日本 10Y 暂无公开实时接口。",
        "spread": spread_desc,
        "verdict": verdict,
    }


def _bond_verdict(ief, shy, tlt):
    parts = []
    if ief and ief["pct"] is not None:
        parts.append(f"中长端美债 ETF {'走强' if ief['pct'] > 0 else '走弱'}（{ief['pct']:+.2f}%，≈收益率{'下行' if ief['pct'] > 0 else '上行'}）")
    if tlt and tlt["pct"] is not None:
        parts.append(f"超长端 TLT {'走强' if tlt['pct'] > 0 else '走弱'}（{tlt['pct']:+.2f}%）")
    if ief and ief["pct"] is not None and ief["pct"] > 0.2:
        parts.append("美债走强（收益率下行）对全球成长股估值构成支撑、利空美元")
    elif ief and ief["pct"] is not None and ief["pct"] < -0.2:
        parts.append("美债走弱（收益率上行）压制高估值成长资产、支撑美元")
    return "；".join(parts) if parts else "美债数据暂不可得。"


def _comm_verdict(rows):
    """大宗商品强弱格局。"""
    d = {r["name"]: r for r in rows}
    parts = []
    gold = d.get("COMEX黄金")
    silver = d.get("COMEX白银")
    oil = d.get("WTI原油")
    brent = d.get("布伦特原油")
    copper = d.get("LME铜(美元/吨)")
    li = d.get("碳酸锂主力(元/吨)")
    if gold and gold["pct"] is not None:
        if gold["pct"] >= 0.15:
            parts.append(f"黄金走强（{gold['pct']:+.2f}%），避险/宽松交易占优")
        elif gold["pct"] <= -0.15:
            parts.append(f"黄金走弱（{gold['pct']:+.2f}%），风险偏好回升压制避险")
        else:
            parts.append(f"黄金基本走平（{gold['pct']:+.2f}%）")
    if silver and silver["pct"] is not None:
        parts.append(f"白银 {silver['pct']:+.2f}%")
    if oil and oil["pct"] is not None:
        parts.append(f"WTI 原油 {'走强' if oil['pct'] > 0.1 else '走弱' if oil['pct'] < -0.1 else '基本走平'}（{oil['pct']:+.2f}%）")
    if brent and brent["pct"] is not None:
        parts.append(f"布伦特 {brent['pct']:+.2f}%")
    if copper and copper["pct"] is not None:
        if copper["pct"] >= 0.3:
            parts.append(f"铜走强（{copper['pct']:+.2f}%），工业需求预期改善")
        elif copper["pct"] <= -0.3:
            parts.append(f"铜走弱（{copper['pct']:+.2f}%），全球工业需求预期承压")
        else:
            parts.append(f"铜基本走平（{copper['pct']:+.2f}%）")
    if li and li["pct"] is not None:
        parts.append(f"碳酸锂 {li['pct']:+.2f}%（新能源产业链成本端）")
    return "；".join(parts) if parts else "大宗商品数据暂不可得。"


def _risk_appetite(global_idx, us_idx, fx_rows, gold):
    """全球风险偏好判断（risk on / risk off）。

    美股是全球风险偏好的风向标，单独计权；主要股指涨跌占比、均值、
    美元强弱、黄金避险信号综合评分。
    """
    score = 0
    pcts = []
    for _, s in GLOBAL_INDICES:
        r = _row(global_idx, _, )
        if r and r["pct"] is not None:
            pcts.append(r["pct"])
    us_map = {"标普500": "usINX", "纳斯达克": "usIXIC", "道琼斯": "usDJI"}
    us_pcts = []
    for name in ("标普500", "纳斯达克", "道琼斯"):
        q = us_idx.get(us_map[name])
        if q:
            us_pcts.append(q["pct"])
            pcts.append(q["pct"])

    if pcts:
        up = sum(1 for p in pcts if p > 0)
        avg = sum(pcts) / len(pcts)
        ratio = up / len(pcts)
        if ratio >= 0.6:
            score += 1
        elif ratio <= 0.4:
            score -= 1
        if avg >= 0.3:
            score += 1
        elif avg <= -0.3:
            score -= 1
    if us_pcts:
        us_avg = sum(us_pcts) / len(us_pcts)
        if us_avg >= 0.3:
            score += 1
        elif us_avg <= -0.3:
            score -= 1
    usd = next((r for r in fx_rows if r["name"] == "美元指数"), None)
    if usd and usd["pct"] is not None and usd["pct"] <= -0.1:
        score += 1
    elif usd and usd["pct"] is not None and usd["pct"] >= 0.1:
        score -= 1
    if gold and gold["pct"] is not None:
        if gold["pct"] >= 0.5:
            score -= 1  # 黄金大涨常伴随避险
        elif gold["pct"] <= -0.5:
            score += 1  # 黄金大跌常伴随风险偏好回升
    if score >= 2:
        return "risk on（风险偏好回升）——主要股指普涨"
    if score <= -2:
        return "risk off（避险情绪升温）——主要股指普跌、避险资产受青睐"
    if score >= 1:
        return "risk on 偏强（主要股指多数上涨）"
    if score <= -1:
        return "risk off 偏强（主要股指多数下跌）"
    return "中性（风险资产与避险资产涨跌互现）"


def _macro_stage(usd_pct, ief_pct, gold_pct, risk_txt, comm_verdict):
    """当前全球宏观所处阶段（客观推导）。"""
    parts = []
    if usd_pct is not None and usd_pct <= -0.1:
        parts.append("弱美元")
    if ief_pct is not None:
        if ief_pct >= 0.2:
            parts.append("美债走强/收益率下行")
        elif ief_pct <= -0.2:
            parts.append("美债走弱/收益率上行")
    if gold_pct is not None and gold_pct >= 0.3:
        parts.append("黄金走强")
    if "普涨" in risk_txt or "risk on" in risk_txt:
        parts.append("风险偏好回升")
    if "普跌" in risk_txt or "risk off" in risk_txt:
        parts.append("避险情绪升温")

    if ("弱美元" in parts and "收益率下行" in parts and "风险偏好回升" in parts):
        phase = "降息预期升温 / 宽松交易（弱美元+收益率下行+风险偏好回升）"
    elif ("美债走弱" in parts and "黄金走强" in parts and "risk off" in risk_txt):
        phase = "避险交易（美债收益率上行+黄金涨+股指承压）"
    elif ("弱美元" in parts and "黄金走强" in parts and "risk on" in risk_txt):
        phase = "再通胀/风险偏好回升（弱美元+商品涨+股指涨）"
    elif "risk off" in risk_txt:
        phase = "避险/衰退交易（风险资产承压）"
    else:
        phase = "宏观环境相对均衡（方向待数据确认）"
    return phase, "；".join(parts) if parts else "数据不足"


def _linkage(phase, usd, ief, gold, oil, risk_txt):
    """跨资产联动描述 + 核心驱动/矛盾 + 推演。"""
    parts = []
    if usd and usd["pct"] is not None and usd["pct"] <= -0.1 and gold and gold["pct"] is not None:
        parts.append(f"美元走弱（{usd['pct']:+.2f}%）→ 黄金 {gold['pct']:+.2f}%，弱美元利好大宗与新兴资产")
    if usd and usd["pct"] is not None and usd["pct"] >= 0.1 and gold and gold["pct"] is not None:
        parts.append(f"美元走强（{usd['pct']:+.2f}%）→ 黄金 {gold['pct']:+.2f}%，强美元压制商品")
    if ief and ief["pct"] is not None:
        if ief["pct"] >= 0.2:
            parts.append("美债收益率下行 → 支撑成长股估值、利空美元")
        elif ief["pct"] <= -0.2:
            parts.append("美债收益率上行 → 压制高估值成长、支撑美元")
    if oil and oil["pct"] is not None:
        parts.append(f"原油 {oil['pct']:+.2f}% —— 通胀与能源成本锚")
    return "；".join(parts) if parts else "跨资产联动信号暂不显著。"


def _summary(risk_txt, phase, usd, ief, gold):
    usd_t = f"美元指数 {usd['price']}（{usd['pct']:+.2f}%）" if usd and usd["price"] is not None else "美元数据暂缺"
    bond_t = "美债收益率方向以 ETF 近似"
    gold_t = f"黄金 {gold['price']}（{gold['pct']:+.2f}%）" if gold and gold["price"] is not None else "黄金数据暂缺"
    return f"全球宏观：{usd_t}；{gold_t}；{bond_t}；风险偏好：{risk_txt}；宏观阶段：{phase}。"


# ---------- 主函数 ----------

def fetch_globalmac(date=None):
    """全球宏观主函数。date 参数忽略（全部为最新实时/隔夜收盘口径）。"""
    errors = []
    if date:
        errors.append("全球宏观为最新实时/隔夜收盘口径，不支持历史回放（date 参数已忽略）")

    raw = _collect()

    # 全球股指
    global_rows = []
    for name, secid in GLOBAL_INDICES:
        r = _row(raw["global_idx"], name)
        if r:
            global_rows.append(r)
    eu_names = {n for n, _ in EU_INDICES}
    apac_names = {n for n, _ in APAC_INDICES}
    eu_rows = [r for r in global_rows if r["name"] in eu_names]
    apac_rows = [r for r in global_rows if r["name"] in apac_names]
    us_rows = []
    for name, code in US_INDICES:
        q = raw["us_idx"].get(code)
        if q:
            us_rows.append({"name": name, "price": q["price"], "pct": q["pct"],
                            "pre_close": q["pre_close"], "open": q["open"],
                            "high": q["high"], "low": q["low"]})
    a50 = _row(raw["bond_etf"], "富时中国A50")
    if a50:
        a50["note"] = "期货主力合约数据源暂不可得，以现货指数代理"

    # 外汇
    fx_rows = []
    for name, secid, f14_name in FX_EM:
        r = _row(raw["em_fx"], f14_name)
        if r:
            r["name"] = name
            fx_rows.append(r)
    if raw.get("sina_cny"):
        fx_rows.append(raw["sina_cny"])
    fx_verdict = _fx_verdict(fx_rows)

    # 债券
    bonds = _bonds_block(raw.get("bond_etf") or [], raw.get("sina_t0"))

    # 大宗
    comm_rows = []
    for name, secid, unit in COMM_EM:
        r = _row(raw["comm"], name)
        if r:
            r["unit"] = unit
            comm_rows.append(r)
    sina_map = {
        "WTI原油": raw.get("sina_cl"),
        "布伦特原油": raw.get("sina_oil"),
        "LME铜(美元/吨)": raw.get("sina_cad"),
        "碳酸锂主力(元/吨)": raw.get("sina_lc"),
    }
    for name, r in sina_map.items():
        if r:
            comm_rows.append(r)
    comm_verdict = _comm_verdict(comm_rows)

    usd = next((r for r in fx_rows if r["name"] == "美元指数"), None)
    gold = next((r for r in comm_rows if r["name"] == "COMEX黄金"), None)
    oil = next((r for r in comm_rows if r["name"] == "WTI原油"), None)
    ief = next((r for r in bonds["rows"] if "7-10年" in r["name"]), None)

    risk_txt = _risk_appetite(raw["global_idx"], raw["us_idx"], fx_rows, gold)
    phase, phase_parts = _macro_stage(
        usd["pct"] if usd else None,
        ief["pct"] if ief else None,
        gold["pct"] if gold else None,
        risk_txt, comm_verdict,
    )
    linkage = _linkage(phase, usd, ief, gold, oil, risk_txt)

    # 核心驱动 / 矛盾
    drivers = f"资金面：{fx_verdict}；债市：{bonds['verdict']}；商品：{comm_verdict}。"
    contradiction = _contradiction(risk_txt, usd, gold, ief)

    # 宏观日历（如实标注无公开实时接口）
    calendar = {
        "note": "当日宏观数据与央行事件暂无公开实时接口，请以官方公布为准；本页聚焦跨资产行情联动。",
        "focus": "关注未来交易日：美债拍卖、美国初请/PMI 等高频数据、主要央行官员讲话（以官方日历为准）。",
    }

    outlook = _outlook(phase, risk_txt, usd, ief)
    as_of = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = _summary(risk_txt, phase, usd, ief, gold)

    return {
        "as_of": as_of,
        "indices": {
            "a50": a50,
            "us": us_rows,
            "eu": eu_rows,
            "apac": apac_rows,
            "risk": risk_txt,
        },
        "fx": {"rows": fx_rows, "verdict": fx_verdict},
        "bonds": bonds,
        "commodities": {"rows": comm_rows, "verdict": comm_verdict},
        "calendar": calendar,
        "linkage": {
            "phase": phase,
            "phase_parts": phase_parts,
            "drivers": drivers,
            "contradiction": contradiction,
            "linkage": linkage,
            "outlook": outlook,
        },
        "summary": summary,
        "risk": RISK_TEXT,
        "errors": errors,
    }


def _contradiction(risk_txt, usd, gold, ief):
    if "risk on" in risk_txt and gold and gold["pct"] is not None and gold["pct"] >= 0.3:
        return "风险偏好与避险资产同涨（股指涨+黄金涨），市场对「降息交易」与「衰退担忧」并存，方向博弈明显。"
    if "risk off" in risk_txt and ief and ief["pct"] is not None and ief["pct"] >= 0.2:
        return "避险交易：股指承压但美债走强，资金涌入避险资产，核心矛盾在于增长预期与流动性预期的赛跑。"
    if usd and usd["pct"] is not None and ief and ief["pct"] is not None and usd["pct"] >= 0.1 and ief["pct"] <= -0.2:
        return "美元与美债收益率同步上行，压制新兴市场与高估值成长资产。"
    return "多空驱动交织，市场等待新的宏观数据给出方向。"


def _outlook(phase, risk_txt, usd, ief):
    parts = []
    if "降息预期" in phase or "宽松交易" in phase:
        parts.append("降息交易延续则利好黄金/成长估值，但需警惕预期打满后的获利回吐")
    if "risk off" in risk_txt:
        parts.append("避险环境下控制风险敞口，关注美债与黄金的避险承接")
    if "risk on" in risk_txt:
        parts.append("风险偏好回升环境下关注权益与商品的联动持续性")
    parts.append("密切关注美元指数与美债收益率方向的边际变化（当前收益率以 ETF 近似）")
    parts.append("所有判断基于当日行情推导，不构成任何投资建议")
    return "；".join(parts) + "。"
