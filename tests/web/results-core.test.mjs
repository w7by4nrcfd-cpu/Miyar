// اختبارات منطق صفحة النتائج: node --test tests/web/*.test.mjs
//
// ⚠️ FIXTURE — بيانات اختبار مصطنعة، ليست نتائج حقيقية.
// FIXTURE_RUN أدناه كائن وهمي لاختبار المتحقق فقط: لم يُشغَّل أي مساعد ولم يُستدعَ أي نموذج.
// قيمه موسومة بـ FIXTURE، ولا تُنسخ إلى web/data/ أبداً (يتحقق من ذلك tests/test_fixtures.py).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { interpretResults, validateResults, reviewedRatio, reviewSummaryText } from "../../web/assets/results-core.js";

const read = (p) => readFileSync(new URL(`../../${p}`, import.meta.url), "utf8");
const ok = (text) => ({ status: 200, ok: true, text });
const json = (obj) => ok(JSON.stringify(obj));

const FIXTURE_RUN = Object.freeze({
  run_id: "FIXTURE-not-a-real-result",
  executed_at: "2000-01-01T00:00:00Z", // تاريخ وهمي عمداً
  assistant: "FIXTURE-assistant",
  model: "FIXTURE-model-not-called",
  testset: "official_v0",
  n_cases: 12,
  overall_score: 50,
  levels: {
    A: { n_cases: 3, score: 50 },
    B: { n_cases: 7, score: 50 },
    C: { n_cases: 1, score: 50 },
    D: { n_cases: 1, score: 50 },
  },
  wrong_citations: 2,
  human_reviewed: { approved: 0, total: 12, by_role: { specialist: 0, source_check: 0 } },
  evaluation_record: "evaluation/official/FIXTURE-not-a-real-record.json",
});
const withRun = (patch) => ({ schema_version: 1, runs: [{ ...structuredClone(FIXTURE_RUN), ...patch }] });

// ---------- الحالة الفارغة ----------
test("الملف غير موجود أو تعذّر الوصول → فارغ", () => {
  assert.deepEqual(interpretResults(null), { state: "empty" });
  assert.deepEqual(interpretResults({ status: 404, ok: false, text: "" }), { state: "empty" });
});

test("ملف فارغ أو مسافات فقط → فارغ", () => {
  assert.equal(interpretResults(ok("")).state, "empty");
  assert.equal(interpretResults(ok("  \n ")).state, "empty");
});

test("runs فارغة → فارغ", () => {
  assert.equal(interpretResults(json({ schema_version: 1, runs: [] })).state, "empty");
});

test("الملف المنشور web/data/results.json صالح: فارغ إن لم تُنشر سجلات، وإلا «ok» ولكل تشغيل سجل في evaluation/official/", () => {
  const raw = read("web/data/results.json");
  const view = interpretResults(ok(raw));
  const runs = JSON.parse(raw).runs;
  if (runs.length === 0) {
    assert.equal(view.state, "empty");
  } else {
    assert.equal(view.state, "ok");
    for (const r of runs) assert.match(r.evaluation_record, /^evaluation\/official\/[^/]+\.json$/);
  }
});

// ---------- الحالة غير الصالحة ----------
test("JSON غير صالح → غير صالح، بلا بيانات", () => {
  const view = interpretResults(ok("{ not json"));
  assert.equal(view.state, "invalid");
  assert.equal(view.runs, undefined);
});

test("خطأ في الخادم → غير صالح", () => {
  assert.equal(interpretResults({ status: 500, ok: false, text: "" }).state, "invalid");
});

