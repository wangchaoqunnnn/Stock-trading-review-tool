# -*- coding: utf-8 -*-
"""通用工具函数。"""


def to_num(v):
    """把任意值转为 float，失败返回 NaN（与原始实现行为一致）。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def market_prefix(code):
    """股票代码 -> 行情源交易所前缀（覆盖沪深京全部板块）。

    - 北交所：4xxxxx / 8xxxxx / 92xxxx（含 920xxx 新代码段）
    - 沪市：6xxxxx（主板/科创板 688/689）、9xxxxx（B股 900，排除 92 北交所）
    - 深市：其余（000/001/002/003 主板、300/301 创业板、200 B股）
    注意：必须先判北交所，否则 920xxx 会被 "9" 误判为沪市。
    """
    c = str(code)
    if c.startswith(("4", "8")) or c.startswith("92"):
        return "bj"
    if c.startswith(("6", "9")):
        return "sh"
    return "sz"


# 北交所成交额预筛下限（亿）：北交所流动性天然远低于沪深（中位仅约 0.2 亿），
# 各策略对其使用独立较低门槛，保证北交所股票不被预筛整体滤掉。
BJ_AMOUNT_FLOOR_YI = 0.5


def amount_floor(code, base_yi):
    """成交额预筛下限（亿）：北交所使用独立较低门槛，其余板块用 base_yi。"""
    return BJ_AMOUNT_FLOOR_YI if market_prefix(code) == "bj" else base_yi


def limit_width(code):
    """按板块返回涨跌停幅度（%）：北交所 30、创业板/科创板 20、主板 10。"""
    c = str(code)
    if c.startswith(("4", "8")) or c.startswith("92"):
        return 30.0
    if c.startswith(("3", "68")):
        return 20.0
    return 10.0


def limit_pct(code):
    """涨停判定阈值（%），留少量容差：主板 9.8 / 创业板·科创板 19.5 / 北交所 29.5。"""
    w = limit_width(code)
    return 9.8 if w <= 10.0 else w - 0.5


def big_loss_pct(code):
    """「大面」判定阈值（%）：跌超涨停幅度的 70%（主板 -7 / 创业科创 -14 / 北交所 -21）。"""
    return -limit_width(code) * 0.7


# K 线核对名额中为北交所保留的席位：北交所成交额远低于沪深，
# 若纯按成交额降序截断，北交所个股会被整体挤出核对名单（=整块板块被遗漏）。
BJ_CHECK_QUOTA = 25


def is_bj(code):
    """是否为北交所代码。"""
    return market_prefix(code) == "bj"


def select_candidates(rows, limit, key, bj_quota=BJ_CHECK_QUOTA, code_of=None):
    """按 key 降序截取前 limit 个候选，并为北交所保留 bj_quota 个独立席位。

    北交所流动性低，纯按成交额排序会被沪深个股整体挤出核对名额，
    因此单独保底席位，保证北交所个股同样被逐一核对。返回仍按 key 降序。
    """
    if not rows:
        return []
    get_code = code_of or (lambda r: (r.get("f12") or r.get("code") or ""))
    ordered = sorted(rows, key=key, reverse=True)
    if len(ordered) <= limit:
        return ordered
    bj = [r for r in ordered if is_bj(get_code(r))]
    other = [r for r in ordered if not is_bj(get_code(r))]
    keep_bj = bj[:min(bj_quota, limit)]
    keep_other = other[:max(limit - len(keep_bj), 0)]
    return sorted(keep_bj + keep_other, key=key, reverse=True)
