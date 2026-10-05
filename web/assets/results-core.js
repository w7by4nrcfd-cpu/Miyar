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
      const hasScored = l.n_scored !== undefined;
      if (hasScored && (!isNonNegInt(l.n_scored) || l.n_scored > l.n_cases)) at(`levels.${lv}.n_scored غير صالح`);
      // درجته null إن لم تكن فيه حالات أو لم تُحتسب منه أي حالة؛ وإلا يجب أن تكون له درجة
      const mayBeNull = l.n_cases === 0 || (hasScored && l.n_scored === 0);
      if (l.score === null ? !mayBeNull : !isScore(l.score) || l.n_cases === 0) at(`levels.${lv}.score غير صالح`);
    }
    for (const k of Object.keys(levels)) if (!LEVELS.includes(k)) at(`مستوى غير معروف: ${k}`);
    if (isInt(run.n_cases) && sum !== run.n_cases) at("مجموع حالات المستويات لا يساوي n_cases");
  }

  if (run.n_scored !== undefined && (!isNonNegInt(run.n_scored) || (isInt(run.n_cases) && run.n_scored > run.n_cases))) {
    at("n_scored غير صالح");
  }
  if (run.human_review_needed !== undefined && !isNonNegInt(run.human_review_needed)) at("human_review_needed غير صالح");
  if (run.referral !== undefined) {
    const r = run.referral;
    if (r === null || typeof r !== "object" || !["passed", "failed", "undecided"].every((k) => isNonNegInt(r[k]))) {
      at("referral غير صالح");
    }
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
  if (data.gate !== undefined) {
    const g = data.gate;
    if (g === null || typeof g !== "object" || Array.isArray(g)) errors.push("gate ليس كائناً");
    else {
      if (typeof g.allow !== "boolean") errors.push("gate.allow يجب أن يكون منطقياً");
      if (!isNonEmptyString(g.rule)) errors.push("gate.rule مفقود");
      if (!Array.isArray(g.reasons) || !g.reasons.every((r) => typeof r === "string")) errors.push("gate.reasons غير صالح");
      // القرار يُبنى على تشغيلين منشورين فعلاً
      for (const k of ["reference_run_id", "candidate_run_id"]) {
        if (!ids.has(g[k])) errors.push(`gate.${k} لا يشير إلى تشغيل منشور`);
      }
    }
  }
  if (data.stability !== undefined) {
    const st = data.stability;
    if (st === null || typeof st !== "object" || Array.isArray(st)) errors.push("stability ليس كائناً");
    else {
      for (const [a, v] of Object.entries(st)) {
        if (!v || !Array.isArray(v.run_ids) || v.run_ids.length < 2 || !v.run_ids.every((id) => ids.has(id))) {
          errors.push(`stability.${a}: run_ids يجب أن تشير إلى تشغيلين منشورين أو أكثر`);
        }
      }
    }
  }
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
  return { state: "ok", runs: data.runs, gate: data.gate ?? null, stability: data.stability ?? {} };
}

// ---------- المقارنة (baseline مقابل rag) ----------
// عنوان بطاقة النتائج الموحّدة: «جولة واحدة» و«جولتين» و«3–10 جولات» و«11 جولة» بالمطابقة العربية في العدد والصفة
export function officialRunsHeadline(n) {
  if (n === 1) return "نتائج جولة رسمية واحدة مسجّلة في";
  if (n === 2) return "نتائج جولتين رسميتين مسجّلتين في";
  if (n >= 3 && n <= 10) return `نتائج ${n} جولات رسمية مسجّلة في`;
  return `نتائج ${n} جولة رسمية مسجّلة في`;
}

export const ASSISTANT_ORDER = ["baseline", "rag"];

/** آخر تشغيل لكل مساعد (بوقت التشغيل)، baseline ثم rag ثم غيرهما. لا يُختار «أفضل» تشغيل. */
export function latestByAssistant(runs) {
  const latest = new Map();
  for (const r of runs) {
    const prev = latest.get(r.assistant);
    if (!prev || Date.parse(r.executed_at) >= Date.parse(prev.executed_at)) latest.set(r.assistant, r);
  }
  const rank = (a) => (ASSISTANT_ORDER.includes(a) ? ASSISTANT_ORDER.indexOf(a) : ASSISTANT_ORDER.length);
  return [...latest.values()].sort((a, b) => rank(a.assistant) - rank(b.assistant) || a.assistant.localeCompare(b.assistant));
}

const fmt = (v) => (v === null || v === undefined ? "—" : String(v));
// عزل «N = 12» باتجاه يسار-يمين داخل النص العربي (LRI … PDI)، حتى لا يظهر «12 = N»
export const nEq = (n) => `\u2066N = ${n}\u2069`;
/** يحذف محارف العزل (للمقارنة في الاختبارات). */
export const stripIsolates = (t) => t.replace(/[\u2066-\u2069]/g, "");

/** نص خلية مستوى: الدرجة مع N وعدد المحتسب. */
export function levelCell(level) {
  if (level.n_cases === 0) return `لا حالات (${nEq(0)})`;
  const scored = level.n_scored === undefined ? "" : `، المحتسب ${level.n_scored}`;
  return level.score === null ? `لا درجة (${nEq(level.n_cases)}${scored})` : `${level.score} (${nEq(level.n_cases)}${scored})`;
}

/** صفوف جدول المقارنة: [عنوان المقياس، قيمة لكل مساعد بترتيب runs]. كل قيمة من الملف كما هي. */
export function comparisonRows(runs) {
  const rows = [
    ["الدرجة الكلية", runs.map((r) => `${r.overall_score} (${nEq(r.n_cases)}${r.n_scored === undefined ? "" : `، المحتسب ${r.n_scored}`})`)],
    ...LEVELS.map((lv) => [`المستوى ${lv}`, runs.map((r) => levelCell(r.levels[lv]))]),
    ["الإسنادات الخاطئة (wrong_or_missing)", runs.map((r) => fmt(r.wrong_citations))],
    ["الإحالة إلى مختص: التزم / لم يلتزم / لم يُحسم",
      runs.map((r) => (r.referral ? `${r.referral.passed} / ${r.referral.failed} / ${r.referral.undecided}` : "—"))],
    ["أُحيلت إلى مراجعة بشرية (بلا حكم آلي)", runs.map((r) => fmt(r.human_review_needed))],
    ["مراجعة شرعية متخصصة", runs.map((r) => `${r.human_reviewed.by_role.specialist} من ${r.human_reviewed.total}`)],
    ["تحقق من المصادر (ليس مراجعة شرعية)", runs.map((r) => `${r.human_reviewed.by_role.source_check} من ${r.human_reviewed.total}`)],
  ];
  return rows;
}

/** هل لم تُجرَ أي مراجعة شرعية متخصصة في التشغيلات المعروضة؟ */
export function noSpecialistReview(runs) {
  return runs.every((r) => r.human_reviewed.by_role.specialist === 0);
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

/** تنبيه ثابت بجوار المقارنة وقرار البوابة: ميل المقارنة لصالح rag، وصغر N. N من الملف لا من الصفحة. */
export const COMPARISON_CAVEAT =
  "مدخلات الأحاديث اليدوية التي يسترجعها rag أُعدّت لحالات الاختبار نفسها، فالمقارنة تميل لصالح rag.";
export function comparisonCaveat(runs) {
  const ns = [...new Set(runs.map((r) => r.n_cases))].sort((a, b) => a - b);
  return `تنبيه على المقارنة: ${COMPARISON_CAVEAT} والأرقام من عدد محدود من الحالات (${ns.map(nEq).join(" و")})، فلا تُعمَّم.`;
}
