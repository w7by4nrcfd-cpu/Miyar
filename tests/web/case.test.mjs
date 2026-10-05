// صفحة تفصيل الحالة: منطقها (node --test) وعرضها في متصفح حقيقي على 360 و1440.
//
// ⚠️ FIXTURE — بيانات اختبار مصطنعة، ليست نتائج حقيقية: سجل الحالة أدناه يُحقن في الطلب داخل المتصفح فقط (page.route)
// ولا يُكتب في web/data/ أبداً. لم يُشغَّل أي مساعد ولم يُستدعَ أي نموذج.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { caseIdFrom, checksSummary, interpretRecord, latestRuns, verdict } from "../../web/assets/case-core.js";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "web");
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml" };

const judgement = (patch = {}) => ({
  checks: { correct_misquote: true, cite_source: true, no_fabricated_citation: false }, confidence: 0.9,
  judge_model: "FIXTURE-judge", needs_human_review: false, review_reason: null, rationale: "FIXTURE سبب الحكم",
  program_overrides: [], categories: ["altered"], unnecessary_refusal: false,
  citations: [
    { kind: "quran", quote: "FIXTURE نص كما ورد", cited: "طه: 114", status: "wrong_or_missing", reason: "altered_text", matched_ref: "20:114", matched_text: "FIXTURE نص من البيانات" },
    { kind: "hadith", quote: "FIXTURE حديث", cited: null, status: "needs_review", reason: "no_manual_entry", matched_ref: null, matched_text: null },
  ],
  ...patch,
});
const run = (assistant, at, patch = {}) => ({
  run_id: `FIXTURE-${assistant}`, executed_at: at, assistant, answer_model: "FIXTURE-model", answer: `FIXTURE إجابة ${assistant}`,
  error: null, judgement: judgement(), ...patch,
});
const RECORD = { schema_version: 1, id: "OFF-11", runs: [run("baseline", "2000-01-01T00:00:00Z"), run("rag", "2000-01-01T00:10:00Z")] };
const ok = (obj) => ({ status: 200, ok: true, text: JSON.stringify(obj) });

// ---------- المنطق ----------
test("معرّف الحالة من العنوان، ويُرفض غير الصالح", () => {
  assert.equal(caseIdFrom("?id=OFF-05"), "OFF-05");
  assert.equal(caseIdFrom("?id=../x"), null);
  assert.equal(caseIdFrom(""), null);
});

test("غياب السجل → «none»، والسجل الصالح → ok", () => {
  assert.deepEqual(interpretRecord(null, "OFF-11"), { state: "none" });
  assert.deepEqual(interpretRecord({ status: 404, ok: false, text: "" }, "OFF-11"), { state: "none" });
  assert.equal(interpretRecord(ok(RECORD), "OFF-11").state, "ok");
});

test("سجل لا يطابق العقد → غير صالح بلا حكم", () => {
  assert.equal(interpretRecord(ok({ ...RECORD, id: "OFF-01" }), "OFF-11").state, "invalid");
  const bad = structuredClone(RECORD);
  bad.runs[0].judgement.citations[0] = { ...bad.runs[0].judgement.citations[0], status: "supported", matched_text: null };
  assert.equal(interpretRecord(ok(bad), "OFF-11").state, "invalid"); // «مؤيَّد» بلا نص مطابَق
  assert.equal(interpretRecord({ status: 200, ok: true, text: "{x" }, "OFF-11").state, "invalid");
});

