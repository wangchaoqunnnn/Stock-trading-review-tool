/* ---------- 开盘前瞻：隔夜美股 + 外围资产全景（A 股开盘前参考） ----------
 * 数据来自 /api/preopen（腾讯美股 + 东财全市场 + 新浪外盘，规则引擎客观生成）。
 * 复用复盘页的 rv-* 组件样式；支持精简/详细模式。
 */

import { $, apiUrl, esc, fmt, pctClass, signed } from "./utils.js";

let lastData = null;
let brief = false;

function ratingColor(r) {
  if (r === "火热") return "#f04a4a";
  if (r === "温和") return "#ffb020";
  if (r === "偏冷") return "#3fae7e";
  if (r === "极寒") return "#2fbf71";
  return "#aab2c5";
}

function barW(pct) {
  const v = Math.abs(Number(pct) || 0);
  return Math.min(100, (v / 6) * 100).toFixed(1);
}

/* ---------- 一、美股指数概览 ---------- */

function renderIndices(d) {
  const idx = d.indices || [];
  $("poIndices").innerHTML = `<div class="rv-indices">` + idx.map((i) => `
    <div class="rv-idx">
      <div class="rv-idx-name">${esc(i.label || i.name)}</div>
      <div class="rv-idx-close">${fmt(i.price)}</div>
      <div class="rv-idx-pct ${pctClass(i.pct)}">${signed(i.pct)}</div>
      <div class="rv-idx-amt">开 ${fmt(i.open)} · 高 ${fmt(i.high)} · 低 ${fmt(i.low)}</div>
    </div>`).join("") + `</div>` || `<div class="subtitle">美股指数数据暂不可得</div>`;
  $("poTotal").textContent = (d.market && d.market.total_verdict) || "总成交数据暂缺";
  $("poRhythm").textContent = d.rhythm || "";
}

/* ---------- 二、美股情绪温度计 ---------- */

function renderEmotion(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const bars = [
    ["上涨", b.up || 0, b.up_pct || 0, "up"],
    ["平盘", b.flat || 0, b.flat_pct || 0, "flat"],
    ["下跌", b.down || 0, b.down_pct || 0, "down"],
  ];
  $("poBreadth").innerHTML = `<div class="rv-bars">` + bars.map(([label, n, p, cls]) => `
    <div class="rv-bar-row">
      <span class="rv-bar-label">${label}</span>
      <span class="rv-bar-track ${cls}"><span class="rv-bar-fill" style="width:${Math.min(100, p)}%"></span></span>
      <b class="rv-bar-num">${n} 家 · ${fmt(p, 1)}%</b>
    </div>`).join("") + `</div>
    <div class="rv-ladder">
      <span class="rv-chip" style="border-color:rgba(240,74,74,.4);color:#ffb3b3">大涨 ≥+5%：${b.big_up ?? "--"} 家</span>
      <span class="rv-chip" style="border-color:rgba(47,191,113,.4);color:#9fe0c4">大跌 ≤-5%：${b.big_dn ?? "--"} 家</span>
      <span class="rv-chip">大幅异动 |≥10%|：${b.wild ?? "--"} 家</span>
    </div>
    <p class="rv-text">${esc(b.verdict || "")}</p>`;

  const r = m.rating || {};
  $("poRating").innerHTML = `
    <div class="rv-kpis">
      <div class="rv-kpi"><span class="rv-kpi-label">赚钱效应</span><b style="color:${ratingColor(r.level)}">${esc(r.level || "--")}</b></div>
      <div class="rv-kpi"><span class="rv-kpi-label">总成交(亿美元)</span><b>${m.total_amt_yi ? fmt(m.total_amt_yi) : "--"}</b></div>
    </div>
    <p class="rv-text">${esc(r.reason || "")}</p>`;
}

/* ---------- 三、美股板块轮动 ---------- */

function sectorRows(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  return `<table class="rv-board-table"><thead><tr>
      <th>行业板块</th><th class="num">等权涨幅</th><th class="num">成交(亿美元)</th><th>领涨</th><th class="num">涨/跌家数</th>
    </tr></thead><tbody>` + rows.map((r) => `
      <tr>
        <td>${esc(r.name)}</td>
        <td class="num"><span class="rv-bar"><span class="rv-bar-fill ${pctClass(r.pct)}" style="width:${barW(r.pct)}%"></span></span><b class="${pctClass(r.pct)}">${signed(r.pct)}</b></td>
        <td class="num">${r.amount_yi != null ? fmt(r.amount_yi) : "--"}</td>
        <td>${esc(r.leader || "—")}${r.leader_pct != null ? ` <span class="${pctClass(r.leader_pct)}">${signed(r.leader_pct)}</span>` : ""}</td>
        <td class="num">${r.up ?? "--"}/${r.down ?? "--"}</td>
      </tr>`).join("") + `</tbody></table>`;
}

function renderSectors(d) {
  const s = d.sectors || {};
  $("poSectors").innerHTML = `
    <h3 class="rv-sub">美股行业板块涨幅 TOP10（GICS 一级行业等权聚合）</h3>
    ${sectorRows(s.top)}
    <h3 class="rv-sub">美股行业板块跌幅 TOP10</h3>
    ${sectorRows(s.bottom)}`;
  $("poFeature").innerHTML = `<b>板块特征：</b>${esc(s.feature || "")}`;
}

