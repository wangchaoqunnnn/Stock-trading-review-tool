/* A股每日复盘前端逻辑 */
const $ = (id) => document.getElementById(id);

let auto = true;
let timer = null;

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

function renderSignals(d) {
  const items = (d.signals || []).map((s) => {
    const cls = s.ok ? "ok" : "no";
    const mark = s.ok ? "✓" : "✕";
    return `<div class="signal ${cls}">
      <span class="mark">${mark}</span>
      <span class="name">${esc(s.name)}</span>
      <span class="detail">${esc(s.detail)}</span>
    </div>`;
  }).join("");
  $("signals").innerHTML = `<div class="signal-list">${items || "暂无信号数据"}</div>`;
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

function toYi(v) {
  const n = Number(v);
  return isNaN(n) ? 0 : n / 100000000;
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

function startAuto() {
  if (timer) clearInterval(timer);
  timer = setInterval(() => { if (auto) load(false); }, 30000);
}

$("refreshBtn").addEventListener("click", () => load(true));
$("autoBtn").addEventListener("click", () => {
  auto = !auto;
  $("autoBtn").classList.toggle("active", auto);
  $("refreshState").textContent = auto ? "自动刷新 30s" : "已暂停自动刷新";
});

startAuto();
load(true);
