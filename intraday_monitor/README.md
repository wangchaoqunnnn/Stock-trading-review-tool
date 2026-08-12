# 盘中实时监控

- 启动：`powershell -ExecutionPolicy Bypass -File start.ps1`
- 页面：http://127.0.0.1:8765/
- 数据接口：http://127.0.0.1:8765/api/snapshot

功能：自动轮询涨停池、板块涨停数、板块主力净流入、个股量比、首封时间、炸板次数，并按确认条件给出盘中筛选结果。

页面包含两个 tab：盘中监控（实时轮询，保持不变）与复盘筛选（iframe 嵌入 http://127.0.0.1:8787/ 的每日复盘页面）。

停止服务：在任务管理器结束占用 8765 端口的 python 进程，或运行 `Stop-Process -Id <PID>`。
