/* ---------- 实时盘口 ---------- */

import { $, esc, fmt, pctClass, signed, apiUrl } from "./utils.js";
import { renderSignals, renderErrors } from "./daily.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const RT_INDEX_HEADERS = [
  { key: "name", label: "指数" },
  { key: "current", label: "最新", align: "num", dir: -1 },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "avg_price", label: "分时均价", align: "num", dir: -1 },
  { key: "vs_avg_pct", label: "相对均价", align: "num", dir: -1 },
];
const RT_BOARD_HEADERS = [
  { key: "name", label: "板块" },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "flow_yi", label: "主力(亿)", align: "num", dir: -1 },
  { key: "zt_count", label: "涨停", align: "num", dir: -1 },
  { key: "delta_flow", label: "环比主力", align: "num", dir: -1 },
  { key: "leader", label: "龙头" },
];
const RT_YZT_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "pct", label: "今日涨跌", align: "num", dir: -1 },
  { key: "lbc", label: "昨日连板", align: "num", dir: -1 },
];
const RT_WATCH_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "lbc", label: "连板", align: "num", dir: -1 },
  { key: "fbt", label: "首封" },
  { key: "zbc", label: "炸板", align: "num", dir: -1 },
  { key: "flow_yi", label: "封单/主力(亿)", align: "num", dir: -1 },
  { key: "vol_ratio", label: "量比", align: "num", dir: -1 },
  { key: "turnover", label: "换手", align: "num", dir: -1 },
  { key: "vs_avg", label: "分时均价", align: "num", dir: -1 },
  { key: "alerts", label: "信号" },
];

let lastData = null;
registerSortable("rt-indices", RT_INDEX_HEADERS, () => renderRealtime(lastData));
registerSortable("rt-ind-top", RT_BOARD_HEADERS, () => renderRealtime(lastData));
registerSortable("rt-ind-flow", RT_BOARD_HEADERS, () => renderRealtime(lastData));
registerSortable("rt-con-flow", RT_BOARD_HEADERS, () => renderRealtime(lastData));
registerSortable("rt-yzt", RT_YZT_HEADERS, () => renderRealtime(lastData));
registerSortable("rt-watch", RT_WATCH_HEADERS, () => renderRealtime(lastData));

function renderRtPhase(d) {
  const p = d.phase || {};
  $("rtPhase").innerHTML = `<b>${esc(p.phase)}</b><span>${esc(p.window)}</span><span>${esc(p.tip)}</span>`;
}

function renderRtIndices(d) {
  const rows = sortableRows("rt-indices", d.indices || []).map((i) => `
    <tr>
      <td>${esc(i.name)}</td>
      <td class="num ${pctClass(i.pct)}">${fmt(i.current)}</td>
      <td class="num ${pctClass(i.pct)}">${signed(i.pct)}</td>
      <td class="num">${i.avg_price ? fmt(i.avg_price) : "--"}</td>
      <td class="num ${i.above_avg == null ? "flat" : (i.above_avg ? "up" : "down")}">${i.above_avg == null ? "--" : (i.above_avg ? "上方" : "下方") + " " + signed(i.vs_avg_pct)}</td>
    </tr>`).join("");
  $("rtIndices").innerHTML = `<table><thead><tr>${sortableHead("rt-indices", RT_INDEX_HEADERS)}</tr></thead><tbody>${rows}</tbody></table>`;
}

function renderRtEmotion(d) {
  const e = d.emotion || {};
  $("rtEmotion").innerHTML = [
    `<span class="chip">涨停 <b class="up">${e.zt || 0}</b></span>`,
    `<span class="chip">炸板 <b>${e.zb || 0}</b></span>`,
    `<span class="chip">跌停 <b class="down">${e.dt || 0}</b></span>`,
    `<span class="chip">最高 <b class="up">${e.max_lb || 0}板</b></span>`,
    `<span class="chip">竞价涨停 <b class="up">${e.jingjia || 0}</b></span>`,
    `<span class="chip">炸板率 <b>${fmt(e.zhaban_rate)}%</b></span>`,
  ].join("");
}

