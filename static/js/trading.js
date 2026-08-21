/* ---------- 交易策略：可执行交易系统 + 实时信号股票池 ----------
 * 数据来自 /api/trading：交易系统定义（含真实回测数据）+
 * 基于系统信号的实时股票池（加入时间/看多理由/所属板块）。
 * 复用暗色报告组件。
 */

import { $, apiUrl, esc, fmt, signed } from "./utils.js";

let lastData = null;
let brief = false;

/* ---------- 页头 ---------- */

function renderHero(d) {
  $("tdHero").innerHTML = `
    <h3>交易策略 · 可执行交易系统与股票池</h3>
    <div class="rv-hero-sub">回测验证 · 高胜率买点 · 实时信号股票池 · 更新 ${esc(d.as_of || "--")}</div>
    <div class="rv-hero-concl">${esc(d.summary || "")}</div>`;
}

/* ---------- 一、交易系统 ---------- */

function sysCard(s) {
  const bt = s.backtest || {};
  const entries = (s.entry || []).map((e) => `<li>${esc(e)}</li>`).join("");
  return `
    <div class="rv-theme main" style="margin-bottom:16px">
      <h4><span class="dot"></span>${esc(s.name)} <span class="rv-tag">${esc(s.style || "")}</span></h4>
      <div class="content">
        <p>${esc(s.summary || "")}</p>
        <p style="margin-top:6px"><strong>入场条件：</strong></p>
        <ul style="margin:4px 0 8px;padding-left:18px;line-height:1.9">${entries}</ul>
        <p><strong>止损：</strong>${esc(s.stop || "")}</p>
        <p><strong>止盈/出场：</strong>${esc(s.target || "")}</p>
        <p><strong>仓位：</strong>${esc(s.position || "")}</p>
        <p style="margin-top:8px"><strong>回测数据（${esc(bt.note || "")}）：</strong></p>
        <table class="rv-table" style="max-width:520px">
          <thead><tr><th>指标</th><th class="num">信号数</th><th class="num">3日胜率</th><th class="num">5日胜率</th><th class="num">5日均收</th><th class="num">不创新低</th></tr></thead>
          <tbody><tr>
            <td>${esc(s.name)}</td>
            <td class="num">${bt.signals ?? "--"}</td>
            <td class="num">${esc(bt.win3 || "--")}</td>
            <td class="num">${esc(bt.win5 || "--")}</td>
            <td class="num">${esc(bt.avg5 || "--")}</td>
            <td class="num">${esc(bt.no_lower || "--")}</td>
          </tr></tbody>
        </table>
        <p class="rv-text" style="margin-top:4px"><strong>对应页面：</strong>${esc(s.source || "")}</p>
      </div>
    </div>`;
}

function renderSystems(d) {
  $("tdSystems").innerHTML = (d.systems || []).map(sysCard).join("");
  const unused = (d.unused_systems || []).map((u) =>
    `<li><strong>${esc(u.name)}</strong>：${esc(u.reason)}</li>`).join("");
  $("tdUnused").innerHTML = unused ? `<b>回测不达标、不采用的系统：</b><ul style="margin:6px 0;padding-left:18px;line-height:1.8">${unused}</ul>` : "";
}

/* ---------- 二、股票池 ---------- */

