/* ---------- 复盘总结：聚合当日真实行情，输出专业级大盘复盘 ----------
 * 数据来自 /api/review（规则引擎基于真实数据生成，不编造）。
 * 界面仿参考设计：浅色专业报告风（渐变页头/堆叠分布条/行式板块条形图/
 * 评级横幅/总结横幅），支持精简/详细模式与导出离线 .html。
 */

import { $, apiUrl, esc, fmt, pctClass, signed } from "./utils.js";

let lastData = null;
let brief = false;

function barW(pct) {
  const v = Math.abs(Number(pct) || 0);
  return Math.min(100, (v / 8) * 100).toFixed(1);
}

/* ---------- 页头 ---------- */

function renderHero(d) {
  const date = d.date_label || (d.as_of || "").slice(0, 10);
  $("rvHero").innerHTML = `
    <h3>A股大盘全景复盘</h3>
    <div class="rv-hero-sub">数据日期 ${esc(date)} · 首席分析师视角 · 更新 ${esc(d.as_of || "--")}</div>
    <div class="rv-hero-concl">${esc(d.summary || "")}</div>`;
}

/* ---------- 一、大盘指数概览 ---------- */

function renderIndices(d) {
  const idx = d.indices || [];
  $("rvIndices").innerHTML = `<div class="rv-indices">` + idx.map((i) => `
    <div class="rv-idx">
      <div class="rv-idx-name">${esc(i.name)}</div>
      <div class="rv-idx-close">${fmt(i.current)}</div>
      <div class="rv-idx-pct ${pctClass(i.pct)}">${signed(i.pct)}</div>
      ${i.amount_yi != null ? `<div class="rv-idx-amt">成交 ${fmt(i.amount_yi)} 亿</div>` : `<div class="rv-idx-amt">成交额暂缺</div>`}
    </div>`).join("") + `</div>` || `<div class="subtitle">指数数据暂不可得</div>`;

  const a = d.amount || {};
  const diff = a.diff_pct;
  $("rvVolume").innerHTML = `
    <div>
      <div class="lbl">两市合计成交额</div>
      <div class="val">${a.total_yi != null ? fmt(a.total_yi) + " 亿元" : "暂缺"}</div>
    </div>
    <div style="text-align:right">
      <div class="lbl">较前一交易日同时段</div>
      <div class="sub">${diff == null ? "环比口径暂不可得" : (diff >= 0 ? "放量 +" : "缩量 ") + Math.abs(diff).toFixed(1) + "%"}</div>
    </div>`;
  $("rvRhythm").textContent = d.rhythm || "";
}

/* ---------- 二、市场情绪温度计 ---------- */

function renderEmotion(d) {
  const b = d.breadth || {};
  const tot = (b.up || 0) + (b.down || 0) + (b.flat || 0) || 1;
  const upPct = ((b.up || 0) / tot * 100).toFixed(1);
  const flatPct = ((b.flat || 0) / tot * 100).toFixed(1);
  const downPct = ((b.down || 0) / tot * 100).toFixed(1);
  $("rvBreadth").innerHTML = `
    <div class="rv-dist">
      <span class="u" style="width:${upPct}%">${upPct}%</span>
      ${Number(flatPct) >= 1 ? `<span class="f" style="width:${flatPct}%">${flatPct}%</span>` : ""}
      <span class="d" style="width:${downPct}%">${downPct}%</span>
    </div>
    <div class="rv-dist-legend">
      <span class="l-u">上涨 ${b.up ?? 0} 家 (${upPct}%)</span>
      <span class="l-f">平盘 ${b.flat ?? 0} 家 (${flatPct}%)</span>
      <span class="l-d">下跌 ${b.down ?? 0} 家 (${downPct}%)</span>
    </div>
    <p class="rv-text">${esc(b.verdict || "")}</p>`;

  const L = d.limit || {};
  const ladderHtml = (L.ladder || []).map((x) =>
    `<span class="rv-chip">${x.board}板 × ${x.count}</span>`).join("");
  $("rvLimit").innerHTML = `
    <div class="rv-kpis">
      <div class="rv-kpi"><span class="rv-kpi-label">自然涨停</span><b class="up">${L.zt ?? "--"}</b></div>
      <div class="rv-kpi"><span class="rv-kpi-label">跌停</span><b class="down">${L.dt ?? "--"}</b></div>
      <div class="rv-kpi"><span class="rv-kpi-label">炸板</span><b>${L.zb ?? "--"}</b></div>
      <div class="rv-kpi"><span class="rv-kpi-label">炸板率</span><b>${fmt(L.zb_rate)}%</b></div>
      <div class="rv-kpi"><span class="rv-kpi-label">最高连板</span><b>${L.max_lb ?? "--"} 板</b></div>
    </div>
    ${ladderHtml ? `<div class="rv-ladder">${ladderHtml}</div>` : ""}
    <div class="rv-rating-banner">
      <div class="level">赚钱效应评级：${esc(L.rating || "--")}</div>
      <div class="reason">${esc(L.reason || "")}</div>
    </div>`;

  const emo = d.emotion || {};
  const cyc = d.cycle || {};
  $("rvEmotion").innerHTML = `<b>情绪周期：</b>${emo.score != null ? `情绪分 ${emo.score}（${esc(emo.level)}）` : "情绪数据暂缺"}${cyc.desc ? " · " + esc(cyc.desc) : ""}`;
}

