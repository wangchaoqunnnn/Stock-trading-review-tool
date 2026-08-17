/* ---------- 今日涨停（涨停/炸板/跌停/最高板/竞价涨停） ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const ZP_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "industry", label: "板块" },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "lbc", label: "连板", align: "num", dir: -1 },
  { key: "fbt", label: "首封" },
  { key: "zbc", label: "炸板", align: "num", dir: -1 },
  { key: "vol_wan", label: "量(万手)", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
  { key: "turnover", label: "换手", align: "num", dir: -1 },
];

let lastData = null;
for (const id of ["zp-zt", "zp-zb", "zp-dt", "zp-max", "zp-jj"]) {
  registerSortable(id, ZP_HEADERS, () => renderZtpool(lastData));
}

function zpMarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("zpMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function fmtFbt(v) {
  if (!v) return "--";
  const s = String(v).padStart(6, "0");
  return s.slice(0, 2) + ":" + s.slice(2, 4);
}

function zpTable(groupId, rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  return `<table><thead><tr>${sortableHead(groupId, ZP_HEADERS)}</tr></thead><tbody>` +
    sortableRows(groupId, rows).map((r) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td>${esc(r.industry || "--")}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num">${r.lbc ? `<span class="badge lb">${r.lbc}板</span>` : "--"}</td>
      <td>${fmtFbt(r.fbt)}</td>
      <td class="num">${r.zbc || "--"}</td>
      <td class="num">${r.vol_wan == null ? "--" : fmt(r.vol_wan, 0)}</td>
      <td class="num">${r.vol_ratio == null ? "--" : fmt(r.vol_ratio)}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
      <td class="num">${r.turnover == null ? "--" : fmt(r.turnover)}%</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderZtpool(d) {
  lastData = d;
  zpMarketChips(d);
  $("zpZtCount").textContent = `共 ${d.zt?.count || 0} 只`;
  $("zpZt").innerHTML = zpTable("zp-zt", d.zt?.stocks || []);
  $("zpZbCount").textContent = `共 ${d.zb?.count || 0} 只`;
  $("zpZb").innerHTML = zpTable("zp-zb", d.zb?.stocks || []);
  $("zpDtCount").textContent = `共 ${d.dt?.count || 0} 只`;
  $("zpDt").innerHTML = zpTable("zp-dt", d.dt?.stocks || []);
  $("zpMaxCount").textContent = `最高 ${d.max_board?.max_lb || 0} 板 · ${d.max_board?.count || 0} 只`;
  $("zpMax").innerHTML = zpTable("zp-max", d.max_board?.stocks || []);
  $("zpJjCount").textContent = `共 ${d.jingjia?.count || 0} 只`;
  $("zpJj").innerHTML = zpTable("zp-jj", d.jingjia?.stocks || []);
  $("zpState").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadZtpool(force = false) {
  $("zpState").textContent = "更新中...";
  try {
    const url = force ? "/api/ztpool_refresh" : "/api/ztpool";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderZtpool(d);
  } catch (e) {
    $("errors").textContent = "今日涨停刷新失败：" + e.message;
    $("zpState").textContent = "刷新失败";
  }
}
