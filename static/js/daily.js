/* ---------- 每日复盘 ---------- */

import { $, esc, fmt, pctClass, signed, toYi } from "./utils.js";
import { auto } from "./state.js";
import { registerSortable, sortableHead, sortableRows } from "./sortable.js";

const BOARD_HEADERS = [
  { key: "name", label: "板块" },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "flow_yi", label: "主力(亿)", align: "num", dir: -1 },
  { key: "leader", label: "领涨" },
];
const FLOW_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "flow_yi", label: "主力(亿)", align: "num", dir: -1 },
  { key: "amount_yi", label: "成交(亿)", align: "num", dir: -1 },
];
const ZT_BOARD_HEADERS = [
  { key: "name", label: "行业" },
  { key: "count", label: "家数", align: "num", dir: -1 },
  { key: "fund_yi", label: "封单(亿)", align: "num", dir: -1 },
  { key: "max_lb", label: "最高连板", align: "num", dir: -1 },
];
const WATCH_HEADERS = [
  { key: "code", label: "代码" },
  { key: "name", label: "名称" },
  { key: "pct", label: "涨跌", align: "num", dir: -1 },
  { key: "lbc", label: "连板", align: "num", dir: -1 },
  { key: "flow_yi", label: "封单/主力(亿)", align: "num", dir: -1 },
  { key: "fbt", label: "首封" },
];
const AUCTION_HEADERS = [
  { key: "c", label: "代码" },
  { key: "n", label: "名称" },
  { key: "fund", label: "封单(亿)", align: "num", dir: -1 },
  { key: "hybk", label: "行业" },
];

let lastData = null;
registerSortable("sec-ind-pct", BOARD_HEADERS, () => render(lastData));
registerSortable("sec-ind-flow", BOARD_HEADERS, () => render(lastData));
registerSortable("sec-con-flow", BOARD_HEADERS, () => render(lastData));
registerSortable("daily-inflow", FLOW_HEADERS, () => render(lastData));
registerSortable("daily-outflow", FLOW_HEADERS, () => render(lastData));
registerSortable("zt-byboard", ZT_BOARD_HEADERS, () => render(lastData));
registerSortable("zt-watch", WATCH_HEADERS, () => render(lastData));
registerSortable("zt-auction", AUCTION_HEADERS, () => render(lastData));

export function renderSignals(d, target = "signals") {
  const items = (d.signals || []).map((s) => {
    const cls = s.ok ? "ok" : "no";
    const mark = s.ok ? "✓" : "✕";
    return `<div class="signal ${cls}">
      <span class="mark">${mark}</span>
      <span class="name">${esc(s.name)}</span>
      <span class="detail">${esc(s.detail)}</span>
    </div>`;
  }).join("");
  $(target).innerHTML = `<div class="signal-list">${items || "暂无信号数据"}</div>`;
}

export function renderErrors(d) {
  $("errors").textContent = (d.errors && d.errors.length) ? "部分数据获取失败：" + d.errors.join(" | ") : "";
}

function renderKpis(d) {
  const cards = [];
  for (const idx of d.indices || []) {
    cards.push(`
      <div class="kpi">
        <div class="label">${esc(idx.name)}</div>
        <div class="value ${pctClass(idx.pct)}">${fmt(idx.current)}</div>
        <div class="sub ${pctClass(idx.pct)}">${signed(idx.pct)}</div>
      </div>`);
  }
  const b = d.breadth || {};
  const e = d.emotion || {};
  cards.push(`
    <div class="kpi">
      <div class="label">两市成交额</div>
      <div class="value">${fmt(d.amount_yi)}亿</div>
      <div class="sub">沪+深 东财口径</div>
    </div>
    <div class="kpi">
      <div class="label">上涨 / 下跌</div>
      <div class="value"><span class="up">${b.up || 0}</span> / <span class="down">${b.down || 0}</span></div>
      <div class="sub">平盘 ${b.flat || 0} 家</div>
    </div>
    <div class="kpi">
      <div class="label">涨停 / 炸板</div>
      <div class="value"><span class="up">${e.zt || 0}</span> / <span class="flat">${e.zb || 0}</span></div>
      <div class="sub">跌停 ${e.dt || 0} 家</div>
    </div>
    <div class="kpi">
      <div class="label">最高连板</div>
      <div class="value">${e.max_lb || 0} 板</div>
      <div class="sub">竞价涨停 ${e.jingjia || 0} 家 · 炸板率 ${fmt(e.zhaban_rate)}%</div>
    </div>`);
  $("kpis").innerHTML = cards.join("");
}

function renderEmotion(d) {
  const e = d.emotion || {};
  $("emotion").innerHTML = [
    `<span class="chip">涨停 <b class="up">${e.zt || 0}</b></span>`,
    `<span class="chip">炸板 <b>${e.zb || 0}</b></span>`,
    `<span class="chip">跌停 <b class="down">${e.dt || 0}</b></span>`,
    `<span class="chip">最高 <b class="up">${e.max_lb || 0}板</b></span>`,
    `<span class="chip">竞价涨停 <b class="up">${e.jingjia || 0}</b></span>`,
    `<span class="chip">炸板率 <b>${fmt(e.zhaban_rate)}%</b></span>`,
  ].join("");
}

