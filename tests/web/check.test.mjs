// صفحة «تحقق من نص» (وضع ثانوي): تطابق نسخة المتصفح مع بايثون، وعرضها في متصفح حقيقي على 360 و1440.
//
// المرجع: tests/fixtures/paste_parity.json يولّده miyar/paste_check.py (ويتحقق tests/test_paste_check.py من تزامنه مع بايثون).
// هنا يُشغَّل check-core.js على النصوص نفسها ويُقارن بالنتيجة حرفياً. النصوص الموسومة FIXTURE اصطناعية؛
// لم يُستدعَ أي نموذج.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { QuranIndex, checkText, entryStatus, hintsFor, normalize, pyRound3, ratio, wordDiff } from "../../web/assets/check-core.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const WEB = join(ROOT, "web");
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml" };
const read = (p) => JSON.parse(readFileSync(join(ROOT, p), "utf8"));
const QURAN = read("web/assets/check/quran.json");
const HADITH = read("web/assets/check/hadith.json");
const PARITY = read("tests/fixtures/paste_parity.json");
const index = new QuranIndex(QURAN);

test("التوحيد في المتصفح يطابق بايثون على كل آيات المصحف (الرسمان)", () => {
  const h = createHash("sha256");
  QURAN.simple.forEach((s, i) => h.update(`${normalize(s)}\n${normalize(QURAN.uthmani[i])}\n`));
  assert.equal(h.digest("hex"), PARITY.normalized_digest);
});

test("نتائج المتصفح تطابق بايثون حرفياً على كل حالات التطابق", () => {
  assert.ok(PARITY.cases.length >= 80);
  for (const c of PARITY.cases) {
    assert.deepStrictEqual(JSON.parse(JSON.stringify(checkText(c.text, index, HADITH))), c.result, c.text.slice(0, 80));
  }
});

test("التلميحات للنص غير المستخرج تطابق بايثون حرفياً", () => {
  for (const c of PARITY.cases) {
    assert.deepStrictEqual(JSON.parse(JSON.stringify(hintsFor(c.text, index, HADITH))), c.hints, c.text.slice(0, 80));
  }
  const kinds = new Set(PARITY.cases.flatMap((c) => c.hints.map((h) => h.match)));
  assert.deepEqual([...kinds].sort(), ["literal", "near"]);
});

test("اقتراب حذف الحرف الواحد (كل المدخلات، كل حرف) يطابق بايثون ولا يُنتج «مؤيَّد»", () => {
  assert.ok(PARITY.near_fuzz.length > 200);
  let near = 0;
  for (const row of PARITY.near_fuzz) {
    const [r] = checkText(row.text, index, HADITH);
    assert.equal(r.status, row.status, row.text);
    assert.notEqual(r.status, "supported", row.text);
    assert.equal(r.reason, row.reason, row.text);
    assert.equal(r.entry_id, null, `عُدّ مطابقاً حرفياً (بحدود الكلمات لا الأحرف): ${row.text}`);
    assert.ok(["near_match_not_literal", "no_manual_entry"].includes(r.reason), row.text);
    assert.equal(r.near ? r.near.entry_id : null, row.near_id, row.text);
    assert.equal(r.near ? r.near.q_word : null, row.q_word, row.text);
    assert.equal(r.near ? r.near.entry_word : null, row.entry_word, row.text);
    assert.equal(r.near ? r.near.similarity : null, row.similarity, row.text);
    if (r.near) near++;
  }
  assert.ok(near > 200, `اقتراب في ${near} فقط`);
  assert.equal(PARITY.near_fuzz.length, 238);
});

test("لا «مؤيَّد» مع اقتراب في أي حالة، والمؤيَّد الحديثي بلا اقتراب ومعه مدخل", () => {
  for (const c of PARITY.cases) for (const r of checkText(c.text, index, HADITH)) {
    if (r.kind !== "hadith") continue;
    if (r.near) assert.equal(r.status, "needs_review");
    if (r.status === "supported") { assert.equal(r.near, null); assert.ok(r.entry && r.entry_id); }
  }
});

test("فروق الكلمات (LCS) كما في بايثون", () => {
  assert.deepStrictEqual(wordDiff("a b c d".split(" "), "a x c".split(" ")), [
    { q: [1, 2], w: [1, 2], q_words: ["b"], w_words: ["x"] }, { q: [3, 4], w: [3, 3], q_words: ["d"], w_words: [] }]);
  assert.deepStrictEqual(wordDiff(["a"], ["a"]), []);
});

