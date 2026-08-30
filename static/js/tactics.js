/* ---------- 战法选股：N字战法 + 突破战法实时信号 ----------
 * 数据来自 /api/tactics：两大战法定义（含回测数据）+
 * 实时扫描的信号个股（买入逻辑/止损价/建议仓位）。
 * 复用暗色报告组件；支持精简/详细模式。
 */

import { $, apiUrl, esc, fmt, signed } from "./utils.js";

let lastData = null;
let brief = false;

/* ---------- 战法定义卡片 ---------- */

function tacticCard(bt, title, summary, rules) {
  const rows = rules.map((r) => `<li>${esc(r)}</li>`).join("");
  return `
    <div class="rv-theme main" style="margin-bottom:14px">
      <h4><span class="dot"></span>${esc(title)}</h4>
      <div class="content">
        <p>${esc(summary)}</p>
        <ul style="margin:6px 0 8px;padding-left:18px;line-height:1.9">${rows}</ul>
        <p style="margin-top:6px"><strong>回测数据（${esc(bt.note || "")}）：</strong>
          <span class="rv-chip">${bt.signals} 信号</span>
          <span class="rv-chip">3日胜率 ${esc(bt.win3)}</span>
          <span class="rv-chip">5日胜率 ${esc(bt.win5)}</span>
          <span class="rv-chip">3日均收 ${esc(bt.avg3)}</span>
          <span class="rv-chip">5日均收 ${esc(bt.avg5)}</span>
        </p>
      </div>
    </div>`;
}

function renderTactics(d) {
  const bt = d.backtest || {};
  $("tcN").innerHTML = tacticCard(bt.n_shape || {}, "N字战法（低吸反转 · 赔率型）",
    "强势股 20%+ 拉升后缩量回调不破势，放量阳线反包启动确定性第二波；不吃首板、不吃追高。",
    [
      "第一波：3-7 根阳线累计涨幅 ≥20%（确认强势活跃股）。",
      "回调：3-8 天缩量回落（均量 ≤ 前5日均量）、不创新低、回踩均线企稳。",
      "信号：放量阳线（量 ≥ 前5日均量×1.2）上穿5日线、收盘收复前日——N字第三笔启动。",
      "止损：跌破第一波起涨低点无条件离场；单票 -4%~-6% 硬止损；入场3天不启动离场。",
      "止盈：前高压力减半、突破前高持有至缩量滞涨/断板清仓。",
      "仓位：情绪回暖 3-4 成、正常 2-3 成、弱市 1-2 成、情绪冰点停用。",
    ]);
  $("tcB").innerHTML = tacticCard(bt.breakout || {}, "突破战法（趋势主升 · 胜率型）",
    "横盘蓄势 = 筹码沉淀，放量突破 = 资金抢筹；只做盘整/平台/压力突破，吃确定性主升浪。",
    [
      "蓄势：7-20 天箱体横盘（振幅 ≤15%）、量能萎缩、无破位。",
      "突破：收盘站稳箱体上沿 + 放量（量 ≥ 前5日均量×1.5）——真突破三要素（放量/板块共振/收盘站稳）。",
      "止损：跌回箱体内部突破失效；单票最大 -5%；突破次日低开不修复离场。",
      "止盈：冲高 5-8% 无力减仓、连阳主升持有至首破10日线、极强标的持有至放量滞涨/顶部背离。",
      "仓位：真突破+板块龙头 4-5 成、跟风 2 成、指数弱 轻仓试错。",
    ]);
}

/* ---------- 信号个股 ---------- */

