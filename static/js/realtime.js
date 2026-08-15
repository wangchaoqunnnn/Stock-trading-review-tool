/* ---------- 实时盘口 ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";
import { renderSignals, renderErrors } from "./daily.js";

function renderRtPhase(d) {
  const p = d.phase || {};
  $("rtPhase").innerHTML = `<b>${esc(p.phase)}</b><span>${esc(p.window)}</span><span>${esc(p.tip)}</span>`;
}

function renderRtIndices(d) {
  const rows = (d.indices || []).map((i) => `
    <tr>
      <td>${esc(i.name)}</td>
      <td class="num ${pctClass(i.pct)}">${fmt(i.current)}</td>
      <td class="num ${pctClass(i.pct)}">${signed(i.pct)}</td>
      <td class="num">${i.avg_price ? fmt(i.avg_price) : "--"}</td>
      <td class="num ${i.above_avg == null ? "flat" : (i.above_avg ? "up" : "down")}">${i.above_avg == null ? "--" : (i.above_avg ? "上方" : "下方") + " " + signed(i.vs_avg_pct)}</td>
    </tr>`).join("");
  $("rtIndices").innerHTML = `<table><thead><tr><th>指数</th><th class="num">最新</th><th class="num">涨跌</th><th class="num">分时均价</th><th class="num">相对均价</th></tr></thead><tbody>${rows}</tbody></table>`;
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
  const samples = (y.samples || []).slice(0, 8).map((s) => `
    <tr>
      <td>${esc(s.code)}</td><td>${esc(s.name)}</td>
      <td class="num ${pctClass(s.pct)}">${signed(s.pct)}</td>
      <td class="num">${s.lbc ? `${s.lbc}板` : "首板"}</td>
    </tr>`).join("");
  $("rtYesterday").innerHTML =
    `<div class="subtitle">昨日涨停今日溢价：平均 <b class="${pctClass(y.avg_pct)}">${signed(y.avg_pct)}</b>，上涨 ${y.up || 0} / 下跌 ${y.down || 0}，样本 ${y.matched || 0} 只</div>` +
    (samples ? `<table><thead><tr><th>代码</th><th>名称</th><th class="num">今日涨跌</th><th class="num">昨日连板</th></tr></thead><tbody>${samples}</tbody></table>` : `<div class="subtitle">暂无昨日涨停样本</div>`);
}

function rtBoardTable(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  return `<table><thead><tr><th>板块</th><th class="num">涨跌</th><th class="num">主力(亿)</th><th class="num">涨停</th><th class="num">环比主力</th><th>龙头</th></tr></thead><tbody>` +
    rows.map((r) => `<tr>
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
  html += rtBoardTable((d.industry_top || []).slice(0, 8));
  html += `<div class="subtitle">行业主力净流入 TOP8</div>`;
  html += rtBoardTable((d.industry_flow || []).slice(0, 8));
  html += `<div class="subtitle">概念主力净流入 TOP8</div>`;
  html += rtBoardTable((d.concept_top_flow || []).slice(0, 8));
  $("rtSectors").innerHTML = html;
}

function renderRtWatchlist(d) {
  const rows = (d.watchlist || []).map((s) => {
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
    `<table><thead><tr><th>代码</th><th>名称</th><th class="num">涨跌</th><th class="num">连板</th><th>首封</th><th class="num">炸板</th><th class="num">封单/主力(亿)</th><th class="num">量比</th><th class="num">换手</th><th class="num">分时均价</th><th>信号</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderRealtime(d) {
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
    const url = force ? "/api/realtime_refresh" : "/api/realtime";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderRealtime(d);
  } catch (e) {
    $("errors").textContent = "实时盘口刷新失败：" + e.message;
    $("rtState").textContent = "刷新失败";
  }
}
