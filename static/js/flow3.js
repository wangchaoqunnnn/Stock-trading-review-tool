/* ---------- 3日资金（连续净流入/流出） ---------- */

import { $, esc, fmt, pctClass, signed, apiUrl } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const F3_BOARD_HEADERS = [
  { key: "name", label: "板块" },
  { key: "days", label: "连续天数", align: "num", dir: -1 },
  { key: "streak_flow_yi", label: "累计净流入(亿)", align: "num", dir: -1 },
  { key: "today_flow_yi", label: "今日净流入(亿)", align: "num", dir: -1 },
  { key: "pct", label: "今日涨跌", align: "num", dir: -1 },
];
const F3_STOCK_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "days", label: "连续天数", align: "num", dir: -1 },
  { key: "streak_flow_yi", label: "累计净流入(亿)", align: "num", dir: -1 },
  { key: "flow_yi", label: "今日净流入(亿)", align: "num", dir: -1 },
  { key: "pct", label: "今日涨跌", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "industry", label: "板块" },
];

let lastData = null;
registerSortable("f3-in", F3_BOARD_HEADERS, () => renderFlow3(lastData));
registerSortable("f3-out", F3_BOARD_HEADERS, () => renderFlow3(lastData));
registerSortable("f3-stocks", F3_STOCK_HEADERS, () => renderFlow3(lastData));

function f3MarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("f3Market").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function f3BoardTable(groupId, rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无符合条件的板块</div>`;
  return `<table><thead><tr>${sortableHead(groupId, F3_BOARD_HEADERS)}</tr></thead><tbody>` +
    sortableRows(groupId, rows).map((r) => `<tr>
      <td>${esc(r.name)}</td>
      <td class="num"><b>${r.days}天</b></td>
      <td class="num ${pctClass(r.streak_flow_yi)}">${signed(r.streak_flow_yi, 2, "")}</td>
      <td class="num ${pctClass(r.today_flow_yi)}">${signed(r.today_flow_yi, 2, "")}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function f3StockTable(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无符合条件的个股</div>`;
  return `<table><thead><tr>${sortableHead("f3-stocks", F3_STOCK_HEADERS)}</tr></thead><tbody>` +
    sortableRows("f3-stocks", rows).map((r) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td class="num"><b>${r.days}天</b></td>
      <td class="num ${pctClass(r.streak_flow_yi)}">${signed(r.streak_flow_yi, 2, "")}</td>
      <td class="num ${pctClass(r.flow_yi)}">${signed(r.flow_yi, 2, "")}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
      <td class="num">${fmt(r.vol_ratio)}</td>
      <td>${esc(r.industry || "--")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderFlow3(d) {
  lastData = d;
  f3MarketChips(d);
  const boards = (d.inflow_boards || []).length;
  const out = (d.outflow_boards || []).length;
  const stocks = (d.inflow_stocks || []).length;
  $("f3Summary").textContent = `扫描板块 ${d.scanned_boards || 0} 个：净流入 ${boards} 个 / 净流出 ${out} 个；个股预筛 ${d.scanned_stocks || 0} 只，连续净流入命中 ${stocks} 只`;
  $("f3InflowBoards").innerHTML = f3BoardTable("f3-in", d.inflow_boards || []);
  $("f3OutflowBoards").innerHTML = f3BoardTable("f3-out", d.outflow_boards || []);
  $("f3InflowStocks").innerHTML = f3StockTable(d.inflow_stocks || []);
  $("f3State").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadFlow3(force = false) {
  $("f3State").textContent = "更新中...";
  try {
    const url = apiUrl("/api/flow3", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderFlow3(d);
  } catch (e) {
    $("errors").textContent = "3日资金刷新失败：" + e.message;
    $("f3State").textContent = "刷新失败";
  }
}
