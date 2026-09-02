/* ---------- N型反转：三段式N字形态实时选股 + 板块共振 ---------- */

import { $, apiUrl, esc, fmt, pctClass, signed } from "./utils.js";

let lastData = null;

const RESONANCE = {
  strong: { label: "强共振", color: "#f04a4a" },
  normal: { label: "共振", color: "#ffb020" },
  weak: { label: "无共振", color: "#2fbf71" },
};

function renderHero(d) {
  $("nsHero").innerHTML = `
    <h3>N 型反转（策略选股版）</h3>
    <div class="rv-hero-sub">三段式 N 字形态 · 及时捕捉启动第三笔 · ${d.count ?? 0} 只实时信号 · 更新 ${esc(d.as_of || "--")}</div>
    <div class="rv-hero-concl">拉升（上）→ 缩量回调（下）→ 放量反转（上）= N 字成型；配合板块共振（板块走强+资金流入）确认合力。</div>`;
}

function renderShape(d) {
  $("nsShape").innerHTML = `
    <div class="rv-two">
      <div class="rv-pos-neg pos" style="text-align:center">
        <div style="font-family:monospace;font-size:34px;line-height:1.1;font-weight:700">N</div>
        <div style="font-size:12px;color:#8b93a7">三段式：上 — 下 — 上</div>
      </div>
      <div style="font-size:13px;color:#cfd6e4;line-height:1.9">
        <p><strong style="color:#f04a4a">第一笔「上」</strong>：3-7 根阳线累计涨幅 ≥20%（强势启动、量能放大）——N 字的左上升沿。</p>
        <p><strong style="color:#ffb020">第二笔「下」</strong>：3-8 天缩量回调（均量 ≤ 前5日均量×0.9）、回踩不破第一波起涨低点——N 字的中间回落，洗盘而非出货。</p>
        <p><strong style="color:#4c8dff">第三笔「上」</strong>：放量阳线（量 ≥ 前5日均量×1.2）上穿 5 日线、收复回调跌幅——N 字右侧反转启动，即买点。</p>
      </div>
    </div>`;
}

function resBadge(r) {
  if (!r) return `<span class="rv-chip">板块数据暂缺</span>`;
  const cfg = RESONANCE[r.level] || RESONANCE.weak;
  const flow = r.flow_yi == null ? "" : ` · 资金${r.flow_yi >= 0 ? "+" : ""}${fmt(r.flow_yi, 1)}亿`;
  return `<span class="rv-chip" style="border-color:${cfg.color};color:${cfg.color}">${esc(r.name)} ${signed(r.pct)}${flow} · ${cfg.label}</span>`;
}

function renderPool(d) {
  const stocks = d.stocks || [];
  $("nsPoolState").textContent = `共 ${d.count ?? stocks.length} 只信号股 · 按共振强度排序 · 实时扫描，10分钟刷新`;
  if (!stocks.length) {
    $("nsPool").innerHTML = `<div class="subtitle">当前无满足 N 型形态的个股（拉升≥20% → 缩量回调3-8天 → 今日放量反转同时满足较少属正常）。</div>`;
    return;
  }
  const tbody = stocks.map((r) => `
    <tr>
      <td>${esc(r.code)}</td>
      <td><b>${esc(r.name)}</b><br><span class="rv-idx-amt">${esc(r.industry || "—")}</span></td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num up">${fmt(r.gain, 1)}%</td>
      <td class="num">${r.days}天</td>
      <td class="num up">${fmt(r.vol_ratio, 2)}x</td>
      <td class="num">${fmt(r.support)}</td>
      <td>${resBadge(r.resonance)}</td>
    </tr>`).join("");
  $("nsPool").innerHTML = `
    <table class="rv-table"><thead><tr>
      <th>代码</th><th>名称/板块</th><th class="num">今日涨幅</th><th class="num">第一波涨幅</th>
      <th class="num">回调天数</th><th class="num">放量倍数</th><th class="num">起涨低点</th><th>板块共振</th>
    </tr></thead><tbody>${tbody}</tbody></table>
    <p class="rv-text rv-note" style="font-size:12px;margin-top:8px">共振判定：信号股所属行业/概念板块当日涨幅&gt;0 且主力净流入&gt;0 = 强共振（红）；仅涨幅&gt;0 = 一般共振（橙）；板块未走强 = 无共振（绿，慎入）。</p>`;
}

function renderRule(d) {
  $("nsRule").innerHTML = `
    <div class="rv-theme style" style="margin-bottom:10px">
      <h4><span class="dot"></span>选股条件</h4>
      <div class="content">
        <p><strong>① 第一波：</strong>3-7 根阳线累计涨幅 ≥20%（确认活跃强势股）。</p>
        <p><strong>② 回调：</strong>3-8 天缩量回调（均量 ≤ 前5日均量×0.9）、不破第一波起涨低点（N 型不破坏）。</p>
        <p><strong>③ 反转启动（今日）：</strong>放量阳线（量 ≥ 前5日均量×1.2）、上穿 5 日线、收复前日收盘。</p>
        <p><strong>④ 板块共振（加分核心）：</strong>个股所属板块当日走强且资金净流入——有合力支撑的 N 型反转更可靠；无共振的独走个股谨慎。</p>
        <p><strong>风险：</strong>N 型破坏（跌破起涨低点）即失效；回调放量/大阴线破位不成立；需结合大盘与情绪周期。</p>
      </div>
    </div>
    <div class="rv-risk-box">
      <h4>⚠️ 风险提示</h4>
      <p>${esc(d.risk || "")}</p>
    </div>`;
}

function render(d) {
  lastData = d;
  $("nsState").innerHTML = `更新于 ${esc(d.as_of || "--")}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
  renderHero(d);
  renderShape(d);
  renderPool(d);
  renderRule(d);
}

export async function loadNshape(force = false) {
  $("nsState").textContent = "更新中...";
  $("nsHero").innerHTML = `
    <h3>N 型反转（策略选股版）</h3>
    <div class="rv-hero-sub">正在扫描全市场（K线N型核对 + 板块共振，约需 5-20 秒），请稍候...</div>
    <div class="rv-hero-concl">拉升 → 缩量回调 → 放量反转。</div>`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 150000);
  try {
    const url = apiUrl("/api/nshape", force);
    const resp = await fetch(url, { signal: ctrl.signal });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    render(d);
  } catch (e) {
    const msg = e.name === "AbortError" ? "扫描超时，请稍后重试" : e.message;
    $("nsState").textContent = "刷新失败：" + msg;
    $("errors").textContent = "N型反转刷新失败：" + msg;
  } finally {
    clearTimeout(timer);
  }
}
