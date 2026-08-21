/* ---------- 全球宏观：全球股指/外汇/债券/大宗商品/跨资产联动全景 ----------
 * 数据来自 /api/globalmac（东财全球行情 + 腾讯美股 + 新浪外盘/国内期货）。
 * 复用暗色报告组件（rv-hero/rv-asset-grid/rv-table/rv-pos-neg 等）。
 */

import { $, apiUrl, esc, fmt, pctClass, signed } from "./utils.js";

let lastData = null;
let brief = false;

function idxCard(i) {
  return `
    <div class="rv-idx">
      <div class="rv-idx-name">${esc(i.name)}${i.note ? ` <span class="rv-tag">代理</span>` : ""}</div>
      <div class="rv-idx-close">${i.price == null ? "--" : fmt(i.price)}</div>
      <div class="rv-idx-pct ${pctClass(i.pct)}">${i.pct == null ? "--" : signed(i.pct)}</div>
      ${i.high != null ? `<div class="rv-idx-amt">高 ${fmt(i.high)} · 低 ${fmt(i.low)}</div>` : ""}
    </div>`;
}

function assetCard(r) {
  return `
    <div class="rv-asset">
      <div class="name">${esc(r.name)}</div>
      <div class="price">${r.price == null ? "--" : fmt(r.price, 2)}</div>
      <div class="chg ${pctClass(r.pct)}">${r.pct == null ? "--" : signed(r.pct)}</div>
      ${r.note ? `<div class="rv-idx-amt" style="margin-top:4px">${esc(r.note)}</div>` : ""}
    </div>`;
}

/* ---------- 页头 ---------- */

function renderHero(d) {
  $("gmHero").innerHTML = `
    <h3>全球宏观资产全景速览</h3>
    <div class="rv-hero-sub">全球股指 · 外汇 · 债券 · 大宗商品 · 跨资产联动 · 更新 ${esc(d.as_of || "--")}</div>
    <div class="rv-hero-concl">${esc(d.summary || "")}</div>`;
}

/* ---------- 一、全球股指 ---------- */

function renderIndices(d) {
  const idx = d.indices || {};
  $("gmRisk").textContent = "全球风险偏好：" + (idx.risk || "--");
  $("gmA50").innerHTML = `<div class="rv-indices">${idx.a50 ? idxCard(idx.a50) : `<div class="subtitle">A50 数据暂不可得</div>`}</div>`;
  $("gmEu").innerHTML = `<div class="rv-indices">${(idx.eu || []).map(idxCard).join("") || `<div class="subtitle">暂无数据</div>`}</div>`;
  $("gmApac").innerHTML = `<div class="rv-indices">${(idx.apac || []).map(idxCard).join("") || `<div class="subtitle">暂无数据</div>`}</div>`;
}

/* ---------- 二、外汇 ---------- */

function renderFx(d) {
  const f = d.fx || {};
  $("gmFx").innerHTML = `<div class="rv-asset-grid">${(f.rows || []).map(assetCard).join("") || `<div class="subtitle">外汇数据暂不可得</div>`}</div>`;
  $("gmFxVerdict").innerHTML = `<b>外汇主线：</b>${esc(f.verdict || "")}`;
}

/* ---------- 三、债券 ---------- */

function renderBonds(d) {
  const b = d.bonds || {};
  $("gmBonds").innerHTML = `
    <div class="rv-asset-grid">${(b.rows || []).map(assetCard).join("") || `<div class="subtitle">债券数据暂不可得</div>`}</div>
    <p class="rv-text"><b>2Y/10Y 利差方向：</b>${esc(b.spread || "")}</p>
    <p class="rv-text rv-note">${esc(b.note || "")}</p>`;
  $("gmBondsVerdict").innerHTML = `<b>传导影响：</b>${esc(b.verdict || "")}`;
}

/* ---------- 四、大宗商品 ---------- */

function renderComm(d) {
  const c = d.commodities || {};
  $("gmComm").innerHTML = `<div class="rv-asset-grid">${(c.rows || []).map(assetCard).join("") || `<div class="subtitle">大宗商品数据暂不可得</div>`}</div>`;
  $("gmCommVerdict").innerHTML = `<b>强弱格局：</b>${esc(c.verdict || "")}`;
}

/* ---------- 五、宏观日历 ---------- */

function renderCalendar(d) {
  const c = d.calendar || {};
  $("gmCalendar").innerHTML = `
    <p class="rv-text">${esc(c.note || "")}</p>
    <div class="rv-pos-neg pos" style="margin-top:8px">
      <div style="font-size:13px;font-weight:700;margin-bottom:4px;color:#7ec3ff">📅 关注方向</div>
      <div style="font-size:12.5px;line-height:1.8">${esc(c.focus || "")}</div>
    </div>`;
}

/* ---------- 六、跨资产联动与宏观研判 ---------- */

function renderLinkage(d) {
  const l = d.linkage || {};
  $("gmLinkage").innerHTML = `
    <div class="rv-phase">宏观阶段：<b>${esc(l.phase || "--")}</b></div>
    <p class="rv-text"><b>跨资产联动：</b>${esc(l.linkage || "")}</p>
    <p class="rv-text"><b>核心驱动：</b>${esc(l.drivers || "")}</p>
    <p class="rv-text"><b>核心矛盾：</b>${esc(l.contradiction || "")}</p>
    <p class="rv-text"><b>短期推演：</b>${esc(l.outlook || "")}</p>`;
}

/* ---------- 总结 ---------- */

function renderSummary(d) {
  $("gmSummary").innerHTML = `
    <div class="rv-summary-box">
      <div class="label">当日全球宏观核心结论</div>
      <div class="text">${esc(d.summary || "")}</div>
    </div>
    <div class="rv-risk-box">
      <h4>⚠️ 风险提示</h4>
      <p>${esc(d.risk || "")}</p>
    </div>`;
}

function render(d) {
  lastData = d;
  $("gmState").innerHTML = `更新于 ${esc(d.as_of || "--")}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
  renderHero(d);
  renderIndices(d);
  renderFx(d);
  renderBonds(d);
  renderComm(d);
  renderCalendar(d);
  renderLinkage(d);
  renderSummary(d);
}

export async function loadGlobalmac(force = false) {
  $("gmState").textContent = "更新中...";
  try {
    const url = apiUrl("/api/globalmac", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    render(d);
  } catch (e) {
    $("gmState").textContent = "刷新失败：" + e.message;
    $("errors").textContent = "全球宏观刷新失败：" + e.message;
  }
}

/* ---------- 精简 / 详细模式 ---------- */

function setBrief(v) {
  brief = v;
  $("#page-globalmac").classList.toggle("brief", v);
  $("#gmMode").textContent = v ? "详细模式" : "精简模式";
}

$("gmMode").addEventListener("click", () => setBrief(!brief));
