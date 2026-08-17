/* ---------- 涨停横盘（20日内封涨停 + 横盘震荡/上升趋势） ---------- */

import { $, esc, fmt, pctClass, signed, apiUrl } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const L20_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "state", label: "状态" },
  { key: "days_since", label: "距涨停", align: "num", dir: 1 },
  { key: "pct", label: "今日涨跌", align: "num", dir: -1 },
  { key: "pct_5d", label: "近5日涨幅", align: "num", dir: -1 },
  { key: "ma20", label: "MA20", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
  { key: "lbc", label: "当时连板", align: "num", dir: -1 },
  { key: "industry", label: "板块", dir: 1 },
  { key: "limit_date", label: "涨停日" },
];

let lastData = null;
registerSortable("l20", L20_HEADERS, () => renderLimit20(lastData));

function l20MarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("l20Market").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function stateTag(s) {
  if (s === "uptrend") return `<span class="alert-tag" style="color:#2fbf71;border-color:#2fbf71;">上升趋势</span>`;
  if (s === "sideways") return `<span class="alert-tag" style="color:#4c8dff;border-color:#4c8dff;">横盘震荡</span>`;
  return `<span class="alert-tag">${esc(s)}</span>`;
}

function l20Table(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无符合条件的个股</div>`;
  const head = sortableHead("l20", L20_HEADERS);
  return `<table><thead><tr>${head}</tr></thead><tbody>` +
    sortableRows("l20", rows).map((r) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td>${stateTag(r.state)}</td>
      <td class="num">${r.days_since || 0}天</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num ${pctClass(r.pct_5d)}">${r.pct_5d == null ? "--" : signed(r.pct_5d)}</td>
      <td class="num">${fmt(r.ma20)}</td>
      <td class="num">${fmt(r.vol_ratio)}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
      <td class="num">${r.lbc ? `${r.lbc}板` : "首板"}</td>
      <td>${esc(r.industry || "--")}</td>
      <td>${esc(r.limit_date)}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderLimit20(d) {
  lastData = d;
  l20MarketChips(d);
  const up = d.uptrend_stocks || [];
  const sw = d.sideways_stocks || [];
  $("l20Summary").textContent = `统计窗口 ${(d.window_dates || []).length} 个交易日（${(d.window_dates || []).slice(-1)[0] || ""} ~ ${(d.window_dates || [])[0] || ""}）| 20日内封涨停 ${d.universe || 0} 只 → 上升趋势 ${d.uptrend_count || 0} / 横盘震荡 ${d.sideways_count || 0}`;
  $("l20Uptrend").innerHTML = `<div class="subtitle">上升趋势（${d.uptrend_count || 0}）</div>` + l20Table(up);
  $("l20Sideways").innerHTML = `<div class="subtitle">横盘震荡（${d.sideways_count || 0}）</div>` + l20Table(sw);
  $("l20State").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadLimit20(force = false) {
  $("l20State").textContent = "更新中...（扫描全A约需1~2分钟）";
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 180000);
  try {
    const url = apiUrl("/api/limit20", force);
    const resp = await fetch(url, { signal: ctrl.signal });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderLimit20(d);
  } catch (e) {
    if (e.name === "AbortError") {
      $("errors").textContent = "涨停横盘扫描超时：数据源（腾讯/新浪K线）响应慢，请稍后点击「立即刷新」重试";
      $("l20State").textContent = "扫描超时";
    } else {
      $("errors").textContent = "涨停横盘刷新失败：" + e.message;
      $("l20State").textContent = "刷新失败";
    }
  } finally {
    clearTimeout(timer);
  }
}
