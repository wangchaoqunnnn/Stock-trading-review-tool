/* ---------- 上升趋势 V 字洗盘：实时选股 ----------
 * 条件：站上MA20且MA20走高（上升趋势）+ 当日分时深V（下跌缩量、回升放量、收复过半）。
 */

import { $, apiUrl, esc, fmt, pctClass, signed } from "./utils.js";

let lastData = null;

function renderHero(d) {
  $("vsHero").innerHTML = `
    <h3>上升趋势 V 字洗盘</h3>
    <div class="rv-hero-sub">盘中深V洗盘 = 强势股洗盘后二次启动 · ${d.count ?? 0} 只实时信号 · 更新 ${esc(d.as_of || "--")}</div>
    <div class="rv-hero-concl">选股条件：① 上升趋势（站上MA20且MA20走高）② 当日分时深V（下跌段缩量、回升段放量、收复过半跌幅）③ 股价处于20日线之上。</div>`;
}

function renderPool(d) {
  const stocks = d.stocks || [];
  $("vsPoolState").textContent = `共 ${d.count ?? stocks.length} 只信号股 · 实时扫描，10分钟刷新 · V字信号盘中变化快，入场前请复核分时`;
  if (!stocks.length) {
    $("vsPool").innerHTML = `<div class="subtitle">当前无满足条件的个股（深V+缩量跌放量涨+上升趋势同时满足较少属正常）。</div>`;
    return;
  }
  const tbody = stocks.map((r) => `
    <tr>
      <td>${esc(r.code)}</td>
      <td><b>${esc(r.name)}</b><br><span class="rv-idx-amt">${esc(r.industry || "—")}</span></td>
      <td class="num">${fmt(r.close)}</td>
      <td class="num ${pctClass(r.pct)}">${signed(r.pct)}</td>
      <td class="num up">${fmt(r.depth, 2)}%</td>
      <td class="num up">${fmt(r.recover, 1)}%</td>
      <td class="num">${fmt(r.vol_ratio, 2)}x</td>
      <td class="num">${fmt(r.ma20)}</td>
      <td class="num">${fmt(r.amount_yi)}</td>
    </tr>`).join("");
  $("vsPool").innerHTML = `
    <table class="rv-table"><thead><tr>
      <th>代码</th><th>名称/板块</th><th class="num">现价</th><th class="num">当日涨幅</th>
      <th class="num">V底深度</th><th class="num">收复幅度</th><th class="num">回升/下跌量比</th>
      <th class="num">MA20</th><th class="num">成交(亿)</th>
    </tr></thead><tbody>${tbody}</tbody></table>
    <p class="rv-text rv-note" style="font-size:12px;margin-top:8px">V底深度=盘中高点至低点跌幅；收复幅度=收盘较V底回升占跌幅比例（≥50%才算洗盘后拉回）；量比=回升段每分钟成交额/下跌段（≥1.15 表示上涨放量）。</p>`;
}

function renderRule(d) {
  $("vsRule").innerHTML = `
    <div class="rv-theme main" style="margin-bottom:10px">
      <h4><span class="dot"></span>V 字洗盘逻辑</h4>
      <div class="content">
        <p><strong>核心：</strong>强势股（上升趋势）盘中快速下探洗盘（分时深V），
          下跌时缩量（抛压小、洗盘而非出货）、回升时放量（资金回补），
          收盘收复过半跌幅——洗盘结束、二次启动信号。</p>
        <p><strong>识别：</strong>① 收盘价 &gt; MA20 且 MA20 较 5 日前走高（趋势向上）；
          ② 分时存在 ≥2% 深度的 V 底且出现在盘中中段；
          ③ V 底后回升段每分钟成交额 ≥ 下跌段 1.15 倍；④ 收盘收复 V 跌幅 ≥50%。</p>
        <p><strong>风险：</strong>V 型也可能是出货后的反抽（回升量能不足则无效）；
          盘中形态变化快，须结合板块与大盘环境，跌破 V 底即信号失效。</p>
      </div>
    </div>
    <div class="rv-risk-box">
      <h4>⚠️ 风险提示</h4>
      <p>${esc(d.risk || "")}</p>
    </div>`;
}

function render(d) {
  lastData = d;
  $("vsState").innerHTML = `更新于 ${esc(d.as_of || "--")}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
  renderHero(d);
  renderPool(d);
  renderRule(d);
}

export async function loadVshape(force = false) {
  $("vsState").textContent = "更新中...";
  $("vsHero").innerHTML = `
    <h3>上升趋势 V 字洗盘</h3>
    <div class="rv-hero-sub">正在扫描全市场（K线核对 + 分时V型检测，约需 10-30 秒），请稍候...</div>
    <div class="rv-hero-concl">深V洗盘后二次启动。</div>`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 150000);
  try {
    const url = apiUrl("/api/vshape", force);
    const resp = await fetch(url, { signal: ctrl.signal });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    render(d);
  } catch (e) {
    const msg = e.name === "AbortError" ? "扫描超时，请稍后重试" : e.message;
    $("vsState").textContent = "刷新失败：" + msg;
    $("errors").textContent = "V字洗盘刷新失败：" + msg;
  } finally {
    clearTimeout(timer);
  }
}
