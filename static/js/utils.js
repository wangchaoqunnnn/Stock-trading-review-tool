/* 通用工具函数 */

export const $ = (id) => document.getElementById(id);

export function esc(v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function fmt(v, digits = 2) {
  if (v == null || isNaN(v)) return "--";
  return Number(v).toFixed(digits);
}

export function pctClass(v) {
  if (v > 0) return "up";
  if (v < 0) return "down";
  return "flat";
}

export function signed(v, digits = 2, suffix = "%") {
  if (v == null || isNaN(v)) return "--";
  const s = Number(v) > 0 ? "+" : "";
  return s + Number(v).toFixed(digits) + suffix;
}

export function toYi(v) {
  const n = Number(v);
  return isNaN(n) ? 0 : n / 100000000;
}