test("الحكم النهائي من السجل كما هو", () => {
  assert.equal(verdict(judgement(), { altered: "محرَّف" }).text, "أخطاء مرصودة: محرَّف");
  assert.equal(verdict(judgement({ categories: [] })).kind, "ok");
  assert.match(verdict(judgement({ needs_human_review: true, review_reason: "low_confidence" })).text, /مراجعة بشرية ولم تدخل في الدرجة الآلية/);
  assert.match(verdict(judgement({ needs_human_review: true, review_reason: "hadith_unverified" })).text,
    /مراجعة بشرية ولم تدخل في الدرجة الآلية \(استشهاد حديثي بلا مدخل مكتمل في الملف اليدوي/);
  assert.equal(verdict(null).kind, "none");
  assert.equal(checksSummary(judgement()), "2 من 3 فحوص محسومة");
  assert.deepEqual(latestRuns([run("rag", "2000-01-01T00:00:00Z"), run("baseline", "2000-01-01T00:00:00Z")]).map((r) => r.assistant), ["baseline", "rag"]);
});

// ---------- في المتصفح ----------
async function loadPlaywright() {
  for (const spec of ["playwright", "/opt/node22/lib/node_modules/playwright/index.mjs"]) {
    try { return await import(spec); } catch { /* التالي */ }
  }
  return null;
}
const pw = await loadPlaywright();

test("صفحة الحالة في المتصفح", { skip: !pw && !process.env.CI ? "Playwright غير متوفر محلياً" : false }, async (t) => {
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
    for (const [width, scheme] of [[360, "light"], [360, "dark"], [1440, "light"]]) {
      const ctx = await browser.newContext({ viewport: { width, height: 800 }, colorScheme: scheme });
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      const layout = () => page.evaluate(() => {
        const lum = (c) => {
          const [r, g, b] = c.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
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
        for (const el of document.querySelectorAll("#case *")) {
          if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
          const st = getComputedStyle(el);
          if (st.display === "none" || st.visibility === "hidden") continue;
          const a = lum(st.color), b = lum(bgOf(el));
          const cr = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          if (cr < 4.5) low.push(`${el.tagName}:${el.textContent.trim().slice(0, 20)}=${cr.toFixed(2)}`);
        }
        return { overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, low };
      });

      await t.test(`${width} ${scheme}: بلا سجل رسمي → السؤال والتنبيه والنص الصحيح و«ليست ضمن الحالات الاثنتي عشرة المُشغَّلة رسمياً»`, async () => {
        // غياب ملف الحالة يُفرض صراحةً (404)، فلا يتوقف الاختبار على ما نُشر في web/data/cases/
        await page.route("**/data/cases/OFF-11.json", (r) => r.fulfill({ status: 404, body: "" }));
        await page.goto(base + "case.html?id=OFF-11", { waitUntil: "networkidle" });
        const text = await page.locator("#case").innerText();
        for (const needle of ["OFF-11", "السؤال", "تنبيه", "النص الصحيح من البيانات", "طه 20:114", "السلوك المتوقع", "ليست ضمن الحالات الاثنتي عشرة المُشغَّلة رسمياً"]) {
          assert.ok(text.includes(needle), needle);
        }
        assert.equal(await page.locator(".answer-card").count(), 0);
        const l = await layout();
        assert.ok(l.overflow <= 0, `تمرير أفقي ${l.overflow}px`);
        assert.deepEqual(l.low, [], "تباين أقل من 4.5:1");
        await page.unroute("**/data/cases/OFF-11.json");
      });

      await t.test(`${width} ${scheme}: سجل اصطناعي → الإجابة والاستشهادات والحكم والثقة والسبب`, async () => {
        await page.route("**/data/cases/OFF-11.json", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(RECORD) }));
        await page.goto(base + "case.html?id=OFF-11", { waitUntil: "networkidle" });
        const text = await page.locator("#case").innerText();
        for (const needle of ["إجابة المساعد المُختبَر — ليست من مِعيار", "FIXTURE إجابة baseline", "FIXTURE إجابة rag",
          "خاطئ أو غير موجود", "يحتاج تحقق", "FIXTURE نص من البيانات", "أخطاء مرصودة: محرَّف", "0.90", "FIXTURE سبب الحكم", "لم يلتزم"]) {
          assert.ok(text.includes(needle), needle);
        }
        assert.equal(await page.locator(".answer-card").count(), 2);
        const l = await layout();
        assert.ok(l.overflow <= 0, `تمرير أفقي ${l.overflow}px`);
        assert.deepEqual(l.low, [], "تباين أقل من 4.5:1");
        await page.unroute("**/data/cases/OFF-11.json");
      });

      await t.test(`${width} ${scheme}: معرّف غير موجود → رسالة واضحة`, async () => {
        await page.goto(base + "case.html?id=XYZ-999", { waitUntil: "networkidle" });
        assert.match(await page.locator("#case").innerText(), /لا توجد حالة بالمعرّف XYZ-999/);
      });

      await t.test(`${width} ${scheme}: من قائمة الحالات إلى صفحة الحالة بنقرة`, async () => {
        await page.goto(base + "cases.html", { waitUntil: "networkidle" });
        await page.click('a[href="case.html?id=OFF-05"]');
        await page.waitForLoadState("networkidle");
        assert.match(await page.locator("#case").innerText(), /OFF-05[\s\S]*لا حكم مستقل/);
      });
      assert.deepEqual(errors, []);
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
});
