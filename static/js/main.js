/* ---------- 应用入口：Tab 切换、自动刷新、按钮事件 ---------- */

import { $ } from "./utils.js";
import { toggleAuto } from "./state.js";
import { load } from "./daily.js";
import { loadRealtime } from "./realtime.js";
import { loadVolPrice } from "./volprice.js";
import { loadPullback } from "./pullback.js";

let activeTab = "daily";
let timer = null;

function switchTab(name) {
  activeTab = name;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $("page-daily").classList.toggle("hidden", name !== "daily");
  $("page-realtime").classList.toggle("hidden", name !== "realtime");
  if (name === "realtime") loadRealtime(true);
  $("page-volprice").classList.toggle("hidden", name !== "volprice");
  if (name === "volprice") loadVolPrice(true);
  $("page-pullback").classList.toggle("hidden", name !== "pullback");
  if (name === "pullback") loadPullback(true);
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

function startAuto() {
  if (timer) clearInterval(timer);
  timer = setInterval(() => {
    if (activeTab === "realtime") loadRealtime(false);
    else if (activeTab === "volprice") loadVolPrice(false);
    else if (activeTab === "pullback") loadPullback(false);
    else load(false);
  }, 30000);
}

$("refreshBtn").addEventListener("click", () => {
  if (activeTab === "realtime") loadRealtime(true);
  else if (activeTab === "volprice") loadVolPrice(true);
  else if (activeTab === "pullback") loadPullback(true);
  else load(true);
});
$("autoBtn").addEventListener("click", () => {
  const next = toggleAuto();
  $("autoBtn").classList.toggle("active", next);
  $("refreshState").textContent = next ? "自动刷新 30s" : "已暂停自动刷新";
});

startAuto();
load(true);
