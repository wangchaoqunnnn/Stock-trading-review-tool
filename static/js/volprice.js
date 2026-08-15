/* ---------- 量价异动 ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";

function vpBoardChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("vpMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function vpBoardTable(d) {
  const rows = (d.strong_boards || []).slice(0, 8).map((b) => `
    <tr><td>${esc(b.name)}</td><td class="num ${pctClass(b.pct)}">${signed(b.pct)}</td><td class="num ${pctClass(b.flow_yi)}">${signed(b.flow_yi, 2, "")}</td></tr>`).join("");
  $("vpBoards").innerHTML = `<div class="subtitle">板块主力净流入 TOP8</div><table><thead><tr><th>板块</th><th class="num">涨跌</th><th class="num">主力(亿)</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function vpTable(stocks) {
  if (!stocks || !stocks.length) return `<div class="subtitle">暂无</div>`;
  return `<table><thead><tr><th>代码</th><th>名称</th><th class="num">涨跌</th><th class="num">涨速</th><th class="num">量比</th><th class="num">换手</th><th class="num">成交(亿)</th><th class="num">主力(亿)</th><th>板块</th><th class="num">MA20</th><th class="num">5日量比</th><th class="num">20日新高</th><th>信号</th></tr></thead><tbody>` +
    stocks.map((s) => `<tr>
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
  vpBoardChips(d);
  vpBoardTable(d);
  const cats = d.categories || {};
  const order = ["放量上攻", "放量滞涨", "冲高回落", "缩量上涨", "放量下跌", "缩量回踩"];
  let html = `<div class="subtitle">扫描 ${d.total_scanned || 0} 只候选</div>`;
  for (const name of order) {
    const list = cats[name] || [];
    html += `<div class="subtitle">${name}（${list.length}）</div>`;
    html += vpTable(list);
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
