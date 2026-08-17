/* ---------- 龙头股（市场总龙 / 板块龙头 / 情绪龙头） ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const MARKET_HEADERS = [
  { key: "name", label: "名称" },
  { key: "code", label: "代码" },
  { key: "lbc", label: "连板", align: "num", dir: -1 },
  { key: "fund_yi", label: "封单(亿)", align: "num", dir: -1 },
  { key: "pct", label: "涨跌幅", align: "num", dir: -1 },
  { key: "fbt", label: "首封" },
  { key: "industry", label: "板块" },
  { key: "tag", label: "标签" },
];
const BOARD_HEADERS = [
  { key: "industry", label: "板块" },
  { key: "zt_count", label: "涨停家数", align: "num", dir: -1 },
  { key: "name", label: "龙头" },
  { key: "code", label: "代码" },
  { key: "lbc", label: "连板", align: "num", dir: -1 },
  { key: "fund_yi", label: "封单(亿)", align: "num", dir: -1 },
  { key: "pct", label: "涨跌幅", align: "num", dir: -1 },
  { key: "fbt", label: "首封" },
];
const EMOTION_HEADERS = [
  { key: "hot_rank", label: "人气排名", align: "num", dir: 1 },
  { key: "name", label: "名称" },
  { key: "code", label: "代码" },
  { key: "lbc", label: "连板", align: "num", dir: -1 },
  { key: "fund_yi", label: "封单(亿)", align: "num", dir: -1 },
  { key: "pct", label: "涨跌幅", align: "num", dir: -1 },
  { key: "fbt", label: "首封" },
  { key: "industry", label: "板块" },
  { key: "tag", label: "标签" },
];

let lastData = null;
registerSortable("ld-market", MARKET_HEADERS, () => renderLeaders(lastData));
registerSortable("ld-board", BOARD_HEADERS, () => renderLeaders(lastData));
registerSortable("ld-emotion", EMOTION_HEADERS, () => renderLeaders(lastData));

function ldMarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("ldMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function ldTable(groupId, headers, rows, renderRow) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  return `<table><thead><tr>${sortableHead(groupId, headers)}</tr></thead><tbody>` +
    sortableRows(groupId, rows).map(renderRow).join("") + `</tbody></table>`;
}

function renderLeaders(d) {
  lastData = d;
  ldMarketChips(d);
  $("ldMaxState").textContent = `最高 ${d.max_lb || 0} 板 · ${d.market_leader?.count || 0} 只`;
  $("ldMarketLeader").innerHTML = ldTable("ld-market", MARKET_HEADERS, d.market_leader?.stocks || [], (r) => `<tr>
      <td><b>${esc(r.name)}</b></td><td>${esc(r.code)}</td>
      <td class="num"><span class="badge lb">${r.lbc}板</span></td>
      <td class="num">${fmt(r.fund_yi)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td>${esc(r.fbt)}</td>
      <td>${esc(r.industry || "--")}</td>
      <td>${esc(r.tag || "--")}</td>
    </tr>`);
  $("ldBoardLeader").innerHTML = ldTable("ld-board", BOARD_HEADERS, d.board_leader?.stocks || [], (r) => `<tr>
      <td><b>${esc(r.industry)}</b></td>
      <td class="num up">${r.zt_count}</td>
      <td>${esc(r.name)}</td><td>${esc(r.code)}</td>
      <td class="num">${r.lbc ? `<span class="badge lb">${r.lbc}板</span>` : "首板"}</td>
      <td class="num">${fmt(r.fund_yi)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td>${esc(r.fbt)}</td>
    </tr>`);
  $("ldEmotionLeader").innerHTML = ldTable("ld-emotion", EMOTION_HEADERS, d.emotion_leader?.stocks || [], (r) => `<tr>
      <td class="num">${r.hot_rank || "--"}</td>
      <td><b>${esc(r.name)}</b></td><td>${esc(r.code)}</td>
      <td class="num">${r.lbc ? `<span class="badge lb">${r.lbc}板</span>` : "首板"}</td>
      <td class="num">${fmt(r.fund_yi)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td>${esc(r.fbt)}</td>
      <td>${esc(r.industry || "--")}</td>
      <td>${esc(r.tag || "--")}</td>
    </tr>`);
  $("ldState").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadLeaders(force = false) {
  $("ldState").textContent = "更新中...";
  try {
    const url = force ? "/api/leaders_refresh" : "/api/leaders";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderLeaders(d);
  } catch (e) {
    $("errors").textContent = "龙头股刷新失败：" + e.message;
    $("ldState").textContent = "刷新失败";
  }
}
