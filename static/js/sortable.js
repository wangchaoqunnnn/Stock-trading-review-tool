/* ---------- 通用可排序表格：点击表头排序 ----------
 *
 * 用法：
 *   1. 定义表头：const HEADERS = [{key, label, align?, dir?}, ...]
 *      - key: 行对象字段名；align: "num" 右对齐；dir: 该列默认方向(1升/-1降)
 *   2. 注册：registerSortable(groupId, HEADERS, () => renderXxx(lastData))
 *      - 点击表头后自动调用重渲染回调；同一 groupId 的多张表共享排序状态
 *   3. 渲染：表头用 sortableHead(groupId, HEADERS)，行数据用 sortableRows(groupId, rows)
 *
 * 行为：首次点击按该列默认方向排序，再次点击同列切换升/降序；
 * 当前排序列高亮并显示 ▲/▼；空值(null/undefined/"")统一排最后；
 * 数值按大小、字符串按中文拼音比较。
 */

const groups = new Map();       // groupId -> {key, dir, defaultDir}
const headersOf = new Map();    // groupId -> headers
const rerenders = new Map();    // groupId -> () => void

export function registerSortable(groupId, headers, renderFn) {
  headersOf.set(groupId, headers);
  rerenders.set(groupId, renderFn);
  if (!groups.has(groupId)) {
    groups.set(groupId, { key: null, dir: -1, defaultDir: -1 });
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

// 全局点击委托：表头排序
document.addEventListener("click", (e) => {
  const th = e.target.closest("th[data-sort-group]");
  if (!th) return;
  const groupId = th.dataset.sortGroup;
  const key = th.dataset.sortKey;
  const st = groups.get(groupId);
  if (!st) return;
  if (st.key === key) {
    st.dir = -st.dir;
  } else {
    const def = (headersOf.get(groupId) || []).find((h) => h.key === key) || {};
    st.key = key;
    st.dir = def.dir || 1;  // 未显式指定方向的列默认升序（字符串/日期/代码列更自然）
  }
  const fn = rerenders.get(groupId);
  if (fn) fn();
});
