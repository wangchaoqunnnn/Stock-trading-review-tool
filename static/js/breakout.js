/* ---------- 突破新高（突破短期高点 / 突破历史高点） ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const BO_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "pct", label: "涨跌幅", align: "num", dir: -1 },
  { key: "price", label: "现价", align: "num", dir: -1 },
  { key: "break_pct", label: "突破幅度", align: "num", dir: -1 },
  { key: "prev_high", label: "前高", align: "num", dir: -1 },
  { key: "vol_wan", label: "量(万手)", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
  { key: "industry", label: "板块" },
];

let lastData = null;
registerSortable("bo-short", BO_HEADERS, () => renderBreakout(lastData));
registerSortable("bo-hist", BO_HEADERS, () => renderBreakout(lastData));

function boMarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("boMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function boTable(groupId, rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  return `<table><thead><tr>${sortableHead(groupId, BO_HEADERS)}</tr></thead><tbody>` +
    sortableRows(groupId, rows).map((r) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num">${fmt(r.price)}</td>
      <td class="num up">+${fmt(r.break_pct)}%</td>
      <td class="num">${fmt(r.prev_high)}</td>
      <td class="num">${r.vol_wan == null ? "--" : fmt(r.vol_wan, 0)}</td>
      <td class="num">${r.vol_ratio == null ? "--" : fmt(r.vol_ratio)}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
      <td>${esc(r.industry || "--")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderBreakout(d) {
  lastData = d;
  boMarketChips(d);
  const scanned = d.scanned || 0;
  $("boSummary").textContent = `全A预筛 ${scanned} 只（今日上涨 + 成交≥2亿）核对长周期K线；短期窗口 ${d.short_window || 20} 日，历史窗口约 ${d.hist_window || 250} 交易日（以可得数据为准）`;
  $("boShortWindow").textContent = `近${d.short_window || 20}日新高 · ${d.short?.count || 0} 只`;
  $("boShort").innerHTML = boTable("bo-short", d.short?.stocks || []);
  $("boHistWindow").textContent = `可得历史（约${d.hist_window || 250}交易日）新高 · ${d.hist?.count || 0} 只`;
  $("boHist").innerHTML = boTable("bo-hist", d.hist?.stocks || []);
  $("boState").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadBreakout(force = false) {
  $("boState").textContent = "更新中...（扫描全A约需1~2分钟）";
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 180000);
  try {
    const url = force ? "/api/breakout_refresh" : "/api/breakout";
    const resp = await fetch(url, { signal: ctrl.signal });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderBreakout(d);
  } catch (e) {
    if (e.name === "AbortError") {
      $("errors").textContent = "突破新高扫描超时：数据源（K线）响应慢，请稍后点击「立即刷新」重试";
      $("boState").textContent = "扫描超时";
    } else {
      $("errors").textContent = "突破新高刷新失败：" + e.message;
      $("boState").textContent = "刷新失败";
    }
  } finally {
    clearTimeout(timer);
  }
}