test("الحالات تغطي كل فرع: مؤيَّد ولم تُطابَق ويحتاج تحقق، للآيات والأحاديث", () => {
  const seen = new Set(PARITY.cases.flatMap((c) => c.result.map((r) => `${r.kind}:${r.status}`)));
  for (const k of ["quran:supported", "quran:wrong_or_missing", "quran:needs_review", "hadith:supported", "hadith:needs_review"]) assert.ok(seen.has(k), k);
  const reasons = new Set(PARITY.cases.flatMap((c) => c.result.map((r) => r.reason)));
  for (const r of ["exact_match", "exact_match_unreferenced", "wrong_reference", "invalid_reference", "altered_text",
    "altered_text_unreferenced", "not_found", "quote_too_short", "matched_manual_entry", "no_manual_entry",
    "near_match_not_literal"]) assert.ok(reasons.has(r), r);
  assert.ok(PARITY.cases.some((c) => c.result.some((r) => r.diff && r.diff.chunks.length)), "فرق كلمات للآيات");
});

test("ملف الأحاديث للمتصفح فيه المدخلات المكتملة فقط", () => {
  assert.ok(HADITH.entries.length > 0);
  for (const e of HADITH.entries) assert.equal(entryStatus(e), "complete", e.id);
});

test("round(x, 3) والنسبة كما في بايثون", () => {
  assert.equal(pyRound3(0.0625), 0.062); // النصف إلى الزوجي
  assert.equal(pyRound3(0.8425), 0.842);
  assert.equal(ratio("abcd", "bcde"), 0.75);
  assert.equal(ratio("", ""), 1);
});

// ---------- في المتصفح ----------
async function loadPlaywright() {
  for (const spec of ["playwright", "/opt/node22/lib/node_modules/playwright/index.mjs"]) {
    try { return await import(spec); } catch { /* التالي */ }
  }
  return null;
}
const pw = await loadPlaywright();
const v = (s, a) => QURAN.simple[index.pos.get(`${s}:${a}`)];
const SAMPLE = [
  `FIXTURE: قال تعالى: ﴿${v(112, 1)}﴾ (الإخلاص: 1).`,
  "وقال: ﴿الحمد لله رب الناس﴾ (الفاتحة: 2).",
  `وقال رسول الله ﷺ: «${HADITH.entries[0].text}» رواه البخاري.`,
  "وقال ﷺ: «هذا نص اصطناعي ليس حديثاً في أي كتاب» رواه مسلم 5.",
].join("\n");

