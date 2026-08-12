@echo off
cd /d "%~dp0"
echo 正在启动 A股每日复盘服务...
start "" http://127.0.0.1:8787
"C:\Users\HUAWEI\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" server.py
pause
