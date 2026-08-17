/* ---------- 涨停回踩 ---------- */

import { $, esc, fmt, pctClass, signed, apiUrl } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const PB_BOARD_HEADERS = [
  { key: "name", label: "板块" },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "flow_yi", label: "主力(亿)", align: "num", dir: -1 },
];
const PB_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "price", label: "现价", align: "num", dir: -1 },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "hist_vol_ratio", label: "5日量比", align: "num", dir: -1 },
  { key: "turnover", label: "换手", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
  { key: "main_flow", label: "主力(亿)", align: "num", dir: -1 },
  { key: "industry", label: "板块" },
  { key: "ma20", label: "MA20", align: "num", dir: -1 },
  { key: "limit_date", label: "涨停日" },
  { key: "limit_pct", label: "涨停涨幅", align: "num", dir: -1 },
  { key: "days_since", label: "距涨停", align: "num", dir: 1 },
  { key: "score", label: "评分", align: "num", dir: -1 },
  { key: "tags", label: "信号" },
];

let lastData = null;
registerSortable("pb-boards", PB_BOARD_HEADERS, () => renderPullback(lastData));
registerSortable("pb-list", PB_HEADERS, () => renderPullback(lastData));

function pbMarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("pbMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function pbBoardTable(d) {
  const rows = sortableRows("pb-boards", (d.hot_boards || []).slice(0, 8)).map((b) => `
    <tr><td>${esc(b.name)}</td><td class="num ${pctClass(b.pct)}">${signed(b.pct)}</td><td class="num ${pctClass(b.flow_yi)}">${signed(b.flow_yi, 2, "")}</td></tr>`).join("");
  $("pbBoards").innerHTML = `<div class="subtitle">热点板块主力净流入 TOP8</div><table><thead><tr>${sortableHead("pb-boards", PB_BOARD_HEADERS)}</tr></thead><tbody>${rows}</tbody></table>`;
}

function pbTable(stocks) {
  if (!stocks || !stocks.length) return `<div class="subtitle">暂无符合条件的股票</div>`;
  return `<table><thead><tr>${sortableHead("pb-list", PB_HEADERS)}</tr></thead><tbody>` +
    sortableRows("pb-list", stocks).map((s) => `<tr>
      <td>${esc(s.code)}</td><td>${esc(s.name)}</td>
      <td class="num">${fmt(s.price)}</td>
      <td class="num ${pctClass(s.pct)}">${signed(s.pct)}</td>
      <td class="num">${fmt(s.vol_ratio)}</td>
      <td class="num">${s.hist_vol_ratio == null ? "--" : fmt(s.hist_vol_ratio)}</td>
      <td class="num">${fmt(s.turnover)}%</td>
      <td class="num">${fmt(s.amount_yi)}</td>
      <td class="num ${pctClass(s.main_flow)}">${signed(s.main_flow, 2, "")}</td>
      <td>${esc(s.industry || "--")}</td>
      <td class="num">${fmt(s.ma20)}</td>
      <td>${esc(s.limit_date || "--")}</td>
      <td class="num up">${signed(s.limit_pct)}</td>
      <td class="num">${s.days_since || "--"}天</td>
      <td class="num">${fmt(s.score, 1)}</td>
      <td>${(s.tags || []).map((t) => `<span class="alert-tag">${esc(t)}</span>`).join("")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderPullback(d) {
  lastData = d;
  pbMarketChips(d);
  pbBoardTable(d);
  $("pbSummary").textContent = `扫描 ${d.scanned || 0} 只候选，命中 ${d.matched || 0} 只`;
  $("pbList").innerHTML = pbTable(d.stocks || []);
  $("pbState").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadPullback(force = false) {
  $("pbState").textContent = "更新中...";
  try {
    const url = apiUrl("/api/pullback", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderPullback(d);
  } catch (e) {
    $("errors").textContent = "涨停回踩刷新失败：" + e.message;
    $("pbState").textContent = "刷新失败";
  }
}