function renderRtYesterday(d) {
  const y = d.yesterday_zt || {};
  const samples = sortableRows("rt-yzt", (y.samples || []).slice(0, 8)).map((s) => `
    <tr>
      <td>${esc(s.code)}</td><td>${esc(s.name)}</td>
      <td class="num ${pctClass(s.pct)}">${signed(s.pct)}</td>
      <td class="num">${s.lbc ? `${s.lbc}板` : "首板"}</td>
    </tr>`).join("");
  $("rtYesterday").innerHTML =
    `<div class="subtitle">昨日涨停今日溢价：平均 <b class="${pctClass(y.avg_pct)}">${signed(y.avg_pct)}</b>，上涨 ${y.up || 0} / 下跌 ${y.down || 0}，样本 ${y.matched || 0} 只</div>` +
    (samples ? `<table><thead><tr>${sortableHead("rt-yzt", RT_YZT_HEADERS)}</tr></thead><tbody>${samples}</tbody></table>` : `<div class="subtitle">暂无昨日涨停样本</div>`);
}

function rtBoardTable(groupId, rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  return `<table><thead><tr>${sortableHead(groupId, RT_BOARD_HEADERS)}</tr></thead><tbody>` +
    sortableRows(groupId, rows).map((r) => `<tr>
      <td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num ${pctClass(r.flow_yi)}">${signed(r.flow_yi, 2, "")}</td>
      <td class="num up">${r.zt_count || 0}</td>
      <td class="num ${pctClass(r.delta_flow)}">${signed(r.delta_flow, 2, "")}</td>
      <td>${esc(r.leader || "--")} ${r.leader_locked ? `<span class="badge lb">封</span>` : ""}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderRtSectors(d) {
  let html = `<div class="subtitle">行业涨幅 TOP8（涨停家数 / 龙头封板 / 环比主力）</div>`;
  html += rtBoardTable("rt-ind-top", (d.industry_top || []).slice(0, 8));
  html += `<div class="subtitle">行业主力净流入 TOP8</div>`;
  html += rtBoardTable("rt-ind-flow", (d.industry_flow || []).slice(0, 8));
  html += `<div class="subtitle">概念主力净流入 TOP8</div>`;
  html += rtBoardTable("rt-con-flow", (d.concept_top_flow || []).slice(0, 8));
  $("rtSectors").innerHTML = html;
}

function renderRtWatchlist(d) {
  const rows = sortableRows("rt-watch", d.watchlist || []).map((s) => {
    const alerts = (s.alerts || []).map((a) => `<span class="alert-tag">${esc(a)}</span>`).join(" ");
    return `<tr>
      <td>${esc(s.code)}</td>
      <td>${esc(s.name)}</td>
      <td class="num ${pctClass(s.pct)}">${signed(s.pct)}</td>
      <td class="num">${s.lbc ? `<span class="badge lb">${s.lbc}板</span>` : "--"}</td>
      <td>${esc(s.fbt || "--")}</td>
      <td class="num">${s.zbc || 0}</td>
      <td class="num ${pctClass(s.flow_yi)}">${signed(s.flow_yi, 2, "")}</td>
      <td class="num">${fmt(s.vol_ratio)}</td>
      <td class="num">${fmt(s.turnover)}%</td>
      <td class="num ${s.above_avg == null ? "flat" : (s.above_avg ? "up" : "down")}">${s.above_avg == null ? "--" : (s.above_avg ? "上方" : "下方") + " " + fmt(s.vs_avg) + "%"}</td>
      <td>${alerts || "--"}</td>
    </tr>`;
  }).join("");
  $("rtWatchlist").innerHTML =
    `<table><thead><tr>${sortableHead("rt-watch", RT_WATCH_HEADERS)}</tr></thead><tbody>${rows}</tbody></table>`;
}

function renderRealtime(d) {
  lastData = d;
  renderRtPhase(d);
  renderRtIndices(d);
  renderRtEmotion(d);
  renderRtYesterday(d);
  renderSignals(d, "rtSignals");
  renderRtSectors(d);
  renderRtWatchlist(d);
  renderErrors(d);
  $("rtState").textContent = "已更新 " + (d.as_of || "--");
}

export async function loadRealtime(force = false) {
  $("rtState").textContent = "更新中...";
  try {
    const url = apiUrl("/api/realtime", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderRealtime(d);
  } catch (e) {
    $("errors").textContent = "实时盘口刷新失败：" + e.message;
    $("rtState").textContent = "刷新失败";
  }
}