function boardTable(groupId, rows, extra = "") {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  const head = sortableHead(groupId, BOARD_HEADERS);
  const body = sortableRows(groupId, rows).map((r) => `
    <tr>
      <td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num ${pctClass(r.flow_yi)}">${signed(r.flow_yi, 2, "")}</td>
      <td>${esc(r.leader || "--")}</td>
    </tr>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${extra}`;
}

function renderSectors(d) {
  const s = d.sectors || {};
  let html = `<div class="subtitle">行业 · 涨幅TOP8</div>`;
  html += boardTable("sec-ind-pct", (s.industry_top_pct || []).slice(0, 8));
  html += `<div class="subtitle">行业 · 主力净流入TOP8</div>`;
  html += boardTable("sec-ind-flow", (s.industry_top_flow || []).slice(0, 8));
  html += `<div class="subtitle">概念 · 主力净流入TOP8</div>`;
  html += boardTable("sec-con-flow", (s.concept_top_flow || []).slice(0, 8));
  $("sectors").innerHTML = html;
}

function flowTable(groupId, rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  const head = sortableHead(groupId, FLOW_HEADERS);
  const body = sortableRows(groupId, rows).map((r) => `
    <tr>
      <td>${esc(r.code)}</td>
      <td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num ${pctClass(r.flow_yi)}">${signed(r.flow_yi, 2, "")}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
    </tr>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderFlows(d) {
  const f = d.flows || {};
  $("flows").innerHTML =
    `<div class="subtitle">主力净流入 TOP10</div>` + flowTable("daily-inflow", (f.inflow || []).slice(0, 10)) +
    `<div class="subtitle">主力净流出 TOP10</div>` + flowTable("daily-outflow", (f.outflow || []).slice(0, 10));
}

function renderZt(d) {
  const z = d.zt_summary || {};
  const byBoard = (z.by_board || []).slice(0, 8);
  let html = `<div class="subtitle">涨停行业分布 TOP8</div>`;
  html += `<table><thead><tr>${sortableHead("zt-byboard", ZT_BOARD_HEADERS)}</tr></thead><tbody>` +
    sortableRows("zt-byboard", byBoard).map((r) => `<tr><td>${esc(r.name)}</td><td class="num up">${r.count}</td><td class="num">${fmt(r.fund_yi)}</td><td class="num">${r.max_lb}板</td></tr>`).join("") +
    `</tbody></table>`;

  html += `<div class="subtitle">观察池（连板 / 主力资金）</div>`;
  const w = (d.watchlist || []).slice(0, 15);
  html += `<table><thead><tr>${sortableHead("zt-watch", WATCH_HEADERS)}</tr></thead><tbody>` +
    sortableRows("zt-watch", w).map((r) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num">${r.lbc ? `<span class="badge lb">${r.lbc}板</span>` : "--"}</td>
      <td class="num">${fmt(r.flow_yi)}</td>
      <td>${r.fbt ? esc(String(r.fbt)) : "--"}</td>
    </tr>`).join("") +
    `</tbody></table>`;

  const auction = (z.auction || []).slice(0, 5);
  html += `<div class="subtitle">竞价(09:25)封板</div>`;
  html += `<table><thead><tr>${sortableHead("zt-auction", AUCTION_HEADERS)}</tr></thead><tbody>` +
    sortableRows("zt-auction", auction).map((r) => `<tr><td>${esc(r.c)}</td><td>${esc(r.n)}</td><td class="num">${fmt(toYi(r.fund))}</td><td>${esc(r.hybk || "")}</td></tr>`).join("") +
    `</tbody></table>`;
  $("ztpool").innerHTML = html;
}

function renderNews(d) {
  const items = (d.news || []).slice(0, 20).map((n) => `
    <div class="news-item">
      <div class="time">${esc(n.time)}</div>
      <div class="title">${esc(n.title)}</div>
      <div class="summary">${esc(n.summary)}</div>
      ${n.url ? `<a href="${esc(n.url)}" target="_blank" rel="noopener">阅读原文</a>` : ""}
    </div>`).join("");
  $("news").innerHTML = items || `<div class="subtitle">今日暂无相关快讯</div>`;
}

function render(d) {
  lastData = d;
  renderKpis(d);
  renderEmotion(d);
  renderSignals(d);
  renderSectors(d);
  renderFlows(d);
  renderZt(d);
  renderNews(d);
  renderErrors(d);
  $("asOf").textContent = "数据时间 " + (d.as_of || "--");
}

export async function load(force = false) {
  $("refreshState").textContent = "更新中...";
  try {
    const url = force ? "/api/refresh" : "/api/snapshot";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    render(d);
    $("refreshState").textContent = auto ? "自动刷新 30s" : "已暂停自动刷新";
  } catch (e) {
    $("errors").textContent = "刷新失败：" + e.message;
    $("refreshState").textContent = "刷新失败";
  }
}
