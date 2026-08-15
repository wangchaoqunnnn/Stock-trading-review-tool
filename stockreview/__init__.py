# -*- coding: utf-8 -*-
"""A股每日复盘工具后端包。

重构说明：原 server.py 单文件（1200+ 行）按职责拆分为：

- config     全局配置常量
- utils      通用数值工具
- net        东方财富 HTTP 请求与分页抓取
- em         东方财富数据抓取（指数/涨跌分布/涨停池/板块/资金/快讯/K线）
- analysis   纯计算逻辑（情绪指标/信号检查表/观察池/时间窗口等）
- realtime   实时盘口聚合
- volprice   量价异动扫描
- pullback   涨停回踩扫描
- snapshot   每日复盘快照聚合
- cache      TTL 缓存

对外 HTTP 服务与 API 路由保持不变，见仓库根目录 server.py。
"""

__version__ = "2.0.0"