test("صفحة التحقق في المتصفح", { skip: !pw && !process.env.CI ? "Playwright غير متوفر محلياً" : false }, async (t) => {
  assert.ok(pw, "Playwright مطلوب في CI");
  const requests = [];
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    requests.push(path);
    try {
      const body = await readFile(join(WEB, path === "/" ? "index.html" : path));
      res.writeHead(200, { "content-type": TYPES[extname(path)] || "application/octet-stream" });
      res.end(body);
    } catch { res.writeHead(404); res.end(); }
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await pw.chromium.launch();
  try {
    for (const [width, scheme] of [[360, "light"], [360, "dark"], [1440, "light"]]) {
      const ctx = await browser.newContext({ viewport: { width, height: 800 }, colorScheme: scheme });
      const page = await ctx.newPage();
      const errors = [], external = [];
      page.on("pageerror", (e) => errors.push(e.message));
      page.on("request", (r) => { if (!r.url().startsWith(base)) external.push(r.url()); });
      const layout = () => page.evaluate(() => {
        const lum = (c) => {
          const [r, g, b] = c.match(/[\d.]+/g).slice(0, 3).map(Number).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; });
          return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        };
        const bgOf = (el) => {
          for (; el; el = el.parentElement) {
            const c = getComputedStyle(el).backgroundColor;
            if (c && c !== "transparent" && !/rgba\(.*,\s*0\)$/.test(c)) return c;
          }
          return "rgb(255, 255, 255)";
        };
        const low = [];
        for (const el of document.querySelectorAll("main *")) {
          if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
          const st = getComputedStyle(el);
          if (st.display === "none" || st.visibility === "hidden") continue;
          const a = lum(st.color), b = lum(bgOf(el));
          const cr = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          if (cr < 4.5) low.push(`${el.tagName}:${el.textContent.trim().slice(0, 20)}=${cr.toFixed(2)}`);
        }
        return { overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, low };
      });

      await t.test(`${width} ${scheme}: الحدود ظاهرة، ولا تُحمَّل بيانات المصحف قبل الضغط`, async () => {
        requests.length = 0;
        await page.goto(base + "check.html", { waitUntil: "networkidle" });
        const limits = await page.locator("#check-limits").innerText();
        for (const needle of ["ليست تقييماً لمساعد", "لا فتوى", "الأحاديث محدودة جداً", "يحتاج تحقق"]) assert.ok(limits.includes(needle), needle);
        assert.ok(!requests.includes("/assets/check/quran.json"), "حُمّل المصحف قبل الضغط");
      });

      await t.test(`${width} ${scheme}: لصق نص ← حكم لكل آية وحديث`, async () => {
        await page.fill("#check-text", SAMPLE);
        await page.click("#check-run");
        await page.waitForSelector(".check-card");
        assert.equal(await page.locator(".check-card").count(), 4);
        const text = await page.locator("#check-results").innerText();
        for (const needle of ["مؤيَّد", "لم تُطابَق", "يحتاج تحقق", "112:1", "1:2", "نقل محرّف", "H-001", "ضعيف", "لا مدخل مكتمل"]) {
          assert.ok(text.includes(needle), needle);
        }
        const l = await layout();
        assert.ok(l.overflow <= 0, `تمرير أفقي ${l.overflow}px`);
        assert.deepEqual(l.low, [], "تباين أقل من 4.5:1");
      });

      await t.test(`${width} ${scheme}: نص بلا اقتباس ← رسالة صريحة بلا حكم`, async () => {
        await page.fill("#check-text", "نص عادي بلا آية ولا حديث.");
        await page.click("#check-run");
        await page.waitForSelector("#check-results .notice");
        assert.match(await page.locator("#check-results").innerText(), /لم يُستخرج أي نص للفحص/);
      });
      await t.test(`${width} ${scheme}: حديث حُذف منه حرف ← «لم يُطابَق حرفياً» وأقرب مدخل بالكلمة المختلفة، ولا «مؤيَّد»`, async () => {
        await page.fill("#check-text", "قال رسول الله ﷺ: «اطلبوا العلم ولو بالصن» رواه البخاري 1.");
        await page.click("#check-run");
        await page.waitForSelector(".near-card");
        const card = page.locator(".check-card").first();
        const text = await card.innerText();
        for (const needle of ["لم يُطابَق حرفياً", "يحتاج تحقق", "أقرب مدخل", "H-001", "بالصن", "بالصين", "هذا ليس تأييداً", "للمقارنة فقط"]) {
          assert.ok(text.includes(needle), needle);
        }
        assert.ok(!text.includes("مؤيَّد"), "ظهر «مؤيَّد» مع نص غير مطابق");
        assert.equal(await card.locator(".badge.b-ok").count(), 0);
        const marks = await card.locator("mark.diff").allInnerTexts();
        assert.ok(marks.includes("بالصن") && marks.includes("بالصين"), `الإبراز: ${marks}`);
        assert.ok(marks.length >= 4, "إبراز في النص وفي المدخل وفي سطر الفرق");
        const l = await layout();
        assert.ok(l.overflow <= 0, `تمرير أفقي ${l.overflow}px`);
        assert.deepEqual(l.low, [], "تباين أقل من 4.5:1");
      });

      await t.test(`${width} ${scheme}: آية حُذف منها حرف ← إبراز الكلمة المختلفة في النص وفي نص الموضع`, async () => {
        await page.fill("#check-text", "قال تعالى: ﴿قل هو الله أح﴾ (الإخلاص: 1).");
        await page.click("#check-run");
        await page.waitForSelector(".diff-line");
        const text = await page.locator("#check-results").innerText();
        for (const needle of ["لم تُطابَق", "نقل محرّف", "الكلمة المختلفة", "كتبتَ «اح»", "«احد»"]) assert.ok(text.includes(needle), needle);
        const marks = await page.locator("#check-results mark.diff").allInnerTexts();
        assert.ok(marks.includes("اح") && marks.some((m) => m.startsWith("أَحَد")), `الإبراز: ${marks}`);
        assert.equal(await page.locator("#check-results .check-card .badge.b-ok").count(), 0);
        const l = await layout();
        assert.ok(l.overflow <= 0, `تمرير أفقي ${l.overflow}px`);
        assert.deepEqual(l.low, [], "تباين أقل من 4.5:1");
      });

      await t.test(`${width} ${scheme}: نص مقتبس بلا علامة نسبة ← تلميح بلا حكم (لا «مؤيَّد»)`, async () => {
        await page.fill("#check-text", "قال رسول اله: «اطلبوا العلم ولو بالصن»");
        await page.click("#check-run");
        await page.waitForSelector(".hint-card");
        const text = await page.locator("#check-results").innerText();
        for (const needle of ["لم يُستخرج أي استشهاد للفحص", "نصوص لم تُفحص", "لم يُفحص", "علامة نسبة", "H-001", "ولا حكم"]) assert.ok(text.includes(needle), needle);
        assert.ok(!text.includes("مؤيَّد"));
        assert.equal(await page.locator("#check-results .badge.b-ok, #check-results .badge.b-bad").count(), 0, "شارة حكم على نص لم يُفحص");
        const l = await layout();
        assert.ok(l.overflow <= 0, `تمرير أفقي ${l.overflow}px`);
        assert.deepEqual(l.low, [], "تباين أقل من 4.5:1");
      });

      assert.deepEqual(errors, []);
      assert.deepEqual(external, [], "طلب خارجي");
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
});