/* ---------- 四、中概 & ADR ---------- */

function renderCn(d) {
  const c = d.cn || {};
  const groups = (c.groups || []).map((g) => `
    <div class="rv-cn-group">
      <h3 class="rv-sub">${esc(g.group)} <span class="${pctClass(g.avg_pct)}">均值 ${signed(g.avg_pct)}</span></h3>
      <ul class="rv-list">${(g.stocks || []).map((s) =>
        `<li>${esc(s.name)} <span class="rv-idx-amt">${fmt(s.price)}</span> <b class="${pctClass(s.pct)}">${signed(s.pct)}</b></li>`).join("") || "<li>暂无</li>"}</ul>
    </div>`).join("");
  const etfs = (c.etfs || []).map((e) =>
    `<span class="rv-chip">${esc(e.name)} ${e.pct == null ? "--" : signed(e.pct)}</span>`).join("");
  $("poCn").innerHTML = `
    ${groups || `<div class="subtitle">中概 ADR 数据暂不可得</div>`}
    ${etfs ? `<div class="rv-ladder" style="margin-top:8px">${etfs}</div>` : ""}
    <p class="rv-text"><b>解读：</b>${esc(c.verdict || "")}</p>`;
}

/* ---------- 五、外围资产 ---------- */

function renderFx(d) {
  const f = d.fx || {};
  const cards = (f.rows || []).map((r) => `
    <div class="rv-idx">
      <div class="rv-idx-name">${esc(r.name)}</div>
      <div class="rv-idx-close">${r.price == null ? "--" : fmt(r.price, 2)}</div>
      <div class="rv-idx-pct ${pctClass(r.pct)}">${r.pct == null ? "--" : signed(r.pct)}</div>
      ${r.note ? `<div class="rv-idx-amt">${esc(r.note)}</div>` : ""}
    </div>`).join("");
  $("poFx").innerHTML = `
    <div class="rv-indices">${cards || `<div class="subtitle">外围资产数据暂不可得</div>`}</div>
    <p class="rv-text"><b>对 A 股传导：</b>${esc(f.verdict || "")}</p>`;
}

/* ---------- 六、主线与强弱 ---------- */

function renderMainline(d) {
  const m = d.mainline || {};
  const side = (m.side || []).map((s) => `${esc(s.name)}(${signed(s.pct)})`).join("、");
  const weak = (m.weak || []).map((s) => `${esc(s.name)}(${signed(s.pct)})`).join("、");
  $("poMainline").innerHTML = `
    <p class="rv-text"><b>美股核心主线：</b>${esc(m.main || "--")}</p>
    <p class="rv-text">${esc(m.logic || "")}</p>
    <p class="rv-text"><b>持续性：</b>${esc(m.persist || "")}</p>
    ${side ? `<p class="rv-text"><b>活跃支线：</b>${side}</p>` : ""}
    ${weak ? `<p class="rv-text"><b>退潮/弱势：</b>${weak}</p>` : ""}
    <p class="rv-text"><b>市场风格：</b>${esc(m.style || "")}</p>
    <p class="rv-text rv-note"><b>A 股传导：</b>${esc(m.impact_a || "")}</p>`;
}

/* ---------- 七、阶段解读 ---------- */

function renderStage(d) {
  const s = d.stage || {};
  $("poStage").innerHTML = `
    <div class="rv-phase">阶段判定：<b>${esc(s.phase || "--")}</b></div>
    <p class="rv-text"><b>技术形态：</b>${esc(s.tech || "")}</p>
    <p class="rv-text"><b>核心驱动：</b>${esc(s.drivers || "")}</p>
    <p class="rv-text"><b>核心矛盾：</b>${esc(s.contradiction || "")}</p>
    <p class="rv-text"><b>开盘观察：</b>${esc(s.focus || "")}</p>`;
}

/* ---------- 总结 ---------- */

function renderSummary(d) {
  $("poSummary").innerHTML = `
    <div class="rv-summary">${esc(d.summary || "")}</div>
    <p class="rv-risk">${esc(d.risk || "")}</p>`;
}

function render(d) {
  lastData = d;
  $("poState").innerHTML = `更新于 ${esc(d.as_of || "--")}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
  renderIndices(d);
  renderEmotion(d);
  renderSectors(d);
  renderCn(d);
  renderFx(d);
  renderMainline(d);
  renderStage(d);
  renderSummary(d);
}

export async function loadPreopen(force = false) {
  $("poState").textContent = "更新中...";
  try {
    const url = apiUrl("/api/preopen", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    render(d);
  } catch (e) {
    $("poState").textContent = "刷新失败：" + e.message;
    $("errors").textContent = "开盘前瞻刷新失败：" + e.message;
  }
}

/* ---------- 精简 / 详细模式 ---------- */

function setBrief(v) {
  brief = v;
  $("#page-preopen").classList.toggle("brief", v);
  $("#poMode").textContent = v ? "详细模式" : "精简模式";
}

$("poMode").addEventListener("click", () => setBrief(!brief));
