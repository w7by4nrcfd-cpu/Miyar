// صفحة النتائج في متصفح حقيقي (S3/S4): الحالة الفارغة الصادقة، وجدول المقارنة والبوابة من ملف نتائج اصطناعي.
//
// ⚠️ FIXTURE — بيانات اختبار مصطنعة، ليست نتائج حقيقية: ملف النتائج يُحقن في الطلب داخل المتصفح فقط (page.route)،
// ولا يُكتب في web/data/ أبداً. لم يُشغَّل أي مساعد ولم يُستدعَ أي نموذج.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "web");
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml" };

async function loadPlaywright() {
  for (const spec of ["playwright", "/opt/node22/lib/node_modules/playwright/index.mjs"]) {
    try { return await import(spec); } catch { /* التالي */ }
  }
  return null;
}

const level = (n, score, scored) => ({ n_cases: n, score, n_scored: scored });
const fxRun = (run_id, assistant, at, overall) => ({
  run_id, executed_at: at, assistant, model: "FIXTURE-model-not-called", testset: "official_v0", n_cases: 12,
  overall_score: overall, levels: { A: level(2, 100, 2), B: level(8, overall, 8), C: level(1, null, 0), D: level(1, 50, 1) },
  wrong_citations: 1, n_scored: 11, human_review_needed: 1, referral: { passed: 1, failed: 0, undecided: 0 },
  human_reviewed: { approved: 1, total: 12, by_role: { specialist: 0, source_check: 1 } },
  evaluation_record: `evaluation/official/${run_id}.json`,
});
const FIXTURE_RESULTS = {
  schema_version: 1,
  runs: [fxRun("FIXTURE-base-1", "baseline", "2000-01-01T00:00:00Z", 80), fxRun("FIXTURE-rag-1", "rag", "2000-01-01T00:10:00Z", 70)],
  gate: { rule: "FIXTURE قاعدة البوابة", reference_run_id: "FIXTURE-base-1", candidate_run_id: "FIXTURE-rag-1",
    allow: false, reasons: ["FIXTURE: الدرجة الكلية 70 أقل من المرجع 80"] },
};

const pw = await loadPlaywright();
const required = Boolean(process.env.CI);

test("صفحة النتائج: فارغة بصدق، ومقارنة وبوابة من ملف اصطناعي", { skip: !pw && !required ? "Playwright غير متوفر محلياً" : false }, async (t) => {
  assert.ok(pw, "Playwright مطلوب في CI");
  const server = createServer(async (req, res) => {
    const path = decodeURIComponent(new URL(req.url, "http://x").pathname);
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
    for (const width of [360, 1440]) {
      const ctx = await browser.newContext({ viewport: { width, height: 800 } });
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));

      await t.test(`${width}: ملف نتائج فارغ → «لا نتائج رسمية بعد» بلا أرقام`, async () => {
        // الفارغ يُمرَّر صراحةً: الاختبار لا يتوقف على ما نُشر في المستودع (مع سجلات رسمية أو بدونها)
        await page.route("**/data/results.json", (route) =>
          route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ schema_version: 1, runs: [] }) }));
        await page.goto(base + "results.html", { waitUntil: "networkidle" });
        const text = await page.locator("#results").innerText();
        assert.match(text, /لم يُشغَّل أي تقييم رسمي بعد/);
        assert.match(text, /لا نتائج رسمية بعد/);
        assert.equal(await page.locator("#compare").count(), 0);
        await page.unroute("**/data/results.json");
      });

      await t.test(`${width}: ملف اصطناعي → جدول المقارنة والبوابة دون تمرير أفقي`, async () => {
        await page.route("**/data/results.json", (route) =>
          route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FIXTURE_RESULTS) }));
        await page.goto(base + "results.html", { waitUntil: "networkidle" });
        const text = (await page.locator("#results").innerText()).replace(/[\u2066-\u2069]/g, "");
        for (const needle of ["المقارنة: baseline مقابل rag", "حجب rag", "FIXTURE قاعدة البوابة", "المراجعة الشرعية: مراجعة واحدة لحالة واحدة من 12 (OFF-06)",
          "80 (N = 12، المحتسب 11)", "لا درجة (N = 1، المحتسب 0)", "الثبات يحتاج تشغيلين رسميين"]) {
          assert.ok(text.includes(needle), needle);
        }
        assert.equal(await page.locator("#compare tbody tr").count(), 10);
        // بطاقة تمهيد واحدة في أعلى النتائج (لا بطاقتان متتاليتان) بعنوان يتبع عدد الجولات
        assert.equal(await page.locator("#results-notice").count(), 1);
        assert.equal(await page.locator("#results > .notice").first().getAttribute("id"), "results-notice");
        const head = (await page.locator("#results-notice strong").innerText()).replace(/[\u2066-\u2069]/g, "");
        assert.equal(FIXTURE_RESULTS.runs.length, 2);
        assert.equal(head, "نتائج جولتين رسميتين مسجّلتين في المستودع.");
        // أسماء الملفات في طبقة مطوية
        assert.equal(await page.locator("details#results-tech").getAttribute("open"), null);
        assert.ok((await page.locator("details#results-tech").textContent()).includes("evaluation/official/"));
        assert.equal(await page.locator("h1 + .notice").count(), 0, "لا بطاقة ثابتة قبل بطاقة JavaScript");
        // التنبيه ثابت بجوار المقارنة وبجوار قرار البوابة، مع N من الملف
        for (const id of ["#compare-caveat", "#gate-caveat"]) {
          const caveat = (await page.locator(id).innerText()).replace(/[\u2066-\u2069]/g, "");
          assert.match(caveat, /تميل لصالح rag/);
          assert.match(caveat, /N = 12/);
        }
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        assert.ok(overflow <= 0, `تمرير أفقي ${overflow}px`);
        await page.unroute("**/data/results.json");
      });
      assert.deepEqual(errors, []);
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
});
