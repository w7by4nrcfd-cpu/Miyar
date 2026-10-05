// إعادة عرض تشغيل رسمي محفوظ: كل خطوة منقولة حرفياً من البيانات المنشورة (48 سجلاً)، ولا نص واجهة يوحي بتشغيل حي.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { checksSummary, verdict } from "../../web/assets/case-core.js";
import { BANNER, buildSteps, EXAMPLES, officialCases, parseState, REPLAY_LIMITS, SAVED_BADGE, stateQuery, STEP_TITLES,
  UI_COPY } from "../../web/assets/replay-core.js";

const read = (p) => JSON.parse(readFileSync(new URL(`../../web/${p}`, import.meta.url), "utf8"));
const meta = read("data/testcases.json");
const results = read("data/results.json");
const cases = officialCases(meta);
const records = Object.fromEntries(cases.map((c) => [c.id, read(`data/cases/${c.id}.json`)]));

test("كل السجلات الـ48: الخطوات السبع منقولة حرفياً من السجل", () => {
  let n = 0, referred = 0;
  for (const c of cases) {
    for (const run of records[c.id].runs) {
      n += 1;
      const s = buildSteps(c, run, results, meta);
      const j = run.judgement;
      assert.equal(s.length, STEP_TITLES.length);
      assert.equal(s[0].prompt, c.prompt);
      assert.equal(s[0].expected, c.expected_behavior);
      assert.deepEqual(s[0].references, c.references);
      assert.equal(s[1].answer, run.answer);
      assert.equal(s[1].runId, run.run_id);
      assert.equal(s[1].executedAt, run.executed_at);
      assert.deepEqual(s[2].citations, j.citations.map((x) => ({ kind: x.kind, quote: x.quote, cited: x.cited ?? null })));
      assert.deepEqual(s[3].citations.map(({ statusLabel, ...rest }) => rest),
        j.citations.map((x) => ({ kind: x.kind, quote: x.quote, status: x.status, reason: x.reason,
          matchedRef: x.matched_ref ?? null, matchedText: x.matched_text ?? null })));
      for (const x of s[3].citations) assert.equal(x.statusLabel, meta.citation_status_labels[x.status]);
      assert.deepEqual(s[4].verdict, verdict(j, meta.categories));
      assert.equal(s[4].rationale, j.rationale);
      assert.equal(s[4].confidence, j.confidence);
      assert.deepEqual(s[4].categories, j.categories);
      assert.equal(s[5].referred, j.needs_human_review);
      for (const k of s[5].checks) assert.equal(k.value, j.checks[k.name] ?? null);
      assert.equal(s[6].summary, checksSummary(j));
      const rr = results.runs.find((r) => r.run_id === run.run_id);
      assert.deepEqual(s[6].runScore, { score: rr.overall_score, nScored: rr.n_scored, nCases: rr.n_cases });
      if (j.needs_human_review) {
        referred += 1;
        assert.match(s[4].verdict.text, /أُحيلت إلى مراجعة بشرية ولم تدخل في الدرجة الآلية/);
      }
    }
  }
  assert.equal(n, 48);
  assert.equal(referred, 7);
});

test("الأمثلة الثلاثة: ثلاثة مسارات مختلفة من سجلات موجودة", () => {
  const pick = (e) => records[e.case].runs.find((r) => r.run_id === e.run);
  const [a, b, c] = EXAMPLES.map(pick);
  assert.ok(a && b && c);
  assert.ok(a.judgement.citations.some((x) => x.status === "supported") && !a.judgement.needs_human_review);
  assert.ok(b.judgement.citations.some((x) => x.status === "wrong_or_missing"));
  assert.equal(c.judgement.needs_human_review, true);
});

test("رابط المشاركة: الحالة والجولة والخطوة، والرجوع إلى المثال الأول عند أي قيمة غير صالحة", () => {
  assert.deepEqual(parseState(""), { caseId: "OFF-11", runId: "official-2026-10-04-baseline-3", step: 1 });
  const s = { caseId: "OFF-02", runId: "official-2026-10-04-rag-2", step: 4 };
  assert.deepEqual(parseState(stateQuery(s)), s);
  assert.equal(parseState("?case=OFF-02&run=official-2026-10-04-rag-2&step=9").step, 1);
  assert.equal(parseState("?case=<x>&run=a&step=2").caseId, "OFF-11");
});

test("نصوص الواجهة وحدها (لا محتوى السجل) لا توحي بتشغيل حي؛ والشريط بنصه", () => {
  assert.equal(BANNER, "إعادة عرض لتشغيل رسمي محفوظ — ليس تشغيلاً حياً");
  const ui = [...Object.values(UI_COPY), ...STEP_TITLES, ...REPLAY_LIMITS, ...EXAMPLES.map((e) => e.label), SAVED_BADGE];
  for (const t of ui) {
    assert.doesNotMatch(t, /الآن|مباشر|\blive\b|حياً|حيّ|تشغيل حي|جارٍ التحليل|جارٍ التقييم/i, t);
  }
});
