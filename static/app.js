/* A股每日复盘 + 实时盘口 */
const $ = (id) => document.getElementById(id);

let auto = true;
let timer = null;
let activeTab = "daily";

function esc(v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fmt(v, digits = 2) {
  if (v == null || isNaN(v)) return "--";
  return Number(v).toFixed(digits);
}

function pctClass(v) {
  if (v > 0) return "up";
  if (v < 0) return "down";
  return "flat";
}

function signed(v, digits = 2, suffix = "%") {
  if (v == null || isNaN(v)) return "--";
  const s = Number(v) > 0 ? "+" : "";
  return s + Number(v).toFixed(digits) + suffix;
}

function toYi(v) {
  const n = Number(v);
  return isNaN(n) ? 0 : n / 100000000;
}

/* ---------- 每日复盘 ---------- */

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

function renderSignals(d, target = "signals") {
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

function boardTable(rows, extra = "") {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  const head = `<tr><th>板块</th><th class="num">涨跌</th><th class="num">主力(亿)</th><th class="num">领涨</th></tr>`;
  const body = rows.map((r) => `
    <tr>
      <td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num ${pctClass(r.flow_yi)}">${signed(r.flow_yi, 2, "")}</td>
      <td>${esc(r.leader || "--")}</td>
    </tr>`).join("");
  return `<table><thead>${head}</thead><tbody>${body}</tbody></table>${extra}`;
}

function renderSectors(d) {
  const s = d.sectors || {};
  let html = `<div class="subtitle">行业 · 涨幅TOP8</div>`;
  html += boardTable((s.industry_top_pct || []).slice(0, 8));
  html += `<div class="subtitle">行业 · 主力净流入TOP8</div>`;
  html += boardTable((s.industry_top_flow || []).slice(0, 8));
  html += `<div class="subtitle">概念 · 主力净流入TOP8</div>`;
  html += boardTable((s.concept_top_flow || []).slice(0, 8));
  $("sectors").innerHTML = html;
}

function flowTable(rows) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  const head = `<tr><th>代码</th><th>名称</th><th class="num">涨跌</th><th class="num">主力(亿)</th><th class="num">成交(亿)</th></tr>`;
  const body = rows.map((r) => `
    <tr>
      <td>${esc(r.code)}</td>
      <td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num ${pctClass(r.flow_yi)}">${signed(r.flow_yi, 2, "")}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
    </tr>`).join("");
  return `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function renderFlows(d) {
  const f = d.flows || {};
  $("flows").innerHTML =
    `<div class="subtitle">主力净流入 TOP10</div>` + flowTable((f.inflow || []).slice(0, 10)) +
    `<div class="subtitle">主力净流出 TOP10</div>` + flowTable((f.outflow || []).slice(0, 10));
}

function renderZt(d) {
  const z = d.zt_summary || {};
  const byBoard = (z.by_board || []).slice(0, 8);
  let html = `<div class="subtitle">涨停行业分布 TOP8</div>`;
  html += `<table><thead><tr><th>行业</th><th class="num">家数</th><th class="num">封单(亿)</th><th class="num">最高连板</th></tr></thead><tbody>` +
    byBoard.map((r) => `<tr><td>${esc(r.name)}</td><td class="num up">${r.count}</td><td class="num">${fmt(r.fund_yi)}</td><td class="num">${r.max_lb}板</td></tr>`).join("") +
    `</tbody></table>`;

  html += `<div class="subtitle">观察池（连板 / 主力资金）</div>`;
  const w = (d.watchlist || []).slice(0, 15);
  html += `<table><thead><tr><th>代码</th><th>名称</th><th class="num">涨跌</th><th class="num">连板</th><th class="num">封单/主力(亿)</th><th>首封</th></tr></thead><tbody>` +
    w.map((r) => `<tr>
      <td>${esc(r.code)}</td><td>${esc(r.name)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num">${r.lbc ? `<span class="badge lb">${r.lbc}板</span>` : "--"}</td>
      <td class="num">${fmt(r.flow_yi)}</td>
      <td>${r.fbt ? esc(String(r.fbt)) : "--"}</td>
    </tr>`).join("") +
    `</tbody></table>`;

  const auction = (z.auction || []).slice(0, 5);
  html += `<div class="subtitle">竞价(09:25)封板</div>`;
  html += `<table><thead><tr><th>代码</th><th>名称</th><th class="num">封单(亿)</th><th>行业</th></tr></thead><tbody>` +
    auction.map((r) => `<tr><td>${esc(r.c)}</td><td>${esc(r.n)}</td><td class="num">${fmt(toYi(r.fund))}</td><td>${esc(r.hybk || "")}</td></tr>`).join("") +
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

function renderErrors(d) {
  $("errors").textContent = (d.errors && d.errors.length) ? "部分数据获取失败：" + d.errors.join(" | ") : "";
}

function render(d) {
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

async function load(force = false) {
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

/* ---------- 实时盘口 ---------- */

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

async function loadRealtime(force = false) {
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

/* ---------- 量价异动 ---------- */

function vpBoardChips(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const e = m.emotion || {};
  const idx = (m.indices || []).map((i) => `${esc(i.name)} ${signed(i.pct)}`).join(" / ");
  $("vpMarket").innerHTML = `<div class="emotion">` + ["指数 " + idx, `上涨 ${b.up || 0} / 下跌 ${b.down || 0}`, `涨停 ${e.zt || 0} / 炸板 ${e.zb || 0}`, `最高 ${e.max_lb || 0}板 · 炸板率 ${fmt(e.zhaban_rate)}%`, `两市成交 ${fmt(m.amount_yi)}亿`].map((c) => `<span class="chip">${c}</span>`).join("") + `</div>`;
}

function vpBoardTable(d) {
  const rows = (d.strong_boards || []).slice(0, 8).map((b) => `
    <tr><td>${esc(b.name)}</td><td class="num ${pctClass(b.pct)}">${signed(b.pct)}</td><td class="num ${pctClass(b.flow_yi)}">${signed(b.flow_yi, 2, "")}</td></tr>`).join("");
  $("vpBoards").innerHTML = `<div class="subtitle">板块主力净流入 TOP8</div><table><thead><tr><th>板块</th><th class="num">涨跌</th><th class="num">主力(亿)</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function vpTable(stocks) {
  if (!stocks || !stocks.length) return `<div class="subtitle">暂无</div>`;
  return `<table><thead><tr><th>代码</th><th>名称</th><th class="num">涨跌</th><th class="num">涨速</th><th class="num">量比</th><th class="num">换手</th><th class="num">成交(亿)</th><th class="num">主力(亿)</th><th>板块</th><th class="num">MA20</th><th class="num">5日量比</th><th class="num">20日新高</th><th>信号</th></tr></thead><tbody>` +
    stocks.map((s) => `<tr>
      <td>${esc(s.code)}</td><td>${esc(s.name)}</td>
      <td class="num ${pctClass(s.pct)}">${signed(s.pct)}</td>
      <td class="num ${pctClass(s.speed)}">${signed(s.speed)}</td>
      <td class="num">${fmt(s.vol_ratio)}</td>
      <td class="num">${fmt(s.turnover)}%</td>
      <td class="num">${fmt(s.amount_yi)}</td>
      <td class="num ${pctClass(s.main_flow)}">${signed(s.main_flow, 2, "")}</td>
      <td>${esc(s.industry || "--")}</td>
      <td class="num">${s.ma20 ? fmt(s.ma20) : "--"}</td>
      <td class="num">${s.hist_vol_ratio == null ? "--" : fmt(s.hist_vol_ratio)}</td>
      <td class="num">${s.break_high20 == null ? "--" : (s.break_high20 ? "是" : "否")}</td>
      <td>${(s.tags || []).map((t) => `<span class="alert-tag">${esc(t)}</span>`).join("")}</td>
    </tr>`).join("") + `</tbody></table>`;
}

function renderVolPrice(d) {
  vpBoardChips(d);
  vpBoardTable(d);
  const cats = d.categories || {};
  const order = ["放量上攻", "放量滞涨", "冲高回落", "缩量上涨", "放量下跌", "缩量回踩"];
  let html = `<div class="subtitle">扫描 ${d.total_scanned || 0} 只候选</div>`;
  for (const name of order) {
    const list = cats[name] || [];
    html += `<div class="subtitle">${name}（${list.length}）</div>`;
    html += vpTable(list);
  }
  $("vpCategories").innerHTML = html;
  $("vpState").textContent = "已更新 " + (d.as_of || "--");
}

async function loadVolPrice(force = false) {
  $("vpState").textContent = "更新中...";
  try {
    const url = force ? "/api/volprice_refresh" : "/api/volprice";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    renderVolPrice(d);
  } catch (e) {
    $("errors").textContent = "量价异动刷新失败：" + e.message;
    $("vpState").textContent = "刷新失败";
  }
}

function switchTab(name) {
  activeTab = name;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $("page-daily").classList.toggle("hidden", name !== "daily");
  $("page-realtime").classList.toggle("hidden", name !== "realtime");
  if (name === "realtime") loadRealtime(true);
  $("page-volprice").classList.toggle("hidden", name !== "volprice");
  if (name === "volprice") loadVolPrice(true);
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

function startAuto() {
  if (timer) clearInterval(timer);
  timer = setInterval(() => {
    if (!auto) return;
    if (activeTab === "realtime") loadRealtime(false);
    else if (activeTab === "volprice") loadVolPrice(false);
    else load(false);
  }, 30000);
}

$("refreshBtn").addEventListener("click", () => {
  if (activeTab === "realtime") loadRealtime(true);
  else if (activeTab === "volprice") loadVolPrice(true);
  else load(true);
});
$("autoBtn").addEventListener("click", () => {
  auto = !auto;
  $("autoBtn").classList.toggle("active", auto);
  $("refreshState").textContent = auto ? "自动刷新 30s" : "已暂停自动刷新";
});

startAuto();
load(true);
