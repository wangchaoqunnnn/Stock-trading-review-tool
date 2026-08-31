/* ---------- 实时板块变动：领涨领跌 / 5分钟涨速榜 / 异动时间线 / 大盘归因 ---------- */

import { $, apiUrl, esc, fmt, pctClass, signed } from "./utils.js";

let lastData = null;

function boardList(rows, up) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  const maxAbs = Math.max(...rows.map((r) => Math.abs(Number(r.pct) || 0)), 0.01);
  return `<div class="rv-slist">` + rows.map((r, i) => {
    const w = Math.max(6, Math.min(100, Math.abs(Number(r.pct) || 0) / maxAbs * 100));
    const flow = r.flow_yi == null ? "" : (r.flow_yi >= 0 ? "+" : "") + fmt(r.flow_yi, 1) + "亿";
    return `<div class="rv-srow">
      <span class="rv-srank ${up ? "r" : "g"}${Math.min(3, i + 1)}">${i + 1}</span>
      <span class="rv-sname" title="${esc(r.name)}">${esc(r.name)}<span class="rv-tag">${r.type}</span></span>
      <span class="rv-sbar-wrap"><span class="rv-sbar ${pctClass(r.pct)}" style="width:${w}%">${signed(r.pct)}</span></span>
      <span class="rv-spct ${pctClass(r.pct)}">${signed(r.pct)}</span>
      <span class="rv-sflow">${r.leader ? esc(r.leader) : flow}</span>
    </div>`;
  }).join("") + `</div>`;
}

function speedList(rows, up) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无（板块内异动股不足）</div>`;
  return `<table class="rv-table"><thead><tr>
    <th>板块</th><th class="num">5分钟涨速</th><th class="num">异动股数</th><th class="num">板块成交(亿)</th></tr></thead><tbody>` +
    rows.map((r) => `<tr>
      <td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.speed)}">${signed(r.speed)}</td>
      <td class="num">${r.up_stocks}/${r.down_stocks}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
    </tr>`).join("") + `</tbody></table>`;
}

/* ---------- 大盘归因 ---------- */

function renderAttribution(d) {
  const a = d.attribution;
  if (!a) {
    $("smAttribution").textContent = "归因数据暂不可得。";
    $("smAttrList").innerHTML = "";
    return;
  }
  $("smAttribution").innerHTML = `<b>${esc(a.summary)}</b>`;
  const row = (r) => `<tr>
      <td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num">${fmt(r.weight)}%</td>
      <td class="num ${pctClass(r.contrib)}">${r.contrib >= 0 ? "+" : ""}${fmt(r.contrib, 2)}%</td>
    </tr>`;
  $("smAttrList").innerHTML = `
    <div class="rv-two">
      <div>
        <h3 class="rv-sub" style="color:#f04a4a">▲ 拉动板块（贡献度前 6）</h3>
        <table class="rv-table"><thead><tr><th>板块</th><th class="num">涨跌幅</th><th class="num">成交占比</th><th class="num">贡献度</th></tr></thead>
        <tbody>${(a.up || []).filter((r) => r.contrib > 0).map(row).join("") || `<tr><td colspan="4">无</td></tr>`}</tbody></table>
      </div>
      <div>
        <h3 class="rv-sub" style="color:#2fbf71">▼ 拖累板块（贡献度后 6）</h3>
        <table class="rv-table"><thead><tr><th>板块</th><th class="num">涨跌幅</th><th class="num">成交占比</th><th class="num">贡献度</th></tr></thead>
        <tbody>${(a.down || []).filter((r) => r.contrib < 0).map(row).join("") || `<tr><td colspan="4">无</td></tr>`}</tbody></table>
      </div>
    </div>`;
}

/* ---------- 领涨领跌 ---------- */

function renderLeaders(d) {
  const l = d.leaders || {};
  $("smLeaders").innerHTML = `
    <div class="rv-two">
      <div>
        <h3 class="rv-sub" style="color:#f04a4a">▲ 当前领涨板块 TOP10</h3>
        ${boardList(l.top, true)}
      </div>
      <div>
        <h3 class="rv-sub" style="color:#2fbf71">▼ 当前领跌板块 TOP10</h3>
        ${boardList(l.bottom, false)}
      </div>
    </div>`;
}

/* ---------- 5分钟涨速榜 ---------- */

function renderSpeed(d) {
  const s = d.speed5 || {};
  $("smSpeed").innerHTML = `
    <div class="rv-two">
      <div>
        <h3 class="rv-sub" style="color:#f04a4a">▲ 5 分钟上涨前 5</h3>
        ${speedList(s.up, true)}
      </div>
      <div>
        <h3 class="rv-sub" style="color:#2fbf71">▼ 5 分钟下跌前 5</h3>
        ${speedList(s.down, false)}
      </div>
    </div>
    <p class="rv-text rv-note" style="margin-top:8px">口径：全市场个股 5 分钟涨速（东财 f22）按板块聚合，板块内异动股 ≥2 只才计入。</p>`;
}

/* ---------- 异动与时间线 ---------- */

function renderSurge(d) {
  const now = (d.surge || []).map((s) => {
    const cls = s.direction === "up" ? "up" : "down";
    return `<span class="rv-chip" style="${s.direction === "up" ? "border-color:rgba(240,74,74,.5);color:#ff9c9c" : "border-color:rgba(47,191,113,.5);color:#8fd8b8"}">${esc(s.name)} ${s.direction === "up" ? "异动拉升" : "异动跳水"} ${signed(s.speed)}（${s.count}股）</span>`;
  }).join("");
  $("smSurgeNow").innerHTML = now
    ? `<b>当前异动板块：</b><span class="rv-ladder">${now}</span>`
    : "当前无显著异动板块（5分钟涨速 ≥1% 且异动股 ≥2 只）。";

  const tl = d.timeline || [];
  $("smTimeline").innerHTML = tl.length ? `<table class="rv-table"><thead><tr>
      <th>时间</th><th>板块</th><th class="num">方向</th><th class="num">异动幅度</th><th class="num">异动股数</th></tr></thead><tbody>` +
    [...tl].reverse().map((t) => `<tr>
      <td>${esc(t.time)}</td>
      <td>${esc(t.name)}</td>
      <td class="num ${t.direction === "up" ? "up" : "down"}">${t.direction === "up" ? "拉升" : "跳水"}</td>
      <td class="num ${t.direction === "up" ? "up" : "down"}">${signed(t.speed)}</td>
      <td class="num">${t.count}</td>
    </tr>`).join("") + `</tbody></table>`
    : `<div class="subtitle">暂无异动记录（检测到板块异动后自动记录时间线）</div>`;
}

function render(d) {
  lastData = d;
  $("smState").innerHTML = `更新于 ${esc(d.as_of || "--")}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
  $("smHero").innerHTML = `
    <h3>实时板块变动</h3>
    <div class="rv-hero-sub">领涨领跌 · 5分钟涨速 · 异动时间线 · 大盘涨跌归因 · 每30秒自动刷新</div>
    <div class="rv-hero-concl">看大盘为什么涨跌——由哪些板块拉动/拖累，哪些板块正在异动。</div>`;
  renderAttribution(d);
  renderLeaders(d);
  renderSpeed(d);
  renderSurge(d);
}

export async function loadSectorMv(force = false) {
  $("smState").textContent = "更新中...";
  try {
    const url = apiUrl("/api/sectormv", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    render(d);
  } catch (e) {
    $("smState").textContent = "刷新失败：" + e.message;
    $("errors").textContent = "板块变动刷新失败：" + e.message;
  }
}
