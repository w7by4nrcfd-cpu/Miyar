// «اختبر مساعدك»: العدّ نقي ومن أحكام check-core نفسها؛ ولا يُنشئ الملف حكماً جديداً.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { tally } from "../../web/assets/batch.js";
import { QuranIndex, checkText, SUPPORTED, NEEDS_REVIEW, WRONG_OR_MISSING } from "../../web/assets/check-core.js";

const read = (p) => JSON.parse(readFileSync(new URL(`../../web/${p}`, import.meta.url), "utf8"));

test("tally: يعدّ الأحكام الثلاثة فقط، والفارغ أصفار", () => {
  assert.deepEqual(tally([]), { [SUPPORTED]: 0, [NEEDS_REVIEW]: 0, [WRONG_OR_MISSING]: 0 });
  assert.deepEqual(tally([{ status: SUPPORTED }, { status: SUPPORTED }, { status: WRONG_OR_MISSING }]),
    { [SUPPORTED]: 2, [NEEDS_REVIEW]: 0, [WRONG_OR_MISSING]: 1 });
});

test("الإجابات المحفوظة تُفحص بـ checkText نفسه: آية صحيحة مؤيَّدة، ومحرّفة لم تُطابَق، وكل إجابة رسمية تُفحص بلا خطأ", () => {
  const index = new QuranIndex(read("assets/check/quran.json"));
  const hadith = read("assets/check/hadith.json");
  assert.deepEqual(tally(checkText("قال تعالى: ﴿قُلۡ هُوَ ٱللَّهُ أَحَدٌ﴾ (الإخلاص: 1)", index, hadith)), { [SUPPORTED]: 1, [NEEDS_REVIEW]: 0, [WRONG_OR_MISSING]: 0 });
  assert.deepEqual(tally(checkText("قال تعالى: ﴿قل هو الله واحد﴾ (الإخلاص: 1)", index, hadith)), { [SUPPORTED]: 0, [NEEDS_REVIEW]: 0, [WRONG_OR_MISSING]: 1 });
  const meta = read("data/testcases.json");
  for (const c of meta.cases.filter((x) => x.testset === "official_v0")) {
    for (const r of read(`data/cases/${c.id}.json`).runs) {
      const t = tally(checkText(r.answer, index, hadith));
      assert.ok(Object.values(t).every((n) => Number.isInteger(n) && n >= 0), `${c.id} ${r.run_id}`);
    }
  }
});
