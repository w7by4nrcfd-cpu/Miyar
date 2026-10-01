// صفحة النتائج: تقرأ data/results.json وتعرض حالتها دون أي رقم مصطنع.
import { interpretResults } from "./results-core.js";

const RESULTS_URL = "data/results.json";

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const c of children) node.append(c); // نص فقط: لا innerHTML لبيانات خارجية
  return node;
}

function renderEmpty(root) {
  root.replaceChildren(
    el("div", { class: "notice empty", role: "status" },
      el("strong", {}, "لم يُشغَّل أي اختبار بعد"),
      el("span", {}, "لا توجد نتائج لعرضها. ستظهر هنا نتائج التشغيلات الفعلية فقط بعد تنفيذها وتسجيلها في evaluation/."))
  );
}

function renderInvalid(root, errors) {
  const list = el("ul");
  for (const e of errors.slice(0, 10)) list.append(el("li", {}, e));
  root.replaceChildren(
    el("div", { class: "notice error", role: "alert" },
      el("strong", {}, "بيانات النتائج غير صالحة"),
      el("span", {}, "لن تُعرض أي أرقام من ملف لا يطابق المخطط الموثّق. التفاصيل:"),
      list)
  );
}

function renderOk(root, runs) {
  // لوحة الدرجات التفصيلية تُبنى خلال أيام التحدي؛ هنا تأكيد وجود تشغيلات صالحة فقط.
  const list = el("ul");
  for (const r of runs) {
    list.append(el("li", {}, `${r.run_id} — ${r.assistant} — ${r.executed_at} — `, el("span", { class: "ltr" }, r.evaluation_record)));
  }
  root.replaceChildren(
    el("div", { class: "notice", role: "status" },
      el("strong", {}, `يوجد ${runs.length} تشغيل صالح في ملف النتائج`),
      el("span", {}, "عرض الدرجات ولوحة المقارنة قيد البناء. سجلات التشغيل:"),
      list)
  );
}

async function main() {
  const root = document.getElementById("results");
  let response = null;
  try {
    const res = await fetch(RESULTS_URL, { cache: "no-store" });
    response = { status: res.status, ok: res.ok, text: res.ok ? await res.text() : "" };
  } catch {
    response = null; // تعذّر الوصول = لا نتائج
  }
  const view = interpretResults(response);
  if (view.state === "ok") renderOk(root, view.runs);
  else if (view.state === "invalid") renderInvalid(root, view.errors);
  else renderEmpty(root);
}

main();
