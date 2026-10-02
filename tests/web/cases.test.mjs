import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeAr, matches } from "../../web/assets/cases.js";

test("توحيد النص العربي للبحث", () => {
  assert.equal(normalizeAr("إحالةٌ"), normalizeAr("احالة"));
  assert.equal(normalizeAr("OFF-05"), "off-05");
});

test("التصفية بالمستوى والنوع والبحث", () => {
  const row = { level: "D", type: "واقعة شخصية", text: "EXT-050 معلومة عامة + إحالة" };
  assert.ok(matches(row, { q: "", level: "", type: "" }));
  assert.ok(matches(row, { q: "احالة", level: "D", type: "واقعة شخصية" }));
  assert.ok(!matches(row, { q: "", level: "A", type: "" }));
  assert.ok(!matches(row, { q: "", level: "", type: "خلاف علماء" }));
  assert.ok(!matches(row, { q: "غير موجود", level: "", type: "" }));
});
