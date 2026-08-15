# -*- coding: utf-8 -*-
"""结构对比：比较基线 JSON 与重构后 JSON 的键路径 + 值类型是否一致。

忽略具体数值与列表长度（行情数据随时间变化），只关注结构是否漂移。
用法: python tests/compare_schema.py <base.json> <new.json>
"""
import json
import sys


def typename(v):
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        # JSON 数字的 int/float 属于同一结构类型（0 与 0.0 不视为漂移）
        return "num"
    if isinstance(v, str):
        return "str"
    if isinstance(v, dict):
        return "dict"
    if isinstance(v, list):
        return "list"
    if v is None:
        return "null"
    return type(v).__name__


def schema_map(obj, prefix="root", out=None):
    """递归收集 路径 -> 类型 映射；列表以首元素为代表性元素。"""
    if out is None:
        out = {}
    if isinstance(obj, dict):
        out[prefix] = "dict"
        for k, v in obj.items():
            p = f"{prefix}.{k}"
            out[p] = typename(v)
            schema_map(v, p, out)
    elif isinstance(obj, list):
        out[prefix] = "list"
        if obj:
            # 记录 dict 元素的键集合，避免"元素 0 恰好缺某个键"漏检
            keys_union = set()
            kinds = set()
            for x in obj:
                if isinstance(x, dict):
                    keys_union |= set(x.keys())
                kinds.add(typename(x))
            out[prefix + ".[].keys"] = ",".join(sorted(keys_union))
            out[prefix + ".[].kinds"] = ",".join(sorted(kinds))
            schema_map(obj[0], prefix + ".[]", out)
    else:
        out[prefix] = typename(obj)
    return out


def main():
    base_path, new_path = sys.argv[1], sys.argv[2]
    with open(base_path, encoding="utf-8") as f:
        base = json.load(f)
    with open(new_path, encoding="utf-8") as f:
        new = json.load(f)
    bm = schema_map(base)
    nm = schema_map(new)
    only_base = {k: v for k, v in bm.items() if k not in nm}
    only_new = {k: v for k, v in nm.items() if k not in bm}
    diff_type = {k: (bm[k], nm[k]) for k in bm if k in nm and bm[k] != nm[k]}
    if only_base:
        print("仅基线存在:", json.dumps(only_base, ensure_ascii=False, indent=1))
    if only_new:
        print("仅新版本存在:", json.dumps(only_new, ensure_ascii=False, indent=1))
    if diff_type:
        print("类型不一致:", json.dumps(diff_type, ensure_ascii=False, indent=1))
    if not (only_base or only_new or diff_type):
        print(f"✓ 结构一致: {base_path.split(chr(92))[-1]} vs {new_path.split(chr(92))[-1]}")
        return 0
    print(f"✗ 结构存在差异: {base_path} vs {new_path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
