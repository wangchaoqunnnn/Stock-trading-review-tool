# -*- coding: utf-8 -*-
"""在线结构验证：抓取运行中服务的各端点 JSON，与基线 schema fixture 对比。

用法: python tests/verify_schema.py [base_url]   （默认 http://127.0.0.1:8787）
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_schema import schema_map  # noqa: E402

ENDPOINTS = ["snapshot", "realtime", "volprice", "pullback", "flow3", "trend3", "limit20", "ztpool", "hot", "breakout", "leaders", "heatmap", "emotion_history"]
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fetch(url, timeout=300):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _tolerable(only_base, only_new, diff_type):
    """过滤数据形状导致的假阳性：列表元素级差异（".[]"）与可空字段（null）。"""
    tolerable_base = {k: v for k, v in only_base.items() if ".[]" not in k}
    tolerable_new = {k: v for k, v in only_new.items() if ".[]" not in k}
    tolerable_diff = {k: v for k, v in diff_type.items() if ".[]" not in k and "null" not in v}
    return tolerable_base, tolerable_new, tolerable_diff


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"
    failed = False
    for name in ENDPOINTS:
        fixture_path = os.path.join(FIXTURE_DIR, f"baseline_{name}.json")
        with open(fixture_path, encoding="utf-8") as f:
            expected = json.load(f)
        actual = schema_map(fetch(f"{base}/api/{name}"))
        only_base = {k: v for k, v in expected.items() if k not in actual}
        only_new = {k: v for k, v in actual.items() if k not in expected}
        diff_type = {k: (expected[k], actual[k]) for k in expected if k in actual and expected[k] != actual[k]}
        only_base, only_new, diff_type = _tolerable(only_base, only_new, diff_type)
        if only_base or only_new or diff_type:
            failed = True
            print(f"✗ /api/{name} 结构漂移")
            if only_base:
                print("  仅基线存在:", json.dumps(only_base, ensure_ascii=False)[:500])
            if only_new:
                print("  仅当前存在:", json.dumps(only_new, ensure_ascii=False)[:500])
            if diff_type:
                print("  类型不一致:", json.dumps(diff_type, ensure_ascii=False)[:500])
        else:
            print(f"✓ /api/{name} 与基线结构一致")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