/* ---------- 三、板块轮动图谱 ---------- */

function sectorList(rows, up) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  const maxPct = Math.max(...rows.map((r) => Math.abs(Number(r.pct) || 0)), 0.01);
  return `<div class="rv-slist">` + rows.map((r, i) => {
    const rankCls = up ? (i === 0 ? "r1" : i === 1 ? "r2" : i === 2 ? "r3" : "rn")
      : (i === 0 ? "g1" : i === 1 ? "g2" : i === 2 ? "g3" : "rn");
    const w = Math.max(6, Math.min(100, Math.abs(Number(r.pct) || 0) / maxPct * 100));
    const flowTxt = r.flow_yi == null ? "" : (r.flow_yi >= 0 ? "+" : "") + fmt(r.flow_yi, 2) + "亿";
    return `<div class="rv-srow">
      <span class="rv-srank ${rankCls}">${i + 1}</span>
      <span class="rv-sname" title="${esc(r.name)}">${esc(r.name)}</span>
      <span class="rv-sbar-wrap"><span class="rv-sbar ${pctClass(r.pct)}" style="width:${w}%">${signed(r.pct)}</span></span>
      <span class="rv-spct ${pctClass(r.pct)}">${signed(r.pct)}</span>
      <span class="rv-sflow">${r.leader ? esc(r.leader) + (r.leader_pct != null ? ` ${signed(r.leader_pct)}` : "") : flowTxt}</span>
    </div>`;
  }).join("") + `</div>`;
}

function renderBoards(d) {
  const bs = d.boards || {};
  $("rvBoards").innerHTML = `
    <h3 class="rv-sub" style="color:#e53935">▲ 行业 / 概念板块涨幅 TOP10</h3>
    ${sectorList(bs.top, true)}
    <h3 class="rv-sub" style="color:#2e7d32;margin-top:14px">▼ 行业 / 概念板块跌幅 TOP10</h3>
    ${sectorList(bs.bottom, false)}`;
  $("rvFeature").innerHTML = `<b>轮动特征：</b>${esc(bs.feature || "")}`;
}

/* ---------- 四、资金动向 ---------- */

function renderNorth(d) {
  const n = d.north || {};
  const li = (arr, cls) => (arr && arr.length
    ? arr.map((s) => `<li>${esc(s.name)} <b class="${pctClass(s.pct)}">${signed(s.pct)}</b> <span class="${cls}">${s.flow_yi == null ? "--" : signed(s.flow_yi, 2, "")}亿</span></li>`).join("")
    : "<li>暂无</li>");
  $("rvNorth").innerHTML = `
    <p class="rv-text rv-note">${esc(n.note || "")}</p>
    <p class="rv-text"><b>替代观测（主力资金）：</b>${esc(n.verdict || "")}</p>
    <div class="rv-cols">
      <div><h3 class="rv-sub">个股主力净流入 TOP3</h3><ul class="rv-list">${li(n.stock_in, "up")}</ul></div>
      <div><h3 class="rv-sub">个股主力净流出 TOP3</h3><ul class="rv-list">${li(n.stock_out, "down")}</ul></div>
    </div>`;
}

/* ---------- 五、主线与强弱研判 ---------- */

