/* ---------- 开盘前瞻：隔夜美股 + 外围资产全景（A 股开盘前参考） ----------
 * 数据来自 /api/preopen（腾讯美股 + 东财全市场 + 新浪外盘，规则引擎客观生成）。
 * 界面仿参考设计：浅色专业报告风（深色导航区/评级徽章+温度计/双栏板块
 * 条形图/中概与外围传导表格/正负传导列表），支持精简/详细模式。
 */

import { $, apiUrl, esc, fmt, pctClass, signed } from "./utils.js";

let lastData = null;
let brief = false;

function barW(pct) {
  const v = Math.abs(Number(pct) || 0);
  return Math.min(100, (v / 6) * 100).toFixed(1);
}

function badgeCls(level) {
  if (level === "火热") return "hot";
  if (level === "温和") return "mild";
  if (level === "偏冷") return "cold";
  if (level === "极寒") return "frozen";
  return "mild";
}

function thermoPos(level) {
  if (level === "极寒") return "8%";
  if (level === "偏冷") return "30%";
  if (level === "温和") return "55%";
  if (level === "火热") return "82%";
  return "50%";
}

/* ---------- 页头 ---------- */

function renderHero(d) {
  const date = d.as_of ? d.as_of.slice(0, 10) : "--";
  $("poHero").innerHTML = `
    <h3>隔夜美股 + 外围资产全景前瞻</h3>
    <div class="rv-hero-sub">A股开盘前专业参考 · 数据为隔夜最新收盘口径 · 更新 ${esc(d.as_of || "--")}</div>
    <div class="rv-hero-concl">${esc(d.summary || "")}</div>`;
}

/* ---------- 一、美股核心指数概览 ---------- */

function renderIndices(d) {
  const idx = d.indices || [];
  $("poIndices").innerHTML = `<div class="rv-indices">` + idx.map((i) => `
    <div class="rv-idx">
      <div class="rv-idx-name">${esc(i.label || i.name)}</div>
      <div class="rv-idx-close">${fmt(i.price)}</div>
      <div class="rv-idx-pct ${pctClass(i.pct)}">${signed(i.pct)}</div>
      <div class="rv-idx-amt">开 ${fmt(i.open)} · 高 ${fmt(i.high)} · 低 ${fmt(i.low)}</div>
    </div>`).join("") + `</div>` || `<div class="subtitle">美股指数数据暂不可得</div>`;

  const m = d.market || {};
  const b = m.breadth || {};
  $("poMarket").innerHTML = `<div class="rv-stats">
    <div class="rv-stat">
      <span class="rv-stat-label">美股个股总成交</span>
      <span class="rv-stat-bar"><span class="rv-stat-fill" style="width:${m.total_amt_yi ? Math.min(100, m.total_amt_yi / 80 * 100) : 0}%;background:linear-gradient(90deg,#1565c0,#42a5f5)">${m.total_amt_yi ? "约 " + fmt(m.total_amt_yi) + " 亿美元" : "暂缺"}</span></span>
      <span class="rv-stat-val">东财近似口径</span>
    </div>
    <div class="rv-stat">
      <span class="rv-stat-label">环比前一交易日</span>
      <span class="rv-stat-bar"><span class="rv-stat-fill" style="width:46%;background:linear-gradient(90deg,#ef6c00,#ffb74d)">环比数据暂不可得</span></span>
      <span class="rv-stat-val" style="color:#8b95a7;font-weight:600">—</span>
    </div>
    <div class="rv-stat">
      <span class="rv-stat-label">市场宽度</span>
      <span class="rv-stat-bar"><span class="rv-stat-fill" style="width:${Math.max(4, Math.min(100, b.up_pct || 0))}%;background:${(b.up_pct || 0) >= 50 ? "linear-gradient(90deg,#e53935,#ef5350)" : "linear-gradient(90deg,#2e7d32,#4caf50)"}">上涨占比 ${fmt(b.up_pct, 1)}%</span></span>
      <span class="rv-stat-val">${b.up ?? "--"}/${b.down ?? "--"} 家</span>
    </div>
  </div>`;
  $("poRhythm").textContent = d.rhythm || "";
}

/* ---------- 二、美股市场情绪温度计 ---------- */

