/* ---------- 放量阳线（3日+ 连续小幅放量阳线、上升趋势） ---------- */

import { $, esc, fmt, pctClass, signed, apiUrl } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const T3_STOCK_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "days", label: "连续阳线", align: "num", dir: -1 },
  { key: "pct", label: "今日涨跌", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "pct_5d", label: "近5日涨幅", align: "num", dir: -1 },
  { key: "ma20", label: "MA20", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
  { key: "turnover", label: "换手", align: "num", dir: -1 },
  { key: "industry", label: "板块" },
];
const T3_BOARD_HEADERS = [
  { key: "name", label: "板块" },
  { key: "days", label: "连续阳线", align: "num", dir: -1 },
  { key: "pct", label: "今日涨跌", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "pct_5d", label: "近5日涨幅", align: "num", dir: -1 },
  { key: "ma20", label: "MA20", align: "num", dir: -1 },
  { key: "flow_yi", label: "今日主力(亿)", align: "num", dir: -1 },
];

let lastData = null;
registerSortable("t3-stocks", T3_STOCK_HEADERS, () => renderTrend3(lastData));
registerSortable("t3-boards", T3_BOARD_HEADERS, () => renderTrend3(lastData));

function t3MarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("t3Market").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function t3StockTable(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无符合条件的个股</div>`;
  return `<table><thead><tr>${sortableHead("t3-stocks", T3_STOCK_HEADERS)}</tr></thead><tbody>` +
    sortableRows("t3-stocks", rows).map((r) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td class="num"><b>${r.days}天</b></td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num">${fmt(r.vol_ratio)}</td>
      <td class="num ${pctClass(r.pct_5d)}">${r.pct_5d == null ? "--" : signed(r.pct_5d)}</td>
      <td class="num">${fmt(r.ma20)}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
      <td class="num">${fmt(r.turnover)}%</td>
      <td>${esc(r.industry || "--")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function t3BoardTable(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无符合条件的板块</div>`;
  return `<table><thead><tr>${sortableHead("t3-boards", T3_BOARD_HEADERS)}</tr></thead><tbody>` +
    sortableRows("t3-boards", rows).map((r) => `<tr>
      <td>${esc(r.name)}</td>
      <td class="num"><b>${r.days}天</b></td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num">${fmt(r.vol_ratio)}</td>
      <td class="num ${pctClass(r.pct_5d)}">${r.pct_5d == null ? "--" : signed(r.pct_5d)}</td>
      <td class="num">${fmt(r.ma20)}</td>
      <td class="num ${pctClass(r.flow_yi)}">${signed(r.flow_yi, 2, "")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderTrend3(d) {
  lastData = d;
  t3MarketChips(d);
  $("t3Summary").textContent = `个股预筛 ${d.scanned_stocks || 0} 只，命中 ${(d.stocks || []).length} 只；板块预筛 ${d.scanned_boards || 0} 个，命中 ${(d.boards || []).length} 个`;
  $("t3Stocks").innerHTML = t3StockTable(d.stocks || []);
  $("t3Boards").innerHTML = t3BoardTable(d.boards || []);
  $("t3State").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadTrend3(force = false) {
  $("t3State").textContent = "更新中...";
  try {
    const url = apiUrl("/api/trend3", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderTrend3(d);
  } catch (e) {
    $("errors").textContent = "放量阳线刷新失败：" + e.message;
    $("t3State").textContent = "刷新失败";
  }
}
