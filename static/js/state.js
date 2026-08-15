/* 全局运行状态（跨模块共享的 live binding） */

export let auto = true;

export function setAuto(v) {
  auto = v;
}

export function toggleAuto() {
  auto = !auto;
  return auto;
}
