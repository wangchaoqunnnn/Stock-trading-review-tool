# -*- coding: utf-8 -*-
"""intraday_monitor 等价性测试：git HEAD 的原始 monitor/server.py
与重构版（复用 stockreview 包）在相同离线假数据下输出一致。"""
import importlib.util
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONITOR_DIR = os.path.join(ROOT, "intraday_monitor")
TMP = os.path.join(ROOT, ".refactor_tmp")
sys.path.insert(0, ROOT)


class FakeDT:
    fixed = datetime(2025, 1, 15, 10, 30, 0)

    @classmethod
    def now(cls):
        return cls.fixed


FAKE_POOL = [
    {"c": "600001", "m": 1, "n": "甲科技", "hybk": "半导体", "fbt": 93000, "zbc": 0, "fund": 1.0e8, "ltsz": 2.0e9, "lbc": 2, "zdp": 10.0},
    {"c": "000003", "m": 0, "n": "乙软件", "hybk": "半导体", "fbt": 95000, "zbc": 1, "fund": 5.0e7, "ltsz": 1.0e9, "lbc": 1, "zdp": 9.5},
    {"c": "300004", "m": 0, "n": "丙能源", "hybk": "新能源", "fbt": 102000, "zbc": 0, "fund": 2.0e7, "ltsz": 5.0e8, "lbc": 0, "zdp": 19.9},
]

FAKE_BOARDS = [
    {"f12": "BK01", "f14": "半导体", "f3": 3.2, "f6": 1.0e10, "f8": 2.0, "f10": 1.8, "f17": 101.0, "f18": 100.0, "f62": 8.0e8, "f184": 0.5},
    {"f12": "BK02", "f14": "新能源", "f3": 1.5, "f6": 8.0e9, "f8": 1.6, "f10": 1.2, "f17": 101.5, "f18": 100.0, "f62": 3.0e8, "f184": 0.3},
]

FAKE_BREADTH = {"up": 2500, "down": 1800, "flat": 200}
FAKE_INDEX = [{"name": "上证指数", "pct": 0.33}, {"name": "深证成指", "pct": 0.50}, {"name": "创业板指", "pct": -1.00}]

FAKE_QUOTES = {
    "600001": {"f10": 2.5, "f8": 12.0, "f6": 2.0e9, "f62": 5.0e8},
    "000003": {"f10": 1.2, "f8": 8.0, "f6": 1.5e9, "f62": -2.0e8},
    "300004": {"f10": 0.8, "f8": 15.0, "f6": 1.0e9, "f62": 1.0e8},
}


def deep_equal(a, b, path="root"):
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False, f"{path}: keys differ"
        for k in a:
            ok, msg = deep_equal(a[k], b[k], f"{path}.{k}")
            if not ok:
                return False, msg
        return True, ""
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False, f"{path}: len {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            ok, msg = deep_equal(x, y, f"{path}[{i}]")
            if not ok:
                return False, msg
        return True, ""
    if isinstance(a, float) and isinstance(b, float):
        na, nb = a != a, b != b
        if na or nb:
            return (na == nb), f"{path}: nan 不一致"
        if a != b:
            return False, f"{path}: {a!r} != {b!r}"
        return True, ""
    if a != b:
        return False, f"{path}: {a!r} != {b!r}"
    return True, ""


def load_module_from_git(path, name, out_name):
    out_path = os.path.join(TMP, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        subprocess.run(
            ["git", "show", f"HEAD:{path}"], cwd=ROOT,
            stdout=f, stderr=subprocess.PIPE, check=True,
        )
    spec = importlib.util.spec_from_file_location(name, out_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def patch(mod):
    mod.fetch_zt_pool = lambda date: [dict(x) for x in FAKE_POOL]
    mod.fetch_paged = lambda fs, fields, pz=100, fid="f3": [dict(x) for x in FAKE_BOARDS]
    mod.fetch_breadth = lambda date: dict(FAKE_BREADTH)
    mod.fetch_index = lambda: [dict(x) for x in FAKE_INDEX]
    mod.fetch_quotes = lambda pool: {k: dict(v) for k, v in FAKE_QUOTES.items()}
    mod.datetime = FakeDT


def main():
    print("== 加载原始 intraday_monitor/server.py（git HEAD）==")
    orig = load_module_from_git("intraday_monitor/server.py", "orig_monitor", "orig_monitor.py")
    print("== 加载重构版 intraday_monitor/server.py ==")
    # 重构版直接从工作区加载（import 时会执行 sys.path 注入并导入 stockreview）
    new_path = os.path.join(MONITOR_DIR, "server.py")
    spec = importlib.util.spec_from_file_location("new_monitor", new_path)
    new = importlib.util.module_from_spec(spec)
    sys.modules["new_monitor"] = new
    spec.loader.exec_module(new)

    patch(orig)
    patch(new)

    a = orig.build_snapshot()
    b = new.build_snapshot()
    ok, msg = deep_equal(a, b)
    if not ok:
        raise AssertionError(f"monitor build_snapshot 不一致: {msg}")
    print("  ✓ build_snapshot 输出完全一致")
    print("  样例: total =", a["total"], ", sectors =", len(a["sectors"]), ", stocks =", len(a["stocks"]))
    print("\nmonitor 等价性断言通过 ✔")


if __name__ == "__main__":
    main()
