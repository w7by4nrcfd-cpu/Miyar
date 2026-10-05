// منطق صفحة تفصيل الحالة — بلا DOM، قابل للاختبار بـ node --test.
// بيانات الحالة من data/testcases.json (يولّدها scripts/build_web_pages.py من testsets/ والبيانات المعتمدة)،
// وسجلها الرسمي من data/cases/<id>.json (يكتبه scripts/publish_results.py من evaluation/official/ وحده).
// القاعدة: لا يُعرض حكم إلا من سجل رسمي صالح؛ غياب السجل = «لا سجل رسمي بعد».

const ID = /^[A-Z]+-\d{2,3}$/;

/** معرّف الحالة من عنوان الصفحة (?id=OFF-05)، أو null إن غاب أو لم يطابق الصيغة. */
export function caseIdFrom(search) {
  const id = new URLSearchParams(search).get("id");
  return id && ID.test(id) ? id : null;
}

export function findCase(data, id) {
  if (!data || !Array.isArray(data.cases)) return null;
  return data.cases.find((c) => c.id === id) ?? null;
}

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

/** يتحقق من ملف الحالة المنشور. يعيد قائمة أخطاء (فارغة = صالح). */
export function validateRecord(rec, id) {
  if (!isObj(rec)) return ["الملف ليس كائناً"];
  const errors = [];
  if (rec.id !== id) errors.push("معرّف الحالة في الملف لا يطابق الصفحة");
  if (!Array.isArray(rec.runs)) return [...errors, "runs يجب أن تكون قائمة"];
  rec.runs.forEach((r, i) => {
    if (!isObj(r) || typeof r.run_id !== "string" || typeof r.assistant !== "string") errors.push(`runs[${i}]: ناقص`);
    const j = r?.judgement;
    if (j === null || j === undefined) return;
    if (!isObj(j) || !isObj(j.checks) || typeof j.needs_human_review !== "boolean") errors.push(`runs[${i}].judgement: ناقص`);
    if (typeof j?.confidence !== "number" || j.confidence < 0 || j.confidence > 1) errors.push(`runs[${i}].judgement.confidence غير صالح`);
    for (const c of j?.citations ?? []) {
      // لا «مؤيَّد» بلا نص مطابَق من البيانات وموضعه (BUILD_SPEC S2.1)
      if (c.status === "supported" && !(c.matched_text && c.matched_ref)) errors.push(`runs[${i}]: «مؤيَّد» بلا نص مطابَق`);
    }
  });
  return errors;
}

/**
 * يحوّل استجابة ملف السجل إلى حالة عرض.
 * @returns {{state:"none"} | {state:"invalid", errors:string[]} | {state:"ok", runs:object[]}}
 */
export function interpretRecord(response, id) {
  if (!response || response.status === 404) return { state: "none" };
  if (!response.ok) return { state: "invalid", errors: [`تعذّر تحميل السجل (HTTP ${response.status})`] };
  let rec;
  try {
    rec = JSON.parse(response.text);
  } catch {
    return { state: "invalid", errors: ["ملف السجل ليس JSON صالحاً"] };
  }
  const errors = validateRecord(rec, id);
  if (errors.length) return { state: "invalid", errors };
  if (rec.runs.length === 0) return { state: "none" };
  return { state: "ok", runs: rec.runs };
}

/** آخر تشغيل لكل مساعد، baseline ثم rag ثم غيرهما. */
export function latestRuns(runs) {
  const latest = new Map();
  for (const r of runs) {
    const prev = latest.get(r.assistant);
    if (!prev || Date.parse(r.executed_at) >= Date.parse(prev.executed_at)) latest.set(r.assistant, r);
  }
  const order = ["baseline", "rag"];
  const rank = (a) => (order.includes(a) ? order.indexOf(a) : order.length);
  return [...latest.values()].sort((a, b) => rank(a.assistant) - rank(b.assistant) || a.assistant.localeCompare(b.assistant));
}

const CHECK_TEXT = { true: "التزم", false: "لم يلتزم", null: "لم يُحسم" };

/** نص حالة فحص واحد. */
export function checkText(v) {
  return CHECK_TEXT[v === true ? "true" : v === false ? "false" : "null"];
}

/** الحكم النهائي للحالة في تشغيل واحد، من السجل كما هو. */
export function verdict(judgement, categoryLabels = {}) {
  if (!judgement) return { kind: "none", text: "لا حكم في السجل لهذه الحالة (تعذّر الحكم)" };
  if (judgement.needs_human_review) {
    const why = { low_confidence: "ثقة الحَكَم دون العتبة", invalid_output: "إخراج الحَكَم غير صالح",
      manual_entry_pending: "مدخل الملف اليدوي للحديث ناقص",
      hadith_unverified: "استشهاد حديثي بلا مدخل مكتمل في الملف اليدوي: لا بيانات تؤيد وجوده أو عدمه" }[judgement.review_reason] ?? "إحالة";
    return { kind: "review", text: `أُحيلت إلى مراجعة بشرية ولم تدخل في الدرجة الآلية (${why})` };
  }
  const cats = judgement.categories ?? [];
  if (!cats.length) return { kind: "ok", text: "لا خطأ مرصود" };
  return { kind: "error", text: `أخطاء مرصودة: ${cats.map((c) => categoryLabels[c] ?? c).join("، ")}` };
}

/** نسبة الفحوص الناجحة من المحسومة، نصاً مع عددها؛ أو null إن أُحيلت أو لم يُحسم شيء. */
export function checksSummary(judgement) {
  if (!judgement || judgement.needs_human_review) return null;
  const vals = Object.values(judgement.checks);
  const decided = vals.filter((v) => v !== null);
  if (!decided.length) return null;
  return `${decided.filter(Boolean).length} من ${decided.length} فحوص محسومة`;
}