function renderEmotion(d) {
  const m = d.market || {};
  const b = m.breadth || {};
  const r = m.rating || {};
  const bar = (label, n, pct, cls, valTxt) => `
    <div class="rv-stat">
      <span class="rv-stat-label">${label}</span>
      <span class="rv-stat-bar"><span class="rv-stat-fill" style="width:${Math.max(3, Math.min(100, pct))}%;background:${cls}">${valTxt || n + " 家"}</span></span>
      <span class="rv-stat-val ${pctClass(pct - 50)}">${fmt(pct, 1)}%</span>
    </div>`;
  $("poEmotion").innerHTML = `
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px;flex-wrap:wrap">
      <span style="font-size:13px;color:#5a6577;font-weight:600">赚钱效应综合评级：</span>
      <span class="rv-badge ${badgeCls(r.level)}">${esc(r.level || "--")}</span>
      <span style="font-size:12.5px;color:#8b95a7">大幅异动(|≥10%|) ${b.wild ?? "--"} 家</span>
    </div>
    <div class="rv-thermo"><span class="ptr" style="left:${thermoPos(r.level)}"></span></div>
    <div class="rv-thermo-labels"><span>极寒</span><span>偏冷</span><span>温和</span><span>火热</span><span>极热</span></div>
    <div class="rv-two">
      <div>
        <h3 class="rv-sub">涨跌分布</h3>
        ${bar("上涨家数", b.up, b.up_pct, "linear-gradient(90deg,#e53935,#ef5350)")}
        ${bar("下跌家数", b.down, b.down_pct, "linear-gradient(90deg,#2e7d32,#4caf50)")}
        ${bar("平盘家数", b.flat, b.flat_pct, "#9ca3af")}
      </div>
      <div>
        <h3 class="rv-sub">涨跌波动</h3>
        ${bar("大涨股 (≥+5%)", b.big_up, Math.min(100, (b.big_up || 0) / 5), "linear-gradient(90deg,#e53935,#ef5350)", (b.big_up ?? "--") + " 家")}
        ${bar("大跌股 (≤-5%)", b.big_dn, Math.min(100, (b.big_dn || 0) / 5), "linear-gradient(90deg,#2e7d32,#4caf50)", (b.big_dn ?? "--") + " 家")}
        ${bar("大幅异动 (|≥10%|)", b.wild, Math.min(100, (b.wild || 0) / 5), "linear-gradient(90deg,#ef6c00,#ffb74d)", (b.wild ?? "--") + " 只")}
      </div>
    </div>
    <p class="rv-text" style="margin-top:10px">${esc(r.reason || "")}</p>`;
}

/* ---------- 三、美股板块轮动图谱 ---------- */

function usSectorList(rows, up) {
  if (!rows || !rows.length) return `<div class="subtitle">暂无数据</div>`;
  const maxAbs = Math.max(...rows.map((r) => Math.abs(Number(r.pct) || 0)), 0.01);
  return `<div class="rv-slist">` + rows.map((r) => {
    const w = Math.max(6, Math.min(100, Math.abs(Number(r.pct) || 0) / maxAbs * 100));
    return `<div class="rv-srow">
      <span class="rv-sname" title="${esc(r.name)}">${esc(r.name)}</span>
      <span class="rv-sbar-wrap"><span class="rv-sbar ${pctClass(r.pct)}" style="width:${w}%">${signed(r.pct)}</span></span>
      <span class="rv-spct ${pctClass(r.pct)}">${signed(r.pct)}</span>
      <span class="rv-sflow" title="${esc(r.leader || "")}">${r.leader ? "领涨 " + esc(r.leader) : (r.count ? r.count + " 只" : "")}</span>
    </div>`;
  }).join("") + `</div>`;
}

function renderSectors(d) {
  const s = d.sectors || {};
  $("poSectors").innerHTML = `
    <div class="rv-two">
      <div>
        <h3 class="rv-sub" style="color:#e53935">▲ 行业板块涨幅 TOP</h3>
        ${usSectorList(s.top, true)}
      </div>
      <div>
        <h3 class="rv-sub" style="color:#2e7d32">▼ 行业板块跌幅 TOP</h3>
        ${usSectorList(s.bottom, false)}
      </div>
    </div>
    <p class="rv-text" style="margin-top:12px"><b>隔夜板块核心特征：</b>${esc(s.feature || "")}</p>`;
}

/* ---------- 四、中概股 & 港股 ADR ---------- */

