/* ---------- 放量阳线（3日+ 连续小幅放量阳线、上升趋势） ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";

function t3MarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("t3Market").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function t3StockTable(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无符合条件的个股</div>`;
  return `<table><thead><tr><th>代码</th><th>名称</th><th class="num">连续阳线</th><th class="num">今日涨跌</th><th class="num">量比</th><th class="num">近5日涨幅</th><th class="num">MA20</th><th class="num">成交(亿)</th><th class="num">换手</th><th>板块</th></tr></thead><tbody>` +
    rows.map((r) => `<tr>
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
  return `<table><thead><tr><th>板块</th><th class="num">连续阳线</th><th class="num">今日涨跌</th><th class="num">量比</th><th class="num">近5日涨幅</th><th class="num">MA20</th><th class="num">今日主力(亿)</th></tr></thead><tbody>` +
    rows.map((r) => `<tr>
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
  t3MarketChips(d);
  $("t3Summary").textContent = `个股预筛 ${d.scanned_stocks || 0} 只，命中 ${(d.stocks || []).length} 只；板块预筛 ${d.scanned_boards || 0} 个，命中 ${(d.boards || []).length} 个`;
  $("t3Stocks").innerHTML = t3StockTable(d.stocks || []);
  $("t3Boards").innerHTML = t3BoardTable(d.boards || []);
  $("t3State").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadTrend3(force = false) {
  $("t3State").textContent = "更新中...";
  try {
    const url = force ? "/api/trend3_refresh" : "/api/trend3";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderTrend3(d);
  } catch (e) {
    $("errors").textContent = "放量阳线刷新失败：" + e.message;
    $("t3State").textContent = "刷新失败";
  }
}