function renderPool(d) {
  const pool = d.pool || [];
  $("tdPoolState").textContent = `共 ${d.pool_count ?? pool.length} 只信号股（实时扫描，10分钟刷新）· 股票池仅供策略跟踪研究，非推荐买入`;
  const bySys = {};
  for (const r of pool) {
    (bySys[r.system_id] = bySys[r.system_id] || []).push(r);
  }
  const order = (d.systems || []).map((s) => s.id);
  const blocks = Object.keys(bySys).sort((a, b) => order.indexOf(a) - order.indexOf(b)).map((sid) => {
    const rows = bySys[sid];
    const name = rows[0]?.system_name || sid;
    const tbody = rows.map((r) => `
      <tr>
        <td>${esc(r.code)}</td>
        <td>${esc(r.name)}</td>
        <td>${esc(r.industry || "—")}</td>
        <td>${esc(r.add_date || "—")}<span class="rv-tag">${esc(r.add_label || "")}</span></td>
        <td style="font-size:12px">${esc(r.reason || "")}</td>
      </tr>`).join("");
    return `
      <h3 class="rv-sub" style="margin-top:14px">${esc(name)}（${rows.length} 只）</h3>
      <table class="rv-table">
        <thead><tr><th>代码</th><th>名称</th><th>所属板块</th><th>加入时间</th><th>看多理由（系统信号）</th></tr></thead>
        <tbody>${tbody}</tbody>
      </table>`;
  }).join("");
  $("tdPool").innerHTML = blocks || `<div class="subtitle">当前无符合系统的信号股（盘中信号少属正常）</div>`;
}

/* ---------- 三、说明与风险 ---------- */

function renderSummary(d) {
  $("tdSummary").innerHTML = `
    <div class="rv-theme style" style="margin-bottom:12px">
      <h4><span class="dot"></span>使用说明</h4>
      <div class="content">
        <p><strong>1. 系统选择：</strong>稳健型优先系统1（高胜率低吸反转）；系统2 期望为正但胜率中性，需严格执行止损与仓位纪律。</p>
        <p><strong>2. 信号确认：</strong>股票池为实时扫描信号（10分钟刷新），入场前需自行复核当日 K 线形态与量能是否符合系统条件。</p>
        <p><strong>3. 风控纪律：</strong>单笔亏损 ≤5%、单只仓位 ≤8%-10%、情绪评级偏冷/极寒时整体降半仓；只做计划内交易。</p>
        <p><strong>4. 大盘环境：</strong>可结合本站「每日复盘/开盘前瞻/全球宏观」判断市场环境，弱市减少交易频率。</p>
      </div>
    </div>
    <div class="rv-summary-box" style="text-align:left">
      <div class="label">核心结论</div>
      <div class="text" style="font-size:14px;text-align:center">回测胜率最高的是「缩量回踩支撑+放量阳线确认」（3日78%），其次是「涨停缩量回踩均线」（5日均收+2.22%）；追涨类系统回测接近随机，不采用。</div>
    </div>
    <div class="rv-risk-box">
      <h4>⚠️ 风险提示</h4>
      <p>${esc(d.risk || "")} 股票池仅为策略信号展示，加入时间/看多理由由系统规则生成，不代表对个股的推荐或收益承诺；历史回测胜率不保证未来表现。</p>
    </div>`;
}

function render(d) {
  lastData = d;
  const pool = d.pool || [];
  $("tdState").innerHTML = `更新于 ${esc(d.as_of || "--")}${d.history_date ? ` · 历史回放 ${esc(d.history_date)}` : ""}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
  const sysSummary = (d.systems || []).map((s) => `${s.name}（3日胜率 ${s.backtest?.win3 || "--"}）`).join("；");
  $("tdHero").innerHTML = `
    <h3>交易策略 · 可执行交易系统与股票池</h3>
    <div class="rv-hero-sub">回测验证 · 高胜率买点 · ${pool.length} 只实时信号 · 更新 ${esc(d.as_of || "--")}</div>
    <div class="rv-hero-concl">${esc(sysSummary)}；股票池为系统信号实时扫描，仅供策略跟踪研究。</div>`;
  renderSystems(d);
  renderPool(d);
  renderSummary(d);
}

export async function loadTrading(force = false) {
  $("tdState").textContent = "更新中...";
  try {
    const url = apiUrl("/api/trading", force);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    render(d);
  } catch (e) {
    $("tdState").textContent = "刷新失败：" + e.message;
    $("errors").textContent = "交易策略刷新失败：" + e.message;
  }
}

/* ---------- 精简 / 详细模式 ---------- */

function setBrief(v) {
  brief = v;
  $("#page-trading").classList.toggle("brief", v);
  $("#tdMode").textContent = v ? "详细模式" : "精简模式";
}

$("tdMode").addEventListener("click", () => setBrief(!brief));