function renderCn(d) {
  const c = d.cn || {};
  const groups = c.groups || [];
  const rows = groups.map((g) => {
    const stocks = (g.stocks || []).map((s) => `${esc(s.name)} <span class="${pctClass(s.pct)}">${signed(s.pct)}</span>`).join("、");
    return `<tr>
      <td>${esc(g.group)}</td>
      <td>${stocks || "—"}</td>
      <td class="num ${pctClass(g.avg_pct)}">${signed(g.avg_pct)}</td>
      <td class="num">${(g.stocks || []).length}</td>
    </tr>`;
  }).join("");
  const etfs = (c.etfs || []).map((e) =>
    `<span class="rv-chip">${esc(e.name)} ${e.pct == null ? "--" : signed(e.pct)}</span>`).join("");
  $("poCn").innerHTML = `
    <table class="rv-table">
      <thead><tr><th>细分方向</th><th>代表标的（涨跌幅）</th><th class="num">组内均值</th><th class="num">家数</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="4">中概 ADR 数据暂不可得</td></tr>`}</tbody>
    </table>
    ${etfs ? `<div class="rv-ladder" style="margin-top:8px">${etfs}</div>` : ""}
    <p class="rv-text"><b>核心解读与 A 股传导：</b>${esc(c.verdict || "")}</p>`;
}

/* ---------- 五、外围关键资产联动 ---------- */

const FX_IMPACT = {
  "美元指数": "美元强弱影响人民币与外资风险偏好；美元走弱利好外资回流与黄金有色",
  "COMEX黄金": "金价方向映射 A 股贵金属/黄金板块",
  "离岸人民币(USDCNH)": "人民币升值利好外资流入、航空造纸；贬值则反之",
  "纽约原油": "油价映射 A 股油气链；下跌利好航空/化工成本",
  "美债20年+(TLT)": "长端收益率下行支撑成长股估值；上行压制高估值成长",
};

function renderFx(d) {
  const f = d.fx || {};
  const cards = (f.rows || []).map((r) => `
    <div class="rv-asset">
      <div class="name">${esc(r.name)}</div>
      <div class="price">${r.price == null ? "--" : fmt(r.price, 2)}</div>
      <div class="chg ${pctClass(r.pct)}">${r.pct == null ? "--" : signed(r.pct)}</div>
    </div>`).join("");
  const trows = (f.rows || []).map((r) => `
    <tr>
      <td>${esc(r.name)}</td>
      <td class="num">${r.price == null ? "--" : fmt(r.price, 2)}</td>
      <td class="num ${pctClass(r.pct)}">${r.pct == null ? "--" : signed(r.pct)}</td>
      <td>${esc(FX_IMPACT[r.name] || (r.note || ""))}</td>
    </tr>`).join("");
  $("poFx").innerHTML = `
    <div class="rv-asset-grid">${cards || `<div class="subtitle">外围资产数据暂不可得</div>`}</div>
    <div class="rv-table-scroll">
      <table class="rv-table">
        <thead><tr><th>资产品种</th><th class="num">收盘</th><th class="num">涨跌幅</th><th>对 A 股潜在传导影响</th></tr></thead>
        <tbody>${trows}</tbody>
      </table>
    </div>
    <p class="rv-text" style="margin-top:8px"><b>综合传导：</b>${esc(f.verdict || "")}</p>`;
}

/* ---------- 六、主线与强弱研判 ---------- */

function renderMainline(d) {
  const m = d.mainline || {};
  const side = (m.side || []).map((s) => `${esc(s.name)}(${signed(s.pct)})`).join("、");
  const weak = (m.weak || []).map((s) => `${esc(s.name)}(${signed(s.pct)})`).join("、");
  const items = (m.impact_a || "").split("；").filter((x) => x.trim());
  const transmit = items.map((t) => {
    const neg = /承压|压制|退潮|偏负面|负向/.test(t);
    return `<li><span class="arrow ${neg ? "neg" : "pos"}">${neg ? "→" : "→"}</span><div>${esc(t)}</div></li>`;
  }).join("");
  $("poMainline").innerHTML = `
    <div class="rv-two">
      <div>
        <h3 class="rv-sub" style="color:#e53935">🔥 隔夜核心主线（上涨）</h3>
        <div class="rv-pos-neg pos">
          <div style="font-weight:700;font-size:13.5px;margin-bottom:4px">${esc(m.main || "--")}</div>
          <div style="font-size:12.5px;color:#5a6577">${esc(m.logic || "")}</div>
          <div style="font-size:12.5px;color:#5a6577;margin-top:4px"><strong>持续性：</strong>${esc(m.persist || "")}</div>
          ${side ? `<div style="font-size:12.5px;color:#5a6577;margin-top:4px"><strong>活跃支线：</strong>${side}</div>` : ""}
        </div>
      </div>
      <div>
        <h3 class="rv-sub" style="color:#2e7d32">❄️ 隔夜走弱退潮（下跌）</h3>
        <div class="rv-pos-neg neg">
          ${weak ? `<div style="font-size:12.5px;color:#5a6577;line-height:1.9">${weak}</div>` : `<div style="font-size:12.5px;color:#5a6577">今日无显著走弱板块</div>`}
        </div>
      </div>
    </div>
    <p class="rv-text" style="margin-top:10px"><b>美股市场风格：</b>${esc(m.style || "")}</p>
    <ul class="rv-transmit">
      <li style="border-bottom:none;font-weight:700"><span class="arrow pos">→</span><div>美股情绪 → 今日 A 股开盘传导：</div></li>
      ${transmit || `<li><span class="arrow pos">→</span><div>${esc(m.impact_a || "传导信号暂不显著。")}</div></li>`}
    </ul>`;
}

/* ---------- 七、行情阶段客观解读 ---------- */

function renderStage(d) {
  const s = d.stage || {};
  $("poStage").innerHTML = `
    <div class="rv-phase">阶段判定：<b>${esc(s.phase || "--")}</b></div>
    <div class="rv-two">
      <div>
        <h3 class="rv-sub">📈 美股技术形态</h3>
        <p class="rv-text" style="margin-top:0">${esc(s.tech || "")}</p>
      </div>
      <div>
        <h3 class="rv-sub">🔑 核心驱动与矛盾</h3>
        <p class="rv-text" style="margin-top:0"><strong>核心驱动：</strong>${esc(s.drivers || "")}</p>
        <p class="rv-text"><strong>核心矛盾：</strong>${esc(s.contradiction || "")}</p>
      </div>
    </div>
    <div class="rv-pos-neg pos" style="background:linear-gradient(135deg,#e3f2fd,#bbdefb);margin-top:12px">
      <div style="font-size:13px;font-weight:700;margin-bottom:6px;color:#1565c0">🔮 对今日 A 股开盘潜在影响推演</div>
      <div style="font-size:13px;color:#3a4356;line-height:1.8">${esc(s.focus || "")}</div>
    </div>`;
}

/* ---------- 前瞻总结 ---------- */

function renderSummary(d) {
  const items = (d.mainline && d.mainline.impact_a || "").split("；").filter((x) => x.trim());
  const pos = items.filter((t) => !/承压|压制|退潮|偏负面|负向/.test(t));
  const neg = items.filter((t) => /承压|压制|退潮|偏负面|负向/.test(t));
  $("poSummary").innerHTML = `
    <div class="rv-summary-box">
      <div class="label">📌 一句话提炼</div>
      <div class="text">${esc(d.summary || "")}</div>
    </div>
    <div class="rv-two">
      <div class="rv-pos-neg pos">
        <h4 style="font-size:13px;color:#e53935;margin-bottom:6px">✅ 正向关注方向</h4>
        <ul style="font-size:12.5px;color:#5a6577;padding-left:18px;line-height:1.9;margin:0">${pos.map((t) => `<li>${esc(t)}</li>`).join("") || "<li>暂无显著正向传导</li>"}</ul>
      </div>
      <div class="rv-pos-neg neg">
        <h4 style="font-size:13px;color:#2e7d32;margin-bottom:6px">⚠️ 风险规避方向</h4>
        <ul style="font-size:12.5px;color:#5a6577;padding-left:18px;line-height:1.9;margin:0">${neg.map((t) => `<li>${esc(t)}</li>`).join("") || "<li>暂无显著负向传导</li>"}</ul>
      </div>
    </div>
    <div class="rv-risk-box">
      <h4>⚠️ 风险提示</h4>
      <p>${esc(d.risk || "")}</p>
    </div>`;
}

function render(d) {
  lastData = d;
  $("poState").innerHTML = `更新于 ${esc(d.as_of || "--")}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
  renderHero(d);
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
