// منطق صفحة النتائج — بلا DOM، قابل للاختبار بـ node --test.
// المخطط موثّق في web/data/results.schema.json و web/data/README.md.
//
// القاعدة: لا يُعرض أي رقم إلا من ملف نتائج صالح تماماً. أي شك → لا أرقام.

export const SCHEMA_VERSION = 1;
export const LEVELS = ["A", "B", "C", "D"];
export const REVIEWER_ROLES = ["specialist", "source_check"];

const isInt = (v) => Number.isInteger(v);
const isNonNegInt = (v) => isInt(v) && v >= 0;
const isScore = (v) => typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 100;
const isNonEmptyString = (v) => typeof v === "string" && v.trim() !== "";

function validateRun(run, i) {
  const errors = [];
  const at = (msg) => errors.push(`runs[${i}]: ${msg}`);
  if (run === null || typeof run !== "object" || Array.isArray(run)) {
    at("ليس كائناً");
    return errors;
  }
  for (const key of ["run_id", "executed_at", "assistant", "model", "testset", "evaluation_record"]) {
    if (!isNonEmptyString(run[key])) at(`الحقل ${key} مفقود أو فارغ`);
  }
  if (isNonEmptyString(run.executed_at) && Number.isNaN(Date.parse(run.executed_at))) {
    at("executed_at ليس تاريخاً صالحاً");
  }
  // مبدأ الصدق: كل نتيجة لها سجل تشغيل رسمي (OFFICIAL_RUN) داخل evaluation/official/ وحده
  if (
    isNonEmptyString(run.evaluation_record) &&
    (!run.evaluation_record.startsWith("evaluation/official/") || run.evaluation_record.split("/").includes(".."))
  ) {
    at("evaluation_record يجب أن يشير إلى مسار داخل evaluation/official/");
  }
  // تشغيلات التطوير (مجلد dev داخل evaluation) ليست نتائج رسمية ولا تُعرض أبداً
  if (isNonEmptyString(run.evaluation_record) && /^evaluation\/dev(\/|$)/.test(run.evaluation_record)) {
    at("evaluation_record يشير إلى تشغيل تطوير، وهو ليس نتيجة رسمية");
  }
  if (!isInt(run.n_cases) || run.n_cases < 1) at("n_cases يجب أن يكون عدداً صحيحاً ≥ 1");
  if (!isScore(run.overall_score)) at("overall_score يجب أن يكون بين 0 و100");
  if (!isNonNegInt(run.wrong_citations)) at("wrong_citations يجب أن يكون عدداً صحيحاً ≥ 0");

  const levels = run.levels;
  if (levels === null || typeof levels !== "object" || Array.isArray(levels)) {
    at("levels مفقود");
  } else {
    let sum = 0;
    for (const lv of LEVELS) {
      const l = levels[lv];
      if (l === null || typeof l !== "object") {
        at(`levels.${lv} مفقود`);
        continue;
      }
      if (!isNonNegInt(l.n_cases)) at(`levels.${lv}.n_cases غير صالح`);
      else sum += l.n_cases;
      // مستوى بلا حالات درجته null؛ ومستوى فيه حالات يجب أن تكون له درجة
      if (l.n_cases === 0 ? l.score !== null : !isScore(l.score)) at(`levels.${lv}.score غير صالح`);
    }
    for (const k of Object.keys(levels)) if (!LEVELS.includes(k)) at(`مستوى غير معروف: ${k}`);
    if (isInt(run.n_cases) && sum !== run.n_cases) at("مجموع حالات المستويات لا يساوي n_cases");
  }

  const hr = run.human_reviewed;
  if (hr === null || typeof hr !== "object") {
    at("human_reviewed مفقود");
  } else {
    if (!isNonNegInt(hr.approved) || !isNonNegInt(hr.total)) at("human_reviewed.approved/total غير صالحين");
    else {
      if (hr.approved > hr.total) at("human_reviewed.approved أكبر من total");
      if (isInt(run.n_cases) && hr.total !== run.n_cases) at("human_reviewed.total لا يساوي n_cases");
    }
    // لكل نوع مراجعة عدده؛ وتحقق المصادر (source_check) ليس مراجعة شرعية متخصصة فيُعرض منفصلاً
    const br = hr.by_role;
    if (br === null || typeof br !== "object" || Array.isArray(br)) {
      at("human_reviewed.by_role مفقود");
    } else {
      for (const k of Object.keys(br)) if (!REVIEWER_ROLES.includes(k)) at(`نوع مراجعة غير معروف: ${k}`);
      if (!REVIEWER_ROLES.every((k) => isNonNegInt(br[k]))) at("human_reviewed.by_role غير صالح");
      else if (isNonNegInt(hr.approved) && br.specialist + br.source_check !== hr.approved) {
        at("مجموع by_role لا يساوي human_reviewed.approved");
      }
    }
  }
  return errors;
}

/** يتحقق من كائن النتائج. يعيد قائمة أخطاء (فارغة = صالح). */
export function validateResults(data) {
  if (data === null || typeof data !== "object" || Array.isArray(data)) return ["الجذر ليس كائناً"];
  const errors = [];
  if (data.schema_version !== SCHEMA_VERSION) errors.push(`schema_version يجب أن يساوي ${SCHEMA_VERSION}`);
  if (!Array.isArray(data.runs)) {
    errors.push("runs يجب أن تكون قائمة");
    return errors;
  }
  const ids = new Set();
  data.runs.forEach((run, i) => {
    errors.push(...validateRun(run, i));
    if (run && isNonEmptyString(run.run_id)) {
      if (ids.has(run.run_id)) errors.push(`run_id مكرر: ${run.run_id}`);
      ids.add(run.run_id);
    }
  });
  return errors;
}

/**
 * يحوّل استجابة الملف إلى حالة عرض.
 * @param {{status:number, ok:boolean, text:string}|null} response  null = تعذّر الوصول للملف
 * @returns {{state:"empty"} | {state:"invalid", errors:string[]} | {state:"ok", runs:object[]}}
 */
export function interpretResults(response) {
  if (!response || response.status === 404) return { state: "empty" };
  if (!response.ok) return { state: "invalid", errors: [`تعذّر تحميل الملف (HTTP ${response.status})`] };
  const text = (response.text ?? "").trim();
  if (text === "") return { state: "empty" };
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    return { state: "invalid", errors: ["الملف ليس JSON صالحاً"] };
  }
  const errors = validateResults(data);
  if (errors.length) return { state: "invalid", errors };
  if (data.runs.length === 0) return { state: "empty" };
  return { state: "ok", runs: data.runs };
}

/** عدد الحالات المقبولة لكل نوع مراجعة، مع نصّ عرضه. source_check ليس مراجعة شرعية متخصصة. */
export function reviewSummaryText(run) {
  const { total, by_role: r } = run.human_reviewed;
  return [
    `مراجعة شرعية متخصصة: ${r.specialist} من ${total}`,
    `تحقق من المصادر بواسطة المشارك: ${r.source_check} من ${total} (ليس مراجعة شرعية متخصصة)`,
  ];
}

/** نسبة الحالات المراجَعة بشرياً (0..1). */
export function reviewedRatio(run) {
  return run.human_reviewed.total === 0 ? 0 : run.human_reviewed.approved / run.human_reviewed.total;
}
