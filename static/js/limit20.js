/* ---------- 涨停横盘（20日内封涨停 + 横盘震荡/上升趋势） ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";

// 可排序列：key -> {dir: 默认方向}（1=升序，-1=降序）
const SORTABLE = {
  days_since: { dir: 1 },     // 距涨停：近的在前
  pct: { dir: -1 },           // 今日涨跌
  pct_5d: { dir: -1 },        // 近5日涨幅
  ma20: { dir: -1 },
  vol_ratio: { dir: -1 },     // 量比
  amount_yi: { dir: -1 },     // 成交额
  lbc: { dir: -1 },           // 当时连板
  industry: { dir: 1 },       // 板块（拼音）
};

const COMPARATORS = {
  days_since: (a, b) => (a.days_since || 0) - (b.days_since || 0),
  pct: (a, b) => (a.pct ?? -9999) - (b.pct ?? -9999),
  pct_5d: (a, b) => (a.pct_5d ?? -9999) - (b.pct_5d ?? -9999),
  ma20: (a, b) => (a.ma20 || 0) - (b.ma20 || 0),
  vol_ratio: (a, b) => (a.vol_ratio || 0) - (b.vol_ratio || 0),
  amount_yi: (a, b) => (a.amount_yi || 0) - (b.amount_yi || 0),
  lbc: (a, b) => (a.lbc || 0) - (b.lbc || 0),
  industry: (a, b) => String(a.industry || "").localeCompare(String(b.industry || ""), "zh"),
};

let lastData = null;
let sortKey = "amount_yi";
let sortDir = -1;

// 表头可排序列定义：[key, 显示名, 对齐类]
const SORT_HEADERS = [
  ["days_since", "距涨停", "num"],
  ["pct", "今日涨跌", "num"],
  ["pct_5d", "近5日涨幅", "num"],
  ["ma20", "MA20", "num"],
  ["vol_ratio", "量比", "num"],
  ["amount_yi", "成交(亿)", "num"],
  ["lbc", "当时连板", "num"],
  ["industry", "板块", ""],
];

function sortableTh(key, label, align) {
  const arrow = sortKey === key ? (sortDir === 1 ? " ▲" : " ▼") : "";
  const active = sortKey === key ? " active" : "";
  return `<th class="sortable ${align}${active}" data-key="${key}">${label}${arrow}</th>`;
}

function sortRows(rows) {
  const cmp = COMPARATORS[sortKey];
  return [...rows].sort((a, b) => sortDir * cmp(a, b));
}

function l20MarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("l20Market").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function stateTag(s) {
  if (s === "uptrend") return `<span class="alert-tag" style="color:#2fbf71;border-color:#2fbf71;">上升趋势</span>`;
  if (s === "sideways") return `<span class="alert-tag" style="color:#4c8dff;border-color:#4c8dff;">横盘震荡</span>`;
  return `<span class="alert-tag">${esc(s)}</span>`;
}

function l20Table(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无符合条件的个股</div>`;
  const heads = SORT_HEADERS.map(([key, label, align]) => sortableTh(key, label, align)).join("");
  return `<table><thead><tr><th>代码</th><th>名称</th><th>状态</th>${heads}<th>涨停日</th></tr></thead><tbody>` +
    rows.map((r) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td>${stateTag(r.state)}</td>
      <td class="num">${r.days_since || 0}天</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num ${pctClass(r.pct_5d)}">${r.pct_5d == null ? "--" : signed(r.pct_5d)}</td>
      <td class="num">${fmt(r.ma20)}</td>
      <td class="num">${fmt(r.vol_ratio)}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
      <td class="num">${r.lbc ? `${r.lbc}板` : "首板"}</td>
      <td>${esc(r.industry || "--")}</td>
      <td>${esc(r.limit_date)}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderLimit20(d) {
  lastData = d;
  l20MarketChips(d);
  const up = sortRows(d.uptrend_stocks || []);
  const sw = sortRows(d.sideways_stocks || []);
  $("l20Summary").textContent = `统计窗口 ${(d.window_dates || []).length} 个交易日（${(d.window_dates || []).slice(-1)[0] || ""} ~ ${(d.window_dates || [])[0] || ""}）| 20日内封涨停 ${d.universe || 0} 只 → 上升趋势 ${d.uptrend_count || 0} / 横盘震荡 ${d.sideways_count || 0}`;
  $("l20Uptrend").innerHTML = `<div class="subtitle">上升趋势（${d.uptrend_count || 0}）</div>` + l20Table(up);
  $("l20Sideways").innerHTML = `<div class="subtitle">横盘震荡（${d.sideways_count || 0}）</div>` + l20Table(sw);
  $("l20State").textContent = "已更新 " + (d.as_of || "--");
}

// 点击表头排序（事件委托，两个表通用）
document.addEventListener("click", (e) => {
  const th = e.target.closest("th[data-key]");
  if (!th || !lastData) return;
  const key = th.dataset.key;
  if (sortKey === key) {
    sortDir = -sortDir;
  } else {
    sortKey = key;
    sortDir = SORTABLE[key].dir;
  }
  renderLimit20(lastData);
});

export async function loadLimit20(force = false) {
  $("l20State").textContent = "更新中...（扫描全A约需1~2分钟）";
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 180000);
  try {
    const url = force ? "/api/limit20_refresh" : "/api/limit20";
    const resp = await fetch(url, { signal: ctrl.signal });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderLimit20(d);
  } catch (e) {
    if (e.name === "AbortError") {
      $("errors").textContent = "涨停横盘扫描超时：数据源（腾讯/新浪K线）响应慢，请稍后点击「立即刷新」重试";
      $("l20State").textContent = "扫描超时";
    } else {
      $("errors").textContent = "涨停横盘刷新失败：" + e.message;
      $("l20State").textContent = "刷新失败";
    }
  } finally {
    clearTimeout(timer);
  }
}
