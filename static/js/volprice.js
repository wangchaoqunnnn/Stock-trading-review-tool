/* ---------- 量价异动 ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const VP_BOARD_HEADERS = [
  { key: "name", label: "板块" },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "flow_yi", label: "主力(亿)", align: "num", dir: -1 },
];
const VP_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "speed", label: "涨速", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "turnover", label: "换手", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
  { key: "main_flow", label: "主力(亿)", align: "num", dir: -1 },
  { key: "industry", label: "板块" },
  { key: "ma20", label: "MA20", align: "num", dir: -1 },
  { key: "hist_vol_ratio", label: "5日量比", align: "num", dir: -1 },
  { key: "break_high20", label: "20日新高" },
  { key: "tags", label: "信号" },
];

let lastData = null;
registerSortable("vp-boards", VP_BOARD_HEADERS, () => renderVolPrice(lastData));
for (const name of ["放量上攻", "放量滞涨", "冲高回落", "缩量上涨", "放量下跌", "缩量回踩"]) {
  registerSortable(`vp-${name}`, VP_HEADERS, () => renderVolPrice(lastData));
}

function vpBoardChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("vpMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function vpBoardTable(d) {
  const rows = sortableRows("vp-boards", (d.strong_boards || []).slice(0, 8)).map((b) => `
    <tr><td>${esc(b.name)}</td><td class="num ${pctClass(b.pct)}">${signed(b.pct)}</td><td class="num ${pctClass(b.flow_yi)}">${signed(b.flow_yi, 2, "")}</td></tr>`).join("");
  $("vpBoards").innerHTML = `<div class="subtitle">板块主力净流入 TOP8</div><table><thead><tr>${sortableHead("vp-boards", VP_BOARD_HEADERS)}</tr></thead><tbody>${rows}</tbody></table>`;
}

function vpTable(groupId, stocks) {
  if (!stocks || !stocks.length) return `<div class="subtitle">暂无</div>`;
  return `<table><thead><tr>${sortableHead(groupId, VP_HEADERS)}</tr></thead><tbody>` +
    sortableRows(groupId, stocks).map((s) => `<tr>
      <td>${esc(s.code)}</td><td>${esc(s.name)}</td>
      <td class="num ${pctClass(s.pct)}">${signed(s.pct)}</td>
      <td class="num ${pctClass(s.speed)}">${signed(s.speed)}</td>
      <td class="num">${fmt(s.vol_ratio)}</td>
      <td class="num">${fmt(s.turnover)}%</td>
      <td class="num">${fmt(s.amount_yi)}</td>
      <td class="num ${pctClass(s.main_flow)}">${signed(s.main_flow, 2, "")}</td>
      <td>${esc(s.industry || "--")}</td>
      <td class="num">${s.ma20 ? fmt(s.ma20) : "--"}</td>
      <td class="num">${s.hist_vol_ratio == null ? "--" : fmt(s.hist_vol_ratio)}</td>
      <td class="num">${s.break_high20 == null ? "--" : (s.break_high20 ? "是" : "否")}</td>
      <td>${(s.tags || []).map((t) => `<span class="alert-tag">${esc(t)}</span>`).join("")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderVolPrice(d) {
  lastData = d;
  vpBoardChips(d);
  vpBoardTable(d);
  const cats = d.categories || {};
  const order = ["放量上攻", "放量滞涨", "冲高回落", "缩量上涨", "放量下跌", "缩量回踩"];
  let html = `<div class="subtitle">扫描 ${d.total_scanned || 0} 只候选</div>`;
  for (const name of order) {
    const list = cats[name] || [];
    html += `<div class="subtitle">${name}（${list.length}）</div>`;
    html += vpTable(`vp-${name}`, list);
  }
  $("vpCategories").innerHTML = html;
  $("vpState").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadVolPrice(force = false) {
  $("vpState").textContent = "更新中...";
  try {
    const url = force ? "/api/volprice_refresh" : "/api/volprice";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderVolPrice(d);
  } catch (e) {
    $("errors").textContent = "量价异动刷新失败：" + e.message;
    $("vpState").textContent = "刷新失败";
  }
}
