/* ---------- 市场热度（热度排名TOP50 / 热度上升最快TOP50） ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const HOT_HEADERS = [
  { key: "rank", label: "排名", align: "num", dir: 1 },
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "rank_chg", label: "排名变化", align: "num", dir: -1 },
  { key: "rate", label: "热度值", align: "num", dir: -1 },
  { key: "pct", label: "涨跌幅", align: "num", dir: -1 },
  { key: "popularity_tag", label: "状态" },
  { key: "tags", label: "概念" },
  { key: "analyse_title", label: "上榜原因" },
];

let lastData = null;
registerSortable("hot-top", HOT_HEADERS, () => renderHot(lastData));
registerSortable("hot-rising", HOT_HEADERS, () => renderHot(lastData));
registerSortable("hot-rising3", HOT_HEADERS, () => renderHot(lastData));

function hotMarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("hotMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function hotTable(groupId, rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  return `<table><thead><tr>${sortableHead(groupId, HOT_HEADERS)}</tr></thead><tbody>` +
    sortableRows(groupId, rows).map((r) => `<tr>
      <td class="num">${r.rank || "--"}</td>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.rank_chg)}">${r.rank_chg > 0 ? "▲ " : r.rank_chg < 0 ? "▼ " : ""}${signed(r.rank_chg, 0, "")}</td>
      <td class="num">${fmt(r.rate, 0)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td>${esc(r.popularity_tag || "--")}</td>
      <td>${(r.tags || []).map((t) => `<span class="alert-tag">${esc(t)}</span>`).join("")}</td>
      <td>${esc(r.analyse_title || "--")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderHot(d) {
  lastData = d;
  hotMarketChips(d);
  $("hotSource").textContent = `数据源：${d.source || "同花顺热股榜"} · 更新时间 ${d.as_of || "--"}`;
  $("hotTop").innerHTML = hotTable("hot-top", d.top?.stocks || []);
  $("hotRising").innerHTML = hotTable("hot-rising", d.rising?.stocks || []);
  const r3 = d.rising3 || {};
  if (r3.ready) {
    $("hotR3State").textContent = `连续${r3.days || 3}个交易日排名逐日上升 · ${r3.count || 0} 只（服务端每日快照判定）`;
  } else {
    $("hotR3State").textContent = `数据积累中：今日快照已记录（已积累 ${r3.days_available || 1} 个交易日），需再有 ${(r3.days || 3) - 1} 个交易日后展示连续${r3.days || 3}日结果`;
  }
  $("hotRising3").innerHTML = hotTable("hot-rising3", r3.stocks || []);
  $("hotState").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadHot(force = false) {
  $("hotState").textContent = "更新中...";
  try {
    const url = force ? "/api/hot_refresh" : "/api/hot";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderHot(d);
  } catch (e) {
    $("errors").textContent = "市场热度刷新失败：" + e.message;
    $("hotState").textContent = "刷新失败";
  }
}
