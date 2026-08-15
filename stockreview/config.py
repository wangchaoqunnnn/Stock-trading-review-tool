# -*- coding: utf-8 -*-
"""全局配置常量。"""
import os

# 仓库根目录（本文件位于 <root>/stockreview/config.py）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(ROOT, "static")

# 请求头与东方财富接口 token
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
EM_UT = "bd1d9ddb04089700cf9c27f6f7426281"
EMEX_UT = "7eea3edcaed734bea9cbfc24409ed989"
# 指数分时接口使用的 token
INDEX_UT = "fa5fd1943c7b386f172d6893dbfba10b"

# 全 A 股（沪深京主板/创业板/科创板）
ALL_A_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"

# 当日快讯关键词过滤
NEWS_KEYWORDS = [
    "A股", "两市", "涨停", "连板", "板块", "资金", "成交", "央行", "政策", "半导体",
    "人工智能", "AI", "机器人", "电力", "新能源", "军工", "航天", "有色", "铜",
    "算力", "华为", "特斯拉", "降息", "加息", "苹果", "英伟达",
]

DEFAULT_PORT = 8787
