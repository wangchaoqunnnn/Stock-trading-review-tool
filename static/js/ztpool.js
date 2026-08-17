/* ---------- 今日涨停（涨停/炸板/跌停/最高板/竞价涨停） ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";

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

function zpTable(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  return `<table><thead><tr><th>代码</th><th>名称</th><th>板块</th><th class="num">涨跌</th><th class="num">连板</th><th>首封</th><th class="num">炸板</th><th class="num">量(万手)</th><th class="num">量比</th><th class="num">成交(亿)</th><th class="num">换手</th></tr></thead><tbody>` +
    rows.map((r) => `<tr>
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
  zpMarketChips(d);
  $("zpZtCount").textContent = `共 ${d.zt?.count || 0} 只`;
  $("zpZt").innerHTML = zpTable(d.zt?.stocks || []);
  $("zpZbCount").textContent = `共 ${d.zb?.count || 0} 只`;
  $("zpZb").innerHTML = zpTable(d.zb?.stocks || []);
  $("zpDtCount").textContent = `共 ${d.dt?.count || 0} 只`;
  $("zpDt").innerHTML = zpTable(d.dt?.stocks || []);
  $("zpMaxCount").textContent = `最高 ${d.max_board?.max_lb || 0} 板 · ${d.max_board?.count || 0} 只`;
  $("zpMax").innerHTML = zpTable(d.max_board?.stocks || []);
  $("zpJjCount").textContent = `共 ${d.jingjia?.count || 0} 只`;
  $("zpJj").innerHTML = zpTable(d.jingjia?.stocks || []);
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
