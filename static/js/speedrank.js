/* ---------- 涨速榜（3分钟/5分钟涨速 TOP100） ---------- */

import { $, esc, fmt, pctClass, signed, apiUrl } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const SR_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "speed3", label: "3分钟涨速", align: "num", dir: -1 },
  { key: "speed5", label: "5分钟涨速", align: "num", dir: -1 },
  { key: "speed", label: "即时涨速", align: "num", dir: -1 },
  { key: "pct", label: "涨跌幅", align: "num", dir: -1 },
  { key: "price", label: "现价", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
  { key: "turnover", label: "换手", align: "num", dir: -1 },
  { key: "industry", label: "板块" },
];

let lastData = null;
registerSortable("sr-list", SR_HEADERS, () => renderSpeedRank(lastData));

function srMarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("srMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function srTable(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据（非交易时段或数据源不可达）</div>`;
  return `<table><thead><tr>${sortableHead("sr-list", SR_HEADERS)}</tr></thead><tbody>` +
    sortableRows("sr-list", rows).map((r, i) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.speed3)}">${r.speed3 == null ? "--" : signed(r.speed3)}</td>
      <td class="num ${pctClass(r.speed5)}">${r.speed5 == null ? "--" : signed(r.speed5)}</td>
      <td class="num ${pctClass(r.speed)}">${signed(r.speed)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num">${fmt(r.price)}</td>
      <td class="num">${fmt(r.vol_ratio)}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
      <td class="num">${fmt(r.turnover)}%</td>
      <td>${esc(r.industry || "--")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderSpeedRank(d) {
  lastData = d;
  srMarketChips(d);
  $("srSummary").textContent = `共 ${(d.stocks || []).length} 只 · 按3分钟涨速降序 · 更新 ${d.as_of || "--"}`;
  $("srList").innerHTML = srTable(d.stocks || []);
  $("srState").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadSpeedRank(force = false) {
  $("srState").textContent = "更新中...";
  try {
    const url = apiUrl("/api/speedrank", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderSpeedRank(d);
  } catch (e) {
    $("errors").textContent = "涨速榜刷新失败：" + e.message;
    $("srState").textContent = "刷新失败";
  }
}
