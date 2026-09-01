/* ---------- 情绪周期：阶段判断（冰点/启动/发酵/高潮/退潮）+ 关键节点 ---------- */

import { $, apiUrl, esc, fmt, signed } from "./utils.js";

let lastData = null;

const PHASE_COLOR = {
  "冰点": "#2fbf71",
  "启动": "#3fae7e",
  "发酵": "#4c8dff",
  "高潮": "#f04a4a",
  "退潮": "#ff9b5e",
};

function renderHero(d) {
  $("ecHero").innerHTML = `
    <h3>短线情绪周期</h3>
    <div class="rv-hero-sub">赚钱效应与亏钱效应的循环 · 阶段判断 + 关键节点 · 每30秒自动刷新 · 更新 ${esc(d.as_of || "--")}</div>
    <div class="rv-hero-concl">当前阶段：<b style="font-size:18px;color:${PHASE_COLOR[d.phase] || "#fff"}">${esc(d.phase)}</b>（情绪分 ${d.emotion_score ?? "--"} · 周期打分 ${d.score}）${d.nodes?.length ? ` · 检测到节点：${d.nodes.map((n) => n.type).join("、")}` : ""}</div>`;
}

function renderPhase(d) {
  const color = PHASE_COLOR[d.phase] || "#aab2c5";
  $("ecPhase").innerHTML = `
    <div class="rv-phase" style="border-color:${color};color:${color};background:${color}1a">
      当前阶段：<b style="font-size:22px">${esc(d.phase)}</b>
      <span class="rv-tag" style="margin-left:8px">前一交易日：${esc(d.history?.prev_phase || "--")}</span>
    </div>
    ${d.note ? `<p class="rv-text rv-note">${esc(d.note)}</p>` : ""}
    <p class="rv-text"><b>盘面特征：</b>${esc(d.phase_desc || "")}</p>
    <p class="rv-text rv-note"><b>操作策略：</b>${esc(d.strategy || "")}</p>`;
}

function kpi(label, value, cls) {
  return `<div class="rv-kpi"><span class="rv-kpi-label">${label}</span><b class="${cls || ""}">${value}</b></div>`;
}

function renderMetrics(d) {
  const m = d.metrics || {};
  const promo = m.promo_rate == null ? "--" : fmt(m.promo_rate, 1) + "%";
  const amt = m.amount_diff_pct == null ? "--" : (m.amount_diff_pct >= 0 ? "+" : "") + fmt(m.amount_diff_pct, 1) + "%";
  $("ecMetrics").innerHTML = `
    <div class="rv-kpis">
      ${kpi("涨停家数", m.zt ?? "--", "up")}
      ${kpi("炸板率", fmt(m.zb_rate) + "%", m.zb_rate > 30 ? "down" : "up")}
      ${kpi("跌停", m.dt ?? "--", "down")}
      ${kpi("最高连板", (m.max_lb ?? "--") + " 板")}
      ${kpi("晋级率", promo, (m.promo_rate ?? 0) >= 30 ? "up" : "down")}
      ${kpi("大面数", m.big_loss ?? "--", (m.big_loss ?? 0) >= 15 ? "down" : "up")}
      ${kpi("昨日涨停", m.prev_zt ?? "--")}
      ${kpi("量能环比", amt, (m.amount_diff_pct ?? 0) >= 0 ? "up" : "down")}
    </div>
    <p class="rv-text rv-note" style="font-size:12px">晋级率=昨日涨停股今日继续涨停比例；大面数=昨日涨停今日跌超7%家数；量能环比=两市成交较前一日同时段。</p>`;
}

function renderLeader(d) {
  const l = d.leader || {};
  const today = l.today ? `${esc(l.today.name)}（${l.today.lb}板 · 封单${l.today.fund_yi}亿）` : "暂无（今日无连板）";
  const yest = l.yesterday ? `${esc(l.yesterday.name)}（${l.yesterday.lb}板）` : "无";
  $("ecLeader").innerHTML = `
    <div class="rv-two">
      <div class="rv-pos-neg pos">
        <h4 style="font-size:13px;color:#f04a4a;margin-bottom:6px">今日空间龙头</h4>
        <div style="font-size:13px">${today}</div>
      </div>
      <div class="rv-pos-neg neg">
        <h4 style="font-size:13px;color:#2fbf71;margin-bottom:6px">昨日龙头今日表现</h4>
        <div style="font-size:13px">${yest} → <b>${esc(l.status_text || "--")}</b></div>
      </div>
    </div>`;
  const nodes = d.nodes || [];
  $("ecNodes").innerHTML = nodes.length ? `
    <h3 class="rv-sub" style="margin-top:12px">🎯 检测到的关键节点</h3>
    <table class="rv-table"><thead><tr><th>时间</th><th>节点</th><th>含义</th></tr></thead><tbody>
      ${nodes.map((n) => `<tr><td>${esc(n.time)}</td><td><b style="color:#ffb020">${esc(n.type)}</b></td><td style="font-size:12px">${esc(n.desc)}</td></tr>`).join("")}
    </tbody></table>`
    : `<p class="rv-text" style="margin-top:10px">当前无明确节点信号（节点=周期切换的岔路口，如龙头断板/跌停、启动点、退潮点）。</p>`;
}

function renderHistory(d) {
  const rows = (d.history && d.history.rows) || [];
  if (!rows.length) {
    $("ecHistory").innerHTML = `<div class="subtitle">暂无足够历史数据</div>`;
    return;
  }
  const tbody = [...rows].reverse().map((r) => `<tr>
      <td>${esc(r.date)}</td>
      <td class="num"><b>${r.score}</b></td>
      <td>${esc(r.level)}</td>
      <td class="num up">${r.zt}</td>
      <td class="num">${fmt(r.zhaban_rate)}%</td>
      <td class="num">${r.max_lb}板</td>
      <td class="num down">${r.dt}</td>
    </tr>`).join("");
  $("ecHistory").innerHTML = `
    <table class="rv-table"><thead><tr>
      <th>日期</th><th class="num">情绪分</th><th>等级</th><th class="num">涨停</th><th class="num">炸板率</th><th class="num">最高连板</th><th class="num">跌停</th>
    </tr></thead><tbody>${tbody}</tbody></table>`;
}

function render(d) {
  lastData = d;
  $("ecState").innerHTML = `更新于 ${esc(d.as_of || "--")}${d.history_date ? ` · 历史回放 ${esc(d.history_date)}` : ""}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
  renderHero(d);
  renderPhase(d);
  renderMetrics(d);
  renderLeader(d);
  renderHistory(d);
}

export async function loadEmotionCycle(force = false) {
  $("ecState").textContent = "更新中...";
  try {
    const url = apiUrl("/api/emotion_cycle", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    render(d);
  } catch (e) {
    $("ecState").textContent = "刷新失败：" + e.message;
    $("errors").textContent = "情绪周期刷新失败：" + e.message;
  }
}
