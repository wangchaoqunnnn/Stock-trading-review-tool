/* ---------- 支撑位有效（缩量回踩 + 次日放量阳线确认） ---------- */

import { $, esc, fmt, pctClass, signed, apiUrl } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const SV_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "support", label: "支撑位", align: "num", dir: -1 },
  { key: "price", label: "现价", align: "num", dir: -1 },
  { key: "pct", label: "涨跌幅", align: "num", dir: -1 },
  { key: "signal_date", label: "信号日" },
  { key: "confirm_date", label: "确认日" },
  { key: "shrink_ratio", label: "回踩缩量比", align: "num", dir: 1 },
  { key: "confirm_vol", label: "确认量比", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
  { key: "industry", label: "板块" },
];

let lastData = null;
registerSortable("sv-list", SV_HEADERS, () => renderSupportValid(lastData));

function svMarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("svMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function svTable(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无符合条件的个股</div>`;
  return `<table><thead><tr>${sortableHead("sv-list", SV_HEADERS)}</tr></thead><tbody>` +
    sortableRows("sv-list", rows).map((r) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td class="num">${fmt(r.support)}</td>
      <td class="num">${fmt(r.price)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td>${esc(r.signal_date)}</td>
      <td>${esc(r.confirm_date)}</td>
      <td class="num">${fmt(r.shrink_ratio)}</td>
      <td class="num">${fmt(r.confirm_vol)}</td>
      <td class="num">${fmt(r.vol_ratio)}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
      <td>${esc(r.industry || "--")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderSupportValid(d) {
  lastData = d;
  svMarketChips(d);
  $("svSummary").textContent = `规则：${d.rule || ""} · 预筛 ${d.scanned || 0} 只，命中 ${d.count || 0} 只 · 更新 ${d.as_of || "--"}`;
  $("svList").innerHTML = svTable(d.stocks || []);
  $("svState").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadSupportValid(force = false) {
  $("svState").textContent = "更新中...（扫描全A约需1~2分钟）";
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 180000);
  try {
    const url = apiUrl("/api/support_valid", force);
    const resp = await fetch(url, { signal: ctrl.signal });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderSupportValid(d);
  } catch (e) {
    if (e.name === "AbortError") {
      $("errors").textContent = "支撑位有效扫描超时：数据源（K线）响应慢，请稍后点击「立即刷新」重试";
      $("svState").textContent = "扫描超时";
    } else {
      $("errors").textContent = "支撑位有效刷新失败：" + e.message;
      $("svState").textContent = "刷新失败";
    }
  } finally {
    clearTimeout(timer);
  }
}
