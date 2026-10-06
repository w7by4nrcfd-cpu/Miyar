// رسم المقارنة في صفحة النتائج: كل قيمة فيه منسوخة من web/data/results.json حرفياً (لا رقم محسوب أو مكتوب يدوياً).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { chartData, CHART_METRICS, shortRunId } from "../../web/assets/results-core.js";

const results = JSON.parse(readFileSync(new URL("../../web/data/results.json", import.meta.url), "utf8"));

test("chartData: مقياس لكل من الكلية وA–D، وعمود لكل جولة رسمية بترتيب الملف", () => {
  const data = chartData(results.runs);
  assert.deepEqual(data.map((g) => g.key), CHART_METRICS.map(([k]) => k));
  assert.deepEqual(data.map((g) => g.key), ["overall", "A", "B", "C", "D"]);
  for (const g of data) assert.deepEqual(g.bars.map((b) => b.run), results.runs.map((r) => shortRunId(r.run_id)));
});

test("chartData: الدرجة والمحتسب والمقام مطابقة لـ results.json، والمستوى بلا درجة يبقى null لا صفراً", () => {
  const data = chartData(results.runs);
  results.runs.forEach((r, i) => {
    const o = data[0].bars[i];
    assert.deepEqual([o.score, o.n_scored, o.n_cases], [r.overall_score, r.n_scored, r.n_cases]);
    for (const [j, lv] of ["A", "B", "C", "D"].entries()) {
      const b = data[j + 1].bars[i], src = r.levels[lv];
      assert.deepEqual([b.score, b.n_scored, b.n_cases], [src.score, src.n_scored, src.n_cases]);
      if (src.score === null) assert.equal(b.score, null);
    }
  });
});

test("shortRunId: يحذف البادئة والتاريخ فقط", () => {
  assert.equal(shortRunId("official-2026-10-04-baseline-3"), "baseline-3");
  assert.equal(shortRunId("official-2026-10-04-rag-2"), "rag-2");
});