function renderPool(d) {
  const stocks = d.stocks || [];
  $("tcPoolState").textContent = `共 ${d.count ?? stocks.length} 只信号股 · 情绪分 ${d.emotion_score ?? "--"}（用于仓位建议）· 实时扫描，10分钟刷新`;
  const byTactic = { n_shape: [], breakout: [] };
  for (const s of stocks) (byTactic[s.tactic_id] = byTactic[s.tactic_id] || []).push(s);
  const block = (key, title) => {
    const rows = byTactic[key] || [];
    if (!rows.length) return "";
    const tbody = rows.map((r) => `
      <tr>
        <td>${esc(r.code)}</td>
        <td><b>${esc(r.name)}</b><br><span class="rv-idx-amt">${esc(r.industry)}</span></td>
        <td class="num">${fmt(r.price)}</td>
        <td style="font-size:12px;line-height:1.6">${esc(r.logic)}</td>
        <td class="num" style="color:#ff9b5e">${r.stop == null ? "--" : fmt(r.stop)}</td>
        <td style="font-size:12px">${esc(r.position)}</td>
      </tr>`).join("");
    return `
      <h3 class="rv-sub" style="margin-top:12px">${esc(title)}（${rows.length} 只）</h3>
      <table class="rv-table">
        <thead><tr><th>代码</th><th>名称/板块</th><th class="num">现价</th><th>买入逻辑</th><th class="num">止损价</th><th>建议仓位</th></tr></thead>
        <tbody>${tbody}</tbody>
      </table>`;
  };
  $("tcPool").innerHTML = block("n_shape", "N字战法信号") + block("breakout", "突破战法信号")
    || `<div class="subtitle">当前无符合战法的信号股。战法要求严格（真突破/缩量洗盘末端），命中稀少属正常；盘中/收盘后刷新查看。</div>`;
}

/* ---------- 配套规则 ---------- */

function renderRule(d) {
  $("tcRule").innerHTML = `
    <div class="rv-theme style" style="margin-bottom:10px">
      <h4><span class="dot"></span>两套系统职业配套使用规则</h4>
      <div class="content">
        <p><strong>行情定性：</strong>震荡市/情绪修复 → 只用 N 字战法（低吸）；趋势市/主升行情 → 只用突破战法（追势）。<strong>永不混用</strong>。</p>
        <p><strong>空仓纪律：</strong>无符合形态标的直接空仓，不强行交易；情绪冰点（情绪分 &lt;25）两套战法全部停用。</p>
        <p><strong>极简流程：</strong>复盘筛选 → 行情定性 → 等待标准信号（不提前预埋）→ 入场即挂止损止盈 → 收盘复盘形态对错。</p>
        <p><strong>风控：</strong>单票亏损 -4%~-6% 硬止损；时间止损（入场3天不启动离场）；永远不满仓。</p>
      </div>
    </div>
    <div class="rv-risk-box">
      <h4>⚠️ 风险提示</h4>
      <p>${esc(d.risk || "")}</p>
    </div>`;
}

function render(d) {
  lastData = d;
  const stocks = d.stocks || [];
  $("tcState").innerHTML = `更新于 ${esc(d.as_of || "--")}${d.history_date ? ` · 历史回放 ${esc(d.history_date)}` : ""}`
    + ((d.errors || []).length ? ` <span class="rv-warn">· ${(d.errors || []).map(esc).join("；")}</span>` : "");
  $("tcHero").innerHTML = `
    <h3>战法选股 · N字战法 + 突破战法</h3>
    <div class="rv-hero-sub">回测验证 · ${stocks.length} 只实时信号 · 买入逻辑/止损价/建议仓位 · 更新 ${esc(d.as_of || "--")}</div>
    <div class="rv-hero-concl">N字=缩量洗盘末端低吸（赔率型）；突破=放量突破主升（胜率型）。信号稀少属正常——符合形态才出手。</div>`;
  renderTactics(d);
  renderPool(d);
  renderRule(d);
}

export async function loadTactics(force = false) {
  $("tcState").textContent = "更新中...";
  $("tcHero").innerHTML = `
    <h3>战法选股 · N字战法 + 突破战法</h3>
    <div class="rv-hero-sub">正在扫描全市场构建信号池（约需 20-60 秒），请稍候...</div>
    <div class="rv-hero-concl">符合形态才出手，无信号即空仓。</div>`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 150000);
  try {
    const url = apiUrl("/api/tactics", force);
    const resp = await fetch(url, { signal: ctrl.signal });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const d = await resp.json();
    render(d);
  } catch (e) {
    const msg = e.name === "AbortError" ? "扫描超时（超过150秒），请稍后重试" : e.message;
    $("tcState").textContent = "刷新失败：" + msg;
    $("errors").textContent = "战法选股刷新失败：" + msg;
  } finally {
    clearTimeout(timer);
  }
}

/* ---------- 精简 / 详细模式 ---------- */

function setBrief(v) {
  brief = v;
  $("#page-tactics").classList.toggle("brief", v);
  $("#tcMode").textContent = v ? "详细模式" : "精简模式";
}

$("tcMode").addEventListener("click", () => setBrief(!brief));
