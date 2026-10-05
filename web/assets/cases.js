// صفحة حالات الاختبار: بحث وتصفية داخل المتصفح فقط (لا يُرسل أي شيء). بلا مكتبات خارجية.
const HARAKAT = /[ً-ْٰـ]/g;

export function normalizeAr(s) {
  return String(s)
    .replace(HARAKAT, "")
    .replace(/[أإآٱ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/ة/g, "ه")
    .toLowerCase()
    .trim();
}

export function matches(row, { q, level, type }) {
  if (level && row.level !== level) return false;
  if (type && row.type !== type) return false;
  if (q && !normalizeAr(row.text).includes(normalizeAr(q))) return false;
  return true;
}

function main() {
  const table = document.getElementById("cases");
  if (!table) return;
  const q = document.getElementById("q");
  const lv = document.getElementById("lv");
  const ty = document.getElementById("ty");
  const count = document.getElementById("count");
  const noMatch = document.getElementById("no-match");
  const rows = [...table.tBodies[0].rows].map((tr) => ({
    tr, level: tr.dataset.level, type: tr.dataset.type, text: tr.textContent,
  }));
  const total = rows.length;
  const form = q.closest("form");
  form.addEventListener("submit", (e) => e.preventDefault());
  const apply = () => {
    const filter = { q: q.value, level: lv.value, type: ty.value };
    let shown = 0;
    for (const r of rows) {
      const ok = matches(r, filter);
      r.tr.hidden = !ok;
      if (ok) shown += 1;
    }
    count.textContent = `يُعرض ${shown} من ${total} حالة.`;
    if (noMatch) noMatch.hidden = shown > 0;
  };
  q.addEventListener("input", apply);
  lv.addEventListener("change", apply);
  ty.addEventListener("change", apply);
}

if (typeof document !== "undefined") main();
