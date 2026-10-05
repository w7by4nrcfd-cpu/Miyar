// إعادة عرض تشغيل رسمي محفوظ — منطق بلا DOM، قابل للاختبار بـ node --test.
// المصدر الوحيد: data/testcases.json وdata/results.json وdata/cases/<id>.json (قراءة فقط).
// لا يُعاد تشغيل أي نموذج، ولا يُحسب حكم جديد: كل خطوة تنقل حقول السجل كما هي.
import { checksSummary, checkText, verdict } from "./case-core.js";

/** الشريط الثابت في أعلى إعادة العرض. */
export const BANNER = "إعادة عرض لتشغيل رسمي محفوظ — ليس تشغيلاً حياً";
export const SAVED_BADGE = "تشغيل محفوظ";

export const STEP_TITLES = [
  "السؤال",
  "إجابة المساعد المُختبَر",
  "الاستشهادات المستخرجة من الإجابة",
  "المصدر والمطابقة",
  "حكم مِعيار",
  "فحوص السلوك",
  "النتيجة والقرار",
];

/** ثلاثة مسارات مختلفة لأحكام مِعيار (حالة × جولة)، أولها الافتراضي. */
export const EXAMPLES = [
  { case: "OFF-11", run: "official-2026-10-04-baseline-3", label: "استشهاد مؤيَّد بمطابقة" },
  { case: "OFF-02", run: "official-2026-10-04-baseline-3", label: "استشهاد لم يُطابَق" },
  { case: "OFF-06", run: "official-2026-10-04-baseline-3", label: "إحالة إلى مراجعة بشرية" },
];

/** ما لا يحفظه السجل الرسمي المنشور، فلا يُعرض ولا يُستنتج. */
export const REPLAY_LIMITS = [
  "مخرجات المستخرِج الخام قبل التحقق البرمجي؛ المحفوظ هو الاستشهادات المقبولة فقط.",
  "نص الطلب المرسل إلى الحَكَم.",
  "زمن كل خطوة.",
  "المقاطع التي استرجعها rag للمساعد.",
  "الرموز المستهلكة.",
  "درجة رقمية لكل حالة؛ يُعرض عدد الفحوص المحسومة كما في صفحة الحالة.",
];

/** نصوص الواجهة التي يكتبها إعادة العرض نفسه (لا محتوى السجل)؛ يفحصها اختبار منع إيحاء التشغيل الحي. */
export const UI_COPY = {
  heading: "كيف يحكم مِعيار؟ إعادة عرض خطوة بخطوة",
  examples: "ثلاثة مسارات مختلفة لأحكام مِعيار:",
  caseLabel: "الحالة",
  runLabel: "الجولة",
  prev: "السابق",
  next: "التالي",
  showAll: "اعرض كل الخطوات",
  showOne: "خطوة واحدة في كل مرة",
  limits: "حدود إعادة العرض",
  sourceDetails: "تفاصيل المصدر",
  noCitations: "لم يُستخرج من هذه الإجابة أي آية أو حديث.",
  noMatch: "لا نص مطابَق من البيانات لهذا الاستشهاد.",
  referralChecks: "أُحيلت هذه الإجابة إلى مراجعة بشرية ولم تدخل في الدرجة الآلية، فلا فحوص سلوك محسومة لها.",
  answerFrame: "إجابة المساعد المُختبَر — ليست من مِعيار",
  answerError: "تعذّر جواب المساعد في هذا التشغيل.",
  savedJudgement: "الحكم كما سُجّل في التشغيل الرسمي؛ وصحة الحكم نفسه لم تُقَس بعد.",
  runScore: "الدرجة الكلية لهذه الجولة",
  gateCandidate: "هذه الجولة هي المرشحة في قرار البوابة",
  gateReference: "هذه الجولة هي المرجع في قرار البوابة",
  gateNone: "هذه الجولة ليست طرفاً في قرار البوابة المنشور.",
  loadError: "تعذّر تحميل بيانات إعادة العرض",
  loadErrorNext: "تحقق من اتصالك ثم أعد تحميل الصفحة.",
  notFound: "لا سجل رسمي لهذا الاختيار",
};

