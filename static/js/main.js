/* ---------- 应用入口：Tab 切换、自动刷新、按钮事件 ---------- */

import { $ } from "./utils.js";
import { toggleAuto } from "./state.js";
import { load } from "./daily.js";
import { loadRealtime } from "./realtime.js";
import { loadVolPrice } from "./volprice.js";
import { loadPullback } from "./pullback.js";
import { loadFlow3 } from "./flow3.js";
import { loadTrend3 } from "./trend3.js";
import { loadLimit20 } from "./limit20.js";

// Tab -> 页面元素 id / 数据加载函数
const PAGES = {
  daily: "page-daily",
  realtime: "page-realtime",
  volprice: "page-volprice",
  pullback: "page-pullback",
  flow3: "page-flow3",
  trend3: "page-trend3",
  limit20: "page-limit20",
};
const LOADERS = {
  daily: load,
  realtime: loadRealtime,
  volprice: loadVolPrice,
  pullback: loadPullback,
  flow3: loadFlow3,
  trend3: loadTrend3,
  limit20: loadLimit20,
};

let activeTab = "daily";
let timer = null;

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

function startAuto() {
  if (timer) clearInterval(timer);
  timer = setInterval(() => {
    (LOADERS[activeTab] || load)(false);
  }, 30000);
}

$("refreshBtn").addEventListener("click", () => {
  (LOADERS[activeTab] || load)(true);
});
$("autoBtn").addEventListener("click", () => {
  const next = toggleAuto();
  $("autoBtn").classList.toggle("active", next);
  $("refreshState").textContent = next ? "自动刷新 30s" : "已暂停自动刷新";
});

startAuto();
load(true);