for (const [name, data] of [
  ["جذر ليس كائناً", [1, 2]],
  ["جذر null", null],
  ["{} بلا حقول", {}],
  ["إصدار مخطط خاطئ", { schema_version: 2, runs: [] }],
  ["runs ليست قائمة", { schema_version: 1, runs: {} }],
  ["درجة أكبر من 100", withRun({ overall_score: 150 })],
  ["درجة نصية", withRun({ overall_score: "90" })],
  ["n_cases صفر", withRun({ n_cases: 0 })],
  ["مجموع المستويات لا يساوي N", withRun({ n_cases: 13, human_reviewed: { approved: 0, total: 13, by_role: { specialist: 0, source_check: 0 } } })],
  ["مستوى ناقص", withRun({ levels: { A: { n_cases: 12, score: 1 } } })],
  ["مستوى بلا حالات وله درجة", withRun({ levels: { ...FIXTURE_RUN.levels, C: { n_cases: 0, score: 10 }, A: { n_cases: 4, score: 50 } } })],
  ["مستوى غير معروف", withRun({ levels: { ...FIXTURE_RUN.levels, E: { n_cases: 0, score: null } } })],
  ["إسنادات خاطئة سالبة", withRun({ wrong_citations: -1 })],
  ["مراجَع أكثر من الكل", withRun({ human_reviewed: { approved: 13, total: 12, by_role: { specialist: 13, source_check: 0 } } })],
  ["إجمالي المراجعة لا يساوي N", withRun({ human_reviewed: { approved: 0, total: 5, by_role: { specialist: 0, source_check: 0 } } })],
  ["المراجعة بلا تفصيل حسب النوع", withRun({ human_reviewed: { approved: 0, total: 12 } })],
  ["مجموع الأنواع لا يساوي المقبول", withRun({ human_reviewed: { approved: 3, total: 12, by_role: { specialist: 1, source_check: 1 } } })],
  ["نوع مراجعة غير معروف", withRun({ human_reviewed: { approved: 0, total: 12, by_role: { specialist: 0, source_check: 0, scholar: 0 } } })],
  ["نوع مراجعة سالب", withRun({ human_reviewed: { approved: 0, total: 12, by_role: { specialist: -1, source_check: 1 } } })],
  ["سجل تشغيل خارج evaluation/", withRun({ evaluation_record: "somewhere/x.json" })],
  ["سجل داخل evaluation/ لكن خارج official/", withRun({ evaluation_record: "evaluation/x.json" })],
  ["سجل يخرج من official/ بـ ..", withRun({ evaluation_record: "evaluation/official/../x.json" })],
  ["بادئة تشبه official", withRun({ evaluation_record: "evaluation/officialx/x.json" })],
  ["سجل تشغيل تطوير (DEV_RUN)", withRun({ evaluation_record: "evaluation/dev/run.json" })],
  ["مجلد التطوير نفسه", withRun({ evaluation_record: "evaluation/dev" })],
  ["تاريخ غير صالح", withRun({ executed_at: "أمس" })],
  ["run_id مكرر", { schema_version: 1, runs: [FIXTURE_RUN, FIXTURE_RUN] }],
]) {
  test(`مخالف للمخطط: ${name} → غير صالح`, () => {
    const view = interpretResults(json(data));
    assert.equal(view.state, "invalid");
    assert.ok(view.errors.length > 0);
    assert.equal(view.runs, undefined);
  });
}

test("كل حقل إلزامي في المخطط الموثّق يرفضه المتحقق عند غيابه", () => {
  const schema = JSON.parse(read("web/data/results.schema.json"));
  const required = schema.$defs.run.required;
  assert.ok(required.length >= 11);
  for (const key of required) {
    const run = structuredClone(FIXTURE_RUN);
    delete run[key];
    assert.ok(validateResults({ schema_version: 1, runs: [run] }).length > 0, `لم يُرفض غياب ${key}`);
  }
  assert.deepEqual(Object.keys(FIXTURE_RUN).sort(), [...required].sort());
});

// ---------- الحالة الصالحة ----------
test("تشغيل صالح → ok", () => {
  const view = interpretResults(json({ schema_version: 1, runs: [FIXTURE_RUN] }));
  assert.equal(view.state, "ok");
  assert.equal(view.runs.length, 1);
  assert.equal(reviewedRatio(view.runs[0]), 0);
});

test("عرض المراجعة يفصل التخصص الشرعي عن تحقق المصادر", () => {
  const run = { ...structuredClone(FIXTURE_RUN), human_reviewed: { approved: 5, total: 12, by_role: { specialist: 2, source_check: 3 } } };
  assert.equal(validateResults({ schema_version: 1, runs: [run] }).length, 0);
  const [spec, src] = reviewSummaryText(run);
  assert.match(spec, /مراجعة شرعية متخصصة: 2 من 12/);
  assert.match(src, /3 من 12/);
  assert.match(src, /ليس مراجعة شرعية متخصصة/);
});

test("الـfixture موسوم صراحةً بأنه ليس نتيجة حقيقية", () => {
  for (const key of ["run_id", "assistant", "model", "evaluation_record"]) {
    assert.match(FIXTURE_RUN[key], /FIXTURE/);
  }
});

// ---------- المقارنة والبوابة والثبات (S3/S4) — بيانات FIXTURE مصطنعة ----------
import { comparisonRows, latestByAssistant, levelCell, noSpecialistReview, stripIsolates } from "../../web/assets/results-core.js";

