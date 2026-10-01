// اختبارات منطق صفحة النتائج: node --test tests/web/
// تنبيه: VALID_RUN بيانات اختبار وهمية داخل الاختبار فقط، ولا تُكتب في web/data/ أبداً.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { interpretResults, validateResults, reviewedRatio } from "../../web/assets/results-core.js";

const read = (p) => readFileSync(new URL(`../../${p}`, import.meta.url), "utf8");
const ok = (text) => ({ status: 200, ok: true, text });
const json = (obj) => ok(JSON.stringify(obj));

const VALID_RUN = Object.freeze({
  run_id: "fixture-1",
  executed_at: "2026-10-05T10:00:00Z",
  assistant: "baseline",
  model: "fixture-model",
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
  human_reviewed: { approved: 0, total: 12 },
  evaluation_record: "evaluation/runs/fixture-1.json",
});
const withRun = (patch) => ({ schema_version: 1, runs: [{ ...structuredClone(VALID_RUN), ...patch }] });

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

test("الملف المنشور web/data/results.json فارغ حالياً (لا نتائج مصطنعة)", () => {
  const view = interpretResults(ok(read("web/data/results.json")));
  assert.equal(view.state, "empty");
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
  ["مجموع المستويات لا يساوي N", withRun({ n_cases: 13, human_reviewed: { approved: 0, total: 13 } })],
  ["مستوى ناقص", withRun({ levels: { A: { n_cases: 12, score: 1 } } })],
  ["مستوى بلا حالات وله درجة", withRun({ levels: { ...VALID_RUN.levels, C: { n_cases: 0, score: 10 }, A: { n_cases: 4, score: 50 } } })],
  ["مستوى غير معروف", withRun({ levels: { ...VALID_RUN.levels, E: { n_cases: 0, score: null } } })],
  ["إسنادات خاطئة سالبة", withRun({ wrong_citations: -1 })],
  ["مراجَع أكثر من الكل", withRun({ human_reviewed: { approved: 13, total: 12 } })],
  ["إجمالي المراجعة لا يساوي N", withRun({ human_reviewed: { approved: 0, total: 5 } })],
  ["سجل تشغيل خارج evaluation/", withRun({ evaluation_record: "somewhere/x.json" })],
  ["تاريخ غير صالح", withRun({ executed_at: "أمس" })],
  ["run_id مكرر", { schema_version: 1, runs: [VALID_RUN, VALID_RUN] }],
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
    const run = structuredClone(VALID_RUN);
    delete run[key];
    assert.ok(validateResults({ schema_version: 1, runs: [run] }).length > 0, `لم يُرفض غياب ${key}`);
  }
  assert.deepEqual(Object.keys(VALID_RUN).sort(), [...required].sort());
});

// ---------- الحالة الصالحة ----------
test("تشغيل صالح → ok", () => {
  const view = interpretResults(json({ schema_version: 1, runs: [VALID_RUN] }));
  assert.equal(view.state, "ok");
  assert.equal(view.runs.length, 1);
  assert.equal(reviewedRatio(view.runs[0]), 0);
});
