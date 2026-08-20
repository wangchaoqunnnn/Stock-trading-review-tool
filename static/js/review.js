/* ---------- 复盘总结：聚合当日真实行情，输出专业级大盘复盘 ----------
 * 数据来自 /api/review（规则引擎基于真实数据生成，不编造）。
 * 功能：卡片式复盘 + 精简/详细模式 + 导出可离线双击打开的 .html 文件。
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

function levelColor(score) {
  if (score >= 75) return "#f04a4a";
  if (score >= 60) return "#ff9b5e";
  if (score >= 40) return "#aab2c5";
  if (score >= 25) return "#3fae7e";
  return "#2fbf71";
}

// 涨跌幅 → 条形图宽度（±8% 归一）
function barW(pct) {
  const v = Math.abs(Number(pct) || 0);
  return Math.min(100, (v / 8) * 100).toFixed(1);
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
  $("rvAmount").textContent = (d.amount && d.amount.verdict) || "成交额数据暂缺";
  $("rvRhythm").textContent = d.rhythm || "";
}

/* ---------- 二、市场情绪温度计 ---------- */

function renderEmotion(d) {
  const b = d.breadth || {};
  const bars = [
    ["上涨", b.up || 0, b.up_pct || 0, "up"],
    ["平盘", b.flat || 0, b.flat_pct || 0, "flat"],
    ["下跌", b.down || 0, b.down_pct || 0, "down"],
  ];
  $("rvBreadth").innerHTML = `<div class="rv-bars">` + bars.map(([label, n, p, cls]) => `
    <div class="rv-bar-row">
      <span class="rv-bar-label">${label}</span>
      <span class="rv-bar-track ${cls}"><span class="rv-bar-fill" style="width:${Math.min(100, p)}%"></span></span>
      <b class="rv-bar-num">${n} 家 · ${fmt(p, 1)}%</b>
    </div>`).join("") + `</div><p class="rv-text">${esc(b.verdict || "")}</p>`;

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
      <div class="rv-kpi"><span class="rv-kpi-label">赚钱效应</span><b style="color:${ratingColor(L.rating)}">${esc(L.rating || "--")}</b></div>
    </div>
    ${ladderHtml ? `<div class="rv-ladder">${ladderHtml}</div>` : ""}
    <p class="rv-text">${esc(L.reason || "")}</p>`;

  const emo = d.emotion || {};
  const cyc = d.cycle || {};
  const emoTxt = (emo.score != null ? `情绪分 ${emo.score}（<span style="color:${levelColor(emo.score)}">${esc(emo.level)}</span>）` : "情绪数据暂缺");
  $("rvEmotion").innerHTML = `<b>情绪周期：</b>${emoTxt}${cyc.desc ? " · " + esc(cyc.desc) : ""}`;
}

/* ---------- 三、板块轮动图谱 ---------- */

function boardRows(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  return `<table class="rv-board-table"><thead><tr>
      <th>板块</th><th class="num">涨跌幅</th><th class="num">主力资金(亿)</th><th>领涨龙头</th><th class="num">涨/跌家数</th>
    </tr></thead><tbody>` + rows.map((r) => `
      <tr>
        <td>${esc(r.name)}<span class="rv-tag ${r.type === "概念" ? "rv-tag-concept" : ""}">${r.type}</span></td>
        <td class="num"><span class="rv-bar"><span class="rv-bar-fill ${pctClass(r.pct)}" style="width:${barW(r.pct)}%"></span></span><b class="${pctClass(r.pct)}">${signed(r.pct)}</b></td>
        <td class="num ${pctClass(r.flow_yi)}">${r.flow_yi == null ? "--" : signed(r.flow_yi, 2, "")}</td>
        <td>${esc(r.leader || "—")}${r.leader_pct != null ? ` <span class="${pctClass(r.leader_pct)}">${signed(r.leader_pct)}</span>` : ""}</td>
        <td class="num">${r.up ?? "--"}/${r.down ?? "--"}</td>
      </tr>`).join("") + `</tbody></table>`;
}

function renderBoards(d) {
  const bs = d.boards || {};
  $("rvBoards").innerHTML = `
    <h3 class="rv-sub">行业 / 概念板块涨幅 TOP10</h3>
    ${boardRows(bs.top)}
    <h3 class="rv-sub">行业 / 概念板块跌幅 TOP10</h3>
    ${boardRows(bs.bottom)}`;
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
    <p class="rv-text"><b>核心主线：</b>${esc(m.main || "--")}</p>
    <p class="rv-text">${esc(m.logic || "")}</p>
    <p class="rv-text"><b>持续性：</b>${esc(m.persist || "")}</p>
    ${side ? `<p class="rv-text"><b>活跃支线：</b>${side}</p>` : ""}
    ${weak ? `<p class="rv-text"><b>退潮/弱势：</b>${weak}</p>` : ""}
    <p class="rv-text"><b>市场风格：</b>${esc(m.style || "")}</p>`;
}

/* ---------- 六、行情阶段 ---------- */

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
    <div class="rv-summary">${esc(d.summary || "")}</div>
    <p class="rv-risk">${esc(d.risk || "")}</p>`;
}

function render(d) {
  lastData = d;
  $("rvState").innerHTML = `更新于 ${esc(d.as_of || "--")}${d.history_date ? ` · 历史回放 ${esc(d.history_date)}` : ""}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
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
