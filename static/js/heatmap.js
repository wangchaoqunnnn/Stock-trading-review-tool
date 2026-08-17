/* ---------- 市场热力图（行业板块涨跌色块） ---------- */

import { $, esc, fmt, pctClass, signed } from "./utils.js";

let lastData = null;
let heatSort = "pct"; // 排序字段：pct 涨跌幅 / flow 主力资金

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

export async function loadHeatmap(force = false) {
  $("hmState").textContent = "更新中...";
  try {
    const url = force ? "/api/heatmap_refresh" : "/api/heatmap";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderHeatmap(d);
  } catch (e) {
    $("errors").textContent = "热力图刷新失败：" + e.message;
    $("hmState").textContent = "刷新失败";
  }
}