const RUN = /^[a-z0-9-]{1,80}$/;
const CASE = /^[A-Z]+-\d{2,3}$/;

/** الحالة والجولة والخطوة من رابط المشاركة (?case=&run=&step=)، مع الرجوع إلى المثال الأول. */
export function parseState(search) {
  const q = new URLSearchParams(search);
  const c = q.get("case"), r = q.get("run"), s = Number.parseInt(q.get("step") ?? "1", 10);
  const ok = c && CASE.test(c) && r && RUN.test(r);
  return {
    caseId: ok ? c : EXAMPLES[0].case,
    runId: ok ? r : EXAMPLES[0].run,
    step: Number.isInteger(s) && s >= 1 && s <= STEP_TITLES.length ? s : 1,
  };
}

export function stateQuery({ caseId, runId, step }) {
  return `?case=${encodeURIComponent(caseId)}&run=${encodeURIComponent(runId)}&step=${step}`;
}

/** الحالات الرسمية التي لها سجل (official_v0) بترتيبها في البيانات. */
export function officialCases(meta) {
  return (meta?.cases ?? []).filter((c) => c.testset === "official_v0");
}

/** دور الجولة في قرار البوابة المنشور. */
export function gateRole(gate, runId) {
  if (!gate) return null;
  if (gate.candidate_run_id === runId) return "candidate";
  if (gate.reference_run_id === runId) return "reference";
  return null;
}

/**
 * يبني خطوات إعادة العرض السبع من السجل كما هو.
 * كل قيمة معروضة منقولة من الحقول؛ والنصوص المشتقة (الحكم، ملخص الفحوص) من case-core نفسها.
 */
export function buildSteps(caseMeta, run, results, meta) {
  const j = run.judgement ?? null;
  const cits = j?.citations ?? [];
  const labels = meta?.citation_status_labels ?? {};
  const resRun = (results?.runs ?? []).find((r) => r.run_id === run.run_id) ?? null;
  const gate = results?.gate ?? null;
  return [
    { key: "question", prompt: caseMeta.prompt, masked: !!caseMeta.prompt_masked, trap: !!caseMeta.trap,
      injectedContext: caseMeta.injected_context ?? null, level: caseMeta.level, levelBehavior: caseMeta.level_behavior,
      expected: caseMeta.expected_behavior, references: caseMeta.references ?? [] },
    { key: "answer", answer: run.answer ?? "", error: run.error ?? null, assistant: run.assistant,
      answerModel: run.answer_model ?? null, runId: run.run_id, executedAt: run.executed_at },
    { key: "citations", citations: cits.map((c) => ({ kind: c.kind, quote: c.quote, cited: c.cited ?? null })) },
    { key: "matching",
      citations: cits.map((c) => ({ kind: c.kind, quote: c.quote, status: c.status, statusLabel: labels[c.status] ?? c.status,
        reason: c.reason, matchedRef: c.matched_ref ?? null, matchedText: c.matched_text ?? null })),
    },
    { key: "verdict", verdict: verdict(j, meta?.categories ?? {}), categories: j?.categories ?? [],
      confidence: j?.confidence ?? null, rationale: j?.rationale ?? "", judgeModel: j?.judge_model ?? null,
      reviewReason: j?.review_reason ?? null, referred: !!j?.needs_human_review },
    { key: "checks", referred: !!j?.needs_human_review,
      checks: (caseMeta.checks ?? []).map((k) => {
        const value = j?.checks?.[k.name] ?? null;
        return { name: k.name, description: k.description, value, text: checkText(value) };
      }) },
    { key: "result", summary: checksSummary(j), verdict: verdict(j, meta?.categories ?? {}),
      runScore: resRun ? { score: resRun.overall_score, nScored: resRun.n_scored, nCases: resRun.n_cases } : null,
      gateRole: gateRole(gate, run.run_id), gateAllow: gate ? gate.allow : null, gateReasons: gate?.reasons ?? [],
      candidate: gate?.candidate_run_id ?? null, reference: gate?.reference_run_id ?? null },
  ];
}

/** اسم مختصر للجولة للعرض (baseline-3 من official-2026-10-04-baseline-3). */
export function runShort(runId) {
  return runId.split("-").slice(-2).join("-");
}