const fxRun = (patch) => ({ ...structuredClone(FIXTURE_RUN), n_scored: 11, human_review_needed: 1,
  referral: { passed: 1, failed: 0, undecided: 0 }, ...patch });
const FX_BASE = fxRun({ run_id: "FIXTURE-base-1", assistant: "baseline", executed_at: "2000-01-01T00:00:00Z" });
const FX_RAG = fxRun({ run_id: "FIXTURE-rag-1", assistant: "rag", executed_at: "2000-01-01T00:10:00Z" });
const FX_GATE = { rule: "FIXTURE rule", reference_run_id: "FIXTURE-base-1", candidate_run_id: "FIXTURE-rag-1",
  allow: false, reasons: ["FIXTURE reason"] };

test("ملف فيه gate وstability صالح → ok مع القرار", () => {
  const data = { schema_version: 1, runs: [FX_BASE, FX_RAG], gate: FX_GATE,
    stability: { baseline: { run_ids: ["FIXTURE-base-1", "FIXTURE-rag-1"], overall: {}, levels: {} } } };
  const view = interpretResults(json(data));
  assert.equal(view.state, "ok");
  assert.equal(view.gate.allow, false);
  assert.deepEqual(Object.keys(view.stability), ["baseline"]);
});

test("gate يشير إلى تشغيل غير منشور → غير صالح", () => {
  const data = { schema_version: 1, runs: [FX_BASE], gate: FX_GATE };
  const view = interpretResults(json(data));
  assert.equal(view.state, "invalid");
  assert.ok(view.errors.some((e) => e.includes("candidate_run_id")));
});

test("مستوى بلا حالة محتسبة: درجته null صالحة؛ وnull مع محتسب > 0 غير صالحة", () => {
  const good = fxRun({ levels: { ...FIXTURE_RUN.levels, C: { n_cases: 1, score: null, n_scored: 0 } } });
  assert.equal(validateResults({ schema_version: 1, runs: [good] }).length, 0);
  const bad = fxRun({ levels: { ...FIXTURE_RUN.levels, C: { n_cases: 1, score: null, n_scored: 1 } } });
  assert.ok(validateResults({ schema_version: 1, runs: [bad] }).length > 0);
  const tooMany = fxRun({ levels: { ...FIXTURE_RUN.levels, C: { n_cases: 1, score: 50, n_scored: 2 } } });
  assert.ok(validateResults({ schema_version: 1, runs: [tooMany] }).length > 0);
});

test("آخر تشغيل لكل مساعد، baseline ثم rag", () => {
  const older = { ...FX_BASE, run_id: "FIXTURE-base-0", executed_at: "1999-01-01T00:00:00Z" };
  assert.deepEqual(latestByAssistant([FX_RAG, older, FX_BASE]).map((r) => r.run_id), ["FIXTURE-base-1", "FIXTURE-rag-1"]);
});

test("صفوف المقارنة تنقل القيم كما هي مع N", () => {
  const rows = comparisonRows([FX_BASE, FX_RAG]);
  assert.equal(rows[0][0], "الدرجة الكلية");
  assert.deepEqual(rows[0][1].map(stripIsolates), ["50 (N = 12، المحتسب 11)", "50 (N = 12، المحتسب 11)"]);
  assert.equal(rows.length, 1 + 4 + 5);
  assert.equal(stripIsolates(levelCell({ n_cases: 0, score: null })), "لا حالات (N = 0)");
  assert.equal(stripIsolates(levelCell({ n_cases: 2, score: null, n_scored: 0 })), "لا درجة (N = 2، المحتسب 0)");
  assert.equal(noSpecialistReview([FX_BASE, FX_RAG]), true);
});

import { comparisonCaveat, COMPARISON_CAVEAT } from "../../web/assets/results-core.js";

test("تنبيه المقارنة يذكر ميلها لصالح rag وN من الملف", () => {
  const text = stripIsolates(comparisonCaveat([FX_BASE, FX_RAG]));
  assert.ok(text.includes(COMPARISON_CAVEAT));
  assert.match(text, /أُعدّت لحالات الاختبار نفسها/);
  assert.match(text, /\(N = 12\)/);
  const mixed = stripIsolates(comparisonCaveat([FX_BASE, { ...FX_RAG, n_cases: 51 }]));
  assert.match(mixed, /N = 12 وN = 51/);
});
