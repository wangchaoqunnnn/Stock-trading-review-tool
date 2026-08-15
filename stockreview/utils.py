# -*- coding: utf-8 -*-
"""通用工具函数。"""


def to_num(v):
    """把任意值转为 float，失败返回 NaN（与原始实现行为一致）。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")
