/* ---------- 回踩支撑（上升趋势回踩5日/10日均线） ---------- */

import { $, esc, fmt, pctClass, signed, apiUrl } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const PMA_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "pct", label: "涨跌幅", align: "num", dir: -1 },
  { key: "price", label: "现价", align: "num", dir: -1 },
  { key: "ma", label: "回踩均线", align: "num", dir: -1 },
  { key: "touch_pct", label: "最低距均线", align: "num", dir: 1 },
  { key: "close_pct", label: "收盘距均线", align: "num", dir: 1 },
  { key: "ma5", label: "MA5", align: "num", dir: -1 },
  { key: "ma10", label: "MA10", align: "num", dir: -1 },
  { key: "ma20", label: "MA20", align: "num", dir: -1 },
  { key: "vol_shrink", label: "量能(今/5日均)", align: "num", dir: 1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
  { key: "industry", label: "板块" },
];

let lastData = null;
registerSortable("pma-ma5", PMA_HEADERS, () => renderPullbackMa(lastData));
registerSortable("pma-ma10", PMA_HEADERS, () => renderPullbackMa(lastData));

function pmaMarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("pmaMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function pmaTable(groupId, rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无符合条件的股票</div>`;
  return `<table><thead><tr>${sortableHead(groupId, PMA_HEADERS)}</tr></thead><tbody>` +
    sortableRows(groupId, rows).map((r) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num">${fmt(r.price)}</td>
      <td class="num">${fmt(r.ma)}</td>
      <td class="num">${fmt(r.touch_pct)}%</td>
      <td class="num">${fmt(r.close_pct)}%</td>
      <td class="num">${fmt(r.ma5)}</td>
      <td class="num">${fmt(r.ma10)}</td>
      <td class="num">${fmt(r.ma20)}</td>
      <td class="num">${r.vol_shrink == null ? "--" : fmt(r.vol_shrink)}</td>
      <td class="num">${fmt(r.vol_ratio)}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
      <td>${esc(r.industry || "--")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderPullbackMa(d) {
  lastData = d;
  pmaMarketChips(d);
  $("pmaSummary").textContent = `预筛 ${d.scanned || 0} 只（涨跌幅-6%~5% + 成交≥2亿）核对K线 · 回踩5日 ${d.ma5?.count || 0} 只 / 回踩10日 ${d.ma10?.count || 0} 只`;
  $("pma5").innerHTML = pmaTable("pma-ma5", d.ma5?.stocks || []);
  $("pma10").innerHTML = pmaTable("pma-ma10", d.ma10?.stocks || []);
  $("pmaState").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadPullbackMa(force = false) {
  $("pmaState").textContent = "更新中...（扫描全A约需1分钟）";
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 180000);
  try {
    const url = apiUrl("/api/pullback_ma", force);
    const resp = await fetch(url, { signal: ctrl.signal });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderPullbackMa(d);
  } catch (e) {
    if (e.name === "AbortError") {
      $("errors").textContent = "回踩支撑扫描超时：数据源（K线）响应慢，请稍后点击「立即刷新」重试";
      $("pmaState").textContent = "扫描超时";
    } else {
      $("errors").textContent = "回踩支撑刷新失败：" + e.message;
      $("pmaState").textContent = "刷新失败";
    }
  } finally {
    clearTimeout(timer);
  }
}
