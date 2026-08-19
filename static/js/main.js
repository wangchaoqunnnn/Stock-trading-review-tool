/* ---------- 应用入口：Tab 切换、自动刷新（带倒计时）、按钮事件 ---------- */

import { $ } from "./utils.js";
import { auto, toggleAuto, selectedDate, setSelectedDate } from "./state.js";
import { load } from "./daily.js";
import { loadRealtime } from "./realtime.js";
import { loadVolPrice } from "./volprice.js";
import { loadPullback } from "./pullback.js";
import { loadFlow3 } from "./flow3.js";
import { loadTrend3 } from "./trend3.js";
import { loadLimit20 } from "./limit20.js";
import { loadZtpool } from "./ztpool.js";
import { loadHot } from "./hot.js";
import { loadBreakout } from "./breakout.js";
import { loadLeaders } from "./leaders.js";
import { loadHeatmap } from "./heatmap.js";
import { loadSpeedRank } from "./speedrank.js";
import { loadPullbackMa } from "./pullback_ma.js";

// Tab -> 页面元素 id / 数据加载函数
const PAGES = {
  daily: "page-daily",
  realtime: "page-realtime",
  volprice: "page-volprice",
  pullback: "page-pullback",
  flow3: "page-flow3",
  trend3: "page-trend3",
  limit20: "page-limit20",
  ztpool: "page-ztpool",
  hot: "page-hot",
  breakout: "page-breakout",
  leaders: "page-leaders",
  heatmap: "page-heatmap",
  speedrank: "page-speedrank",
  pullback_ma: "page-pullback_ma",
};
const LOADERS = {
  daily: load,
  realtime: loadRealtime,
  volprice: loadVolPrice,
  pullback: loadPullback,
  flow3: loadFlow3,
  trend3: loadTrend3,
  limit20: loadLimit20,
  ztpool: loadZtpool,
  hot: loadHot,
  breakout: loadBreakout,
  leaders: loadLeaders,
  heatmap: loadHeatmap,
  speedrank: loadSpeedRank,
  pullback_ma: loadPullbackMa,
};

const REFRESH_INTERVAL = 30; // 自动刷新周期（秒）

let activeTab = "daily";
let timer = null;
let countdown = REFRESH_INTERVAL;
let refreshing = false;

function switchTab(name) {
  activeTab = name;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  for (const [tab, pageId] of Object.entries(PAGES)) {
    $(pageId).classList.toggle("hidden", tab !== name);
  }
  // 切到非每日复盘页时立即强制刷新（保持历史行为）
  if (name !== "daily") LOADERS[name](true);
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

// 顶部刷新状态：倒计时显示（由本模块统一管理）
function updateCountdown() {
  if (selectedDate) {
    $("refreshState").textContent = "历史模式（自动刷新暂停）";
    return;
  }
  $("refreshState").textContent = auto ? `自动刷新 ${countdown}s` : "已暂停自动刷新";
}

// 历史回放：点击"数据时间"选择日期，全站切换
function applyHistoryMode() {
  const picker = $("datePicker");
  $("dateReset").classList.toggle("hidden", !selectedDate);
  if (selectedDate) {
    $("asOf").textContent = "历史：" + selectedDate;
    $("asOf").classList.add("hist");
    picker.value = selectedDate;
  } else {
    $("asOf").textContent = "数据时间";
    $("asOf").classList.remove("hist");
    picker.value = "";
  }
  updateCountdown();
  refreshNow(true); // 全站（当前页）强制刷新到该日期
}

$("asOf").addEventListener("click", () => {
  const picker = $("datePicker");
  if (typeof picker.showPicker === "function") picker.showPicker();
  else picker.focus();
});
$("datePicker").addEventListener("change", () => {
  setSelectedDate($("datePicker").value || null);
  applyHistoryMode();
});
$("dateReset").addEventListener("click", () => {
  setSelectedDate(null);
  applyHistoryMode();
});

// 统一刷新入口：手动/自动/初始化都走这里
async function refreshNow(force = false) {
  if (refreshing && !force) return; // 上一轮未完成时跳过自动刷新
  refreshing = true;
  $("refreshState").textContent = "更新中...";
  try {
    await (LOADERS[activeTab] || load)(force);
  } finally {
    refreshing = false;
    if (auto) countdown = REFRESH_INTERVAL;
    updateCountdown();
  }
}

// 每秒 tick：更新倒计时，归零时触发自动刷新（历史模式不自动刷新）
function tick() {
  if (selectedDate) {
    updateCountdown();
    return;
  }
  if (!auto) {
    updateCountdown();
    return;
  }
  countdown -= 1;
  if (countdown <= 0) {
    countdown = REFRESH_INTERVAL;
    refreshNow(false);
  }
  updateCountdown();
}

function startAuto() {
  if (timer) clearInterval(timer);
  timer = setInterval(tick, 1000);
  updateCountdown();
}

$("refreshBtn").addEventListener("click", () => refreshNow(true));
$("autoBtn").addEventListener("click", () => {
  const next = toggleAuto();
  $("autoBtn").classList.toggle("active", next);
  if (next) countdown = REFRESH_INTERVAL;
  updateCountdown();
});

startAuto();
refreshNow(true);
