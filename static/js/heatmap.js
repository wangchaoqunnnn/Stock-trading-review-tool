/* ---------- 市场热力图（行业板块涨跌色块 + 情绪周期表） ---------- */

import { $, esc, fmt, pctClass, signed, apiUrl } from "./utils.js";

let lastData = null;
let heatSort = "pct"; // 排序字段：pct 涨跌幅 / flow 主力资金
let lastEmotion = null;

// 红涨绿跌：归一化到 ±5%
function heatColor(pct) {
  const t = Math.max(-1, Math.min(1, pct / 5));
  if (t >= 0) return `rgba(240, 74, 74, ${(0.15 + t * 0.85).toFixed(2)})`;
  return `rgba(47, 191, 113, ${(0.15 + (-t) * 0.85).toFixed(2)})`;
}

function hmMarketChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("hmMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function renderHeatmap(d) {
  lastData = d;
  hmMarketChips(d);
  const boards = d.boards || [];
  const sorted = [...boards].sort((a, b) => heatSort === "flow"
    ? (b.flow_yi || 0) - (a.flow_yi || 0)
    : (b.pct || 0) - (a.pct || 0));
  $("hmSummary").textContent = `共 ${d.total || boards.length} 个行业板块 · 按${heatSort === "flow" ? "主力净流入" : "涨跌幅"}降序`;
  $("hmBoards").innerHTML = sorted.map((b) => `
    <div class="heat-cell" style="background:${heatColor(b.pct)}"
         title="${esc(b.name)} 涨跌${signed(b.pct)} 主力${signed(b.flow_yi, 2, "")}亿 成交${fmt(b.amount_yi)}亿 领涨:${esc(b.leader || "-")}">
      <div class="heat-name">${esc(b.name)}</div>
      <div class="heat-pct ${pctClass(b.pct)}">${signed(b.pct)}</div>
      <div class="heat-flow">${signed(b.flow_yi, 2, "")}亿</div>
    </div>`).join("") || `<div class="subtitle">暂无数据</div>`;
  $("hmState").textContent = "已更新 " + (d.as_of || "--");
}

document.querySelectorAll(".heat-sort").forEach((btn) => {
  btn.addEventListener("click", () => {
    heatSort = btn.dataset.sort;
    document.querySelectorAll(".heat-sort").forEach((b) => b.classList.toggle("active", b === btn));
    if (lastData) renderHeatmap(lastData);
  });
});

/* ---------- 市场情绪周期表 ---------- */

const LEVELS = [
  [75, "亢奋", "#f04a4a"],
  [60, "活跃", "#ff9b5e"],
  [40, "中性", "#aab2c5"],
  [25, "低迷", "#3fae7e"],
  [0, "冰点", "#2fbf71"],
];

function levelColor(score) {
  for (const [th, , color] of LEVELS) {
    if (score >= th) return color;
  }
  return "#2fbf71";
}

function renderEmotionChart(rows) {
  if (!rows || rows.length < 2) {
    $("ehChart").innerHTML = `<div class="subtitle">暂无足够历史数据</div>`;
    return;
  }
  const W = 920, H = 200, PAD = 30;
  const minScore = 0, maxScore = 100;
  const x = (i) => PAD + i * (W - PAD * 2) / (rows.length - 1);
  const y = (s) => H - PAD - (s - minScore) / (maxScore - minScore) * (H - PAD * 2);
  const pts = rows.map((r, i) => `${x(i).toFixed(1)},${y(r.score).toFixed(1)}`).join(" ");
  const yGrid = [0, 25, 50, 75, 100].map((s) => `
    <line x1="${PAD}" x2="${W - PAD}" y1="${y(s)}" y2="${y(s)}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
    <text x="${PAD - 6}" y="${y(s) + 3}" text-anchor="end" font-size="10" fill="#8b93a7">${s}</text>`).join("");
  $("ehChart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">
    ${yGrid}
    <polyline points="${pts}" fill="none" stroke="#4c8dff" stroke-width="2.5"/>
    ${rows.map((r, i) => `<circle cx="${x(i)}" cy="${y(r.score)}" r="4" fill="${levelColor(r.score)}">
        <title>${esc(r.date)} 情绪${r.score}（${r.level}）</title></circle>`).join("")}
    ${rows.map((r, i) => `<text x="${x(i)}" y="${y(r.score) - 8}" text-anchor="middle" font-size="10" fill="#e6e9ef">${r.score}</text>`).join("")}
    ${rows.map((r, i) => `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" font-size="10" fill="#8b93a7">${r.date.slice(5)}</text>`).join("")}
  </svg>`;
}

function renderEmotionTable(rows) {
  if (!rows || !rows.length) {
    $("ehTable").innerHTML = `<div class="subtitle">暂无数据</div>`;
    return;
  }
  const body = [...rows].reverse().map((r) => `<tr>
      <td>${esc(r.date)}</td>
      <td class="num"><b style="color:${levelColor(r.score)}">${r.score}</b></td>
      <td style="color:${levelColor(r.score)}">${r.level}</td>
      <td class="num up">${r.zt}</td>
      <td class="num">${r.zb}</td>
      <td class="num down">${r.dt}</td>
      <td class="num">${r.max_lb}板</td>
      <td class="num">${r.jingjia}</td>
      <td class="num">${Math.round(r.up_ratio * 100)}%</td>
      <td class="num">${fmt(r.zhaban_rate)}%</td>
    </tr>`).join("");
  $("ehTable").innerHTML = `<table><thead><tr>
      <th>日期</th><th class="num">情绪分</th><th>等级</th><th class="num">涨停</th><th class="num">炸板</th>
      <th class="num">跌停</th><th class="num">最高连板</th><th class="num">竞价涨停</th><th class="num">上涨占比</th><th class="num">炸板率</th>
    </tr></thead><tbody>${body}</tbody></table>`;
}

function renderEmotion(d) {
  lastEmotion = d;
  const rows = d.rows || [];
  $("ehState").textContent = `最近 ${rows.length} 个交易日 · 情绪分=涨停25+炸板率20+连板15+竞价10+上涨占比20+跌停10 · 上涨占比为当日口径（历史接口不提供） · 更新 ${d.as_of || "--"}`;
  renderEmotionChart(rows);
  renderEmotionTable(rows);
}

async function loadEmotionHistory(force = false) {
  try {
    const url = apiUrl("/api/emotion_history", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderEmotion(d);
  } catch (e) {
    $("errors").textContent = "情绪周期表刷新失败：" + e.message;
  }
}

export async function loadHeatmap(force = false) {
  $("hmState").textContent = "更新中...";
  try {
    const url = apiUrl("/api/heatmap", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderHeatmap(d);
  } catch (e) {
    $("errors").textContent = "热力图刷新失败：" + e.message;
    $("hmState").textContent = "刷新失败";
  }
  await loadEmotionHistory(force);
}

