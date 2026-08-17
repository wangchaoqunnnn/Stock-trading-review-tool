/* 全局运行状态（跨模块共享的 live binding） */

export let auto = true;

export function setAuto(v) {
  auto = v;
}

export function toggleAuto() {
  auto = !auto;
  return auto;
}

// 历史回放日期（"YYYY-MM-DD"），null = 实时
export let selectedDate = null;

export function setSelectedDate(v) {
  selectedDate = v || null;
}
