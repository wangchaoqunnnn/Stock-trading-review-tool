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
