/* ---------- 通用可排序表格：点击表头排序（三态循环） ----------
 *
 * 用法：
 *   1. 定义表头：const HEADERS = [{key, label, align?}, ...]
 *      - key: 行对象字段名；align: "num" 右对齐
 *   2. 注册：registerSortable(groupId, HEADERS, () => renderXxx(lastData))
 *      - 点击表头后自动调用重渲染回调；同一 groupId 的多张表共享排序状态
 *   3. 渲染：表头用 sortableHead(groupId, HEADERS)，行数据用 sortableRows(groupId, rows)
 *
 * 点击顺序（三态循环）：
 *   第1下 → 从大到小（降序 ▼）
 *   第2下 → 从小到大（升序 ▲）
 *   第3下 → 默认顺序（服务端原始顺序，无箭头）
 *   第4下 → 回到降序……
 * 空值(null/undefined/"")恒排最后；数值按大小、字符串按中文拼音比较。
 */

const groups = new Map();       // groupId -> {key, dir}
const rerenders = new Map();    // groupId -> () => void

export function registerSortable(groupId, headers, renderFn) {
  rerenders.set(groupId, renderFn);
  if (!groups.has(groupId)) {
    groups.set(groupId, { key: null, dir: -1 });
  }
}

export function sortableHead(groupId, headers) {
  const st = groups.get(groupId) || { key: null, dir: -1 };
  return headers.map((h) => {
    const active = st.key === h.key;
    const arrow = active ? (st.dir === 1 ? " ▲" : " ▼") : "";
    return `<th class="sortable ${h.align || ""}${active ? " active" : ""}" data-sort-key="${h.key}" data-sort-group="${groupId}">${h.label}${arrow}</th>`;
  }).join("");
}

function fieldCmp(a, b) {
  const va = (a === null || a === undefined || a === "") ? null : a;
  const vb = (b === null || b === undefined || b === "") ? null : b;
  if (va === null && vb === null) return 0;
  if (va === null) return 1;
  if (vb === null) return -1;
  if (typeof va === "number" && typeof vb === "number") return va - vb;
  return String(va).localeCompare(String(vb), "zh");
}

export function sortableRows(groupId, rows) {
  const st = groups.get(groupId);
  if (!st || !st.key) return rows;
  const key = st.key;
  return [...rows].sort((x, y) => {
    const nx = (x[key] === null || x[key] === undefined || x[key] === "") ? 1 : 0;
    const ny = (y[key] === null || y[key] === undefined || y[key] === "") ? 1 : 0;
    if (nx !== ny) return nx - ny;  // 空值恒排最后，不受方向影响
    return st.dir * fieldCmp(x[key], y[key]);
  });
}

// 全局点击委托：表头排序（三态循环：降序 → 升序 → 默认顺序 → 循环）
document.addEventListener("click", (e) => {
  const th = e.target.closest("th[data-sort-group]");
  if (!th) return;
  const groupId = th.dataset.sortGroup;
  const key = th.dataset.sortKey;
  const st = groups.get(groupId);
  if (!st) return;
  if (st.key !== key) {
    // 切换到新列：第一下 = 从大到小（降序）
    st.key = key;
    st.dir = -1;
  } else if (st.dir === -1) {
    // 同列第二下：从小到大（升序）
    st.dir = 1;
  } else {
    // 同列第三下：恢复默认顺序（服务端原始顺序）
    st.key = null;
    st.dir = -1;
  }
  const fn = rerenders.get(groupId);
  if (fn) fn();
});