function renderMainline(d) {
  const m = d.mainline || {};
  const side = (m.side || []).map((s) => `${esc(s.name)}(${signed(s.pct)})`).join("、");
  const weak = (m.weak || []).map((s) => `${esc(s.name)}(${signed(s.pct)})`).join("、");
  $("rvMainline").innerHTML = `
    <div class="rv-theme main">
      <h4><span class="dot"></span>当前核心主线：${esc(m.main || "--")}</h4>
      <div class="content"><p>${esc(m.logic || "")}</p><p><strong>持续性：</strong>${esc(m.persist || "")}</p></div>
    </div>
    ${side ? `<div class="rv-theme sub"><h4><span class="dot"></span>活跃支线题材</h4><div class="content">${side}</div></div>` : ""}
    ${weak ? `<div class="rv-theme weak"><h4><span class="dot"></span>弱势退潮板块</h4><div class="content">${weak}</div></div>` : ""}
    <div class="rv-theme style">
      <h4><span class="dot"></span>当日市场风格</h4>
      <div class="content">${esc(m.style || "")}</div>
    </div>`;
}

/* ---------- 六、行情阶段客观解读 ---------- */

function renderStage(d) {
  const s = d.stage || {};
  $("rvStage").innerHTML = `
    <div class="rv-phase">阶段判定：<b>${esc(s.phase || "--")}</b></div>
    <p class="rv-text"><b>技术形态：</b>${esc(s.tech || "")}</p>
    <p class="rv-text"><b>核心驱动：</b>${esc(s.drivers || "")}</p>
    <p class="rv-text"><b>核心矛盾：</b>${esc(s.contradiction || "")}</p>
    <p class="rv-text"><b>短期推演：</b>${esc(s.outlook || "")}</p>`;
}

/* ---------- 复盘总结 ---------- */

function renderSummary(d) {
  $("rvSummary").innerHTML = `
    <div class="rv-summary-box">
      <div class="label">当日行情核心结论</div>
      <div class="text">${esc(d.summary || "")}</div>
    </div>
    <div class="rv-risk-box">
      <h4>⚠️ 风险提示</h4>
      <p>${esc(d.risk || "")}</p>
    </div>`;
}

function render(d) {
  lastData = d;
  $("rvState").innerHTML = `更新于 ${esc(d.as_of || "--")}${d.history_date ? ` · 历史回放 ${esc(d.history_date)}` : ""}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
  renderHero(d);
  renderIndices(d);
  renderEmotion(d);
  renderBoards(d);
  renderNorth(d);
  renderMainline(d);
  renderStage(d);
  renderSummary(d);
}

export async function loadReview(force = false) {
  $("rvState").textContent = "更新中...";
  try {
    const url = apiUrl("/api/review", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    render(d);
  } catch (e) {
    $("rvState").textContent = "刷新失败：" + e.message;
    $("errors").textContent = "复盘总结刷新失败：" + e.message;
  }
}

/* ---------- 精简 / 详细模式 ---------- */

function setBrief(v) {
  brief = v;
  $("#page-review").classList.toggle("brief", v);
  $("#rvMode").textContent = v ? "详细模式" : "精简模式";
}

$("rvMode").addEventListener("click", () => setBrief(!brief));

/* ---------- 导出可离线双击打开的 .html ---------- */

async function exportHtml() {
  if (!lastData) {
    $("errors").textContent = "暂无复盘数据，请先加载后再导出。";
    return;
  }
  const page = $("#page-review");
  const clone = page.cloneNode(true);
  clone.classList.remove("brief", "hidden");
  const ctrl = clone.querySelector(".rv-actions");
  if (ctrl) ctrl.remove();

  let css = "";
  try {
    const resp = await fetch("/style.css");
    css = await resp.text();
  } catch (e) {
    css = "";
  }
  const override = `<style>
    #page-review{display:block;margin:0 auto;max-width:1200px;padding:16px;--rv-top:0}
    #page-review .rv-nav{top:0}
    section[id^="rv-sec-"]{scroll-margin-top:16px}
    body{background:#0b0e14}
  </style>`;
  const title = `A股大盘复盘_${lastData.date_label || "当日"}`;
  const html = `<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>${esc(title)}</title>
<style>${css}</style>${override}
</head><body>${clone.outerHTML}</body></html>`;
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${title}.html`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 3000);
}

$("rvExport").addEventListener("click", exportHtml);
