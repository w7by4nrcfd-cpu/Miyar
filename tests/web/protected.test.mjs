// حماية الأدلة بعد ضغط المحتوى (PR4): كل حقيقة علمية وكل تنبيه ضروري يبقى في الصفحة، والأساسي منها ظاهر مباشرة،
// وميزانية للكلمات الظاهرة (الأقسام المطوية مغلقة) تمنع عودة التضخم. القيم المتوقعة محسوبة من البيانات المنشورة لا مكتوبة يدوياً.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { AGREEMENT_NOTE, gateRuleNote, officialRunsHeadline, overallScoresNote, reasonDenominator } from "../../web/assets/results-core.js";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "web");
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml" };
const read = (p) => JSON.parse(readFileSync(join(WEB, p), "utf8"));
async function loadPlaywright() {
  for (const spec of ["playwright", "/opt/node22/lib/node_modules/playwright/index.mjs"]) {
    try { return await import(spec); } catch { /* التالي */ }
  }
  return null;
}
const pw = await loadPlaywright();

// ---------- القيم المحمية من البيانات المنشورة ----------
const results = read("data/results.json");
const meta = read("data/testcases.json");
const official = meta.cases.filter((c) => c.testset === "official_v0");
const records = official.map((c) => read(`data/cases/${c.id}.json`));
const runsAll = records.flatMap((r) => r.runs);
const cits = runsAll.flatMap((r) => r.judgement?.citations ?? []);
const count = (kind, st) => cits.filter((c) => c.kind === kind && c.status === st).length;
const nQ = cits.filter((c) => c.kind === "quran").length;
const nH = cits.filter((c) => c.kind === "hadith").length;
const referrals = runsAll.filter((r) => r.judgement?.needs_human_review).length;
const withCit = runsAll.filter((r) => (r.judgement?.citations ?? []).length).length;
const latest = Object.values(Object.fromEntries(results.runs.map((r) => [r.assistant, r])));

// ميزانيات الكلمات الظاهرة (الأقسام المطوية مغلقة). النتائج: 530 مؤقتاً، أي أعلى من هدف 500؛ ما بقي ظاهراً هناك كله
// تنبيهات أو أدلة محمية (سطر الدرجات ومقاماتها، وجملة OFF-03، والمراجعة الشرعية، والاتفاق، وتنبيه المقارنة) وجدول المقارنة.
// النتائج 560 = 530 + 30 كلمة لعنواني الرسمين وتعليقهما وتسميات صفوفهما (قيم الرسوم نفسها بيانات مستثناة، انظر open أدناه).
const BUDGET = { "index.html": 220, "results.html": 560, "cases.html": 600, "case.html?id=OFF-02": 400, "replay.html": 160, "check.html": 110 };

test("الأدلة المحمية والميزانيات في المتصفح", { skip: !pw && !process.env.CI ? "Playwright غير متوفر محلياً" : false }, async (t) => {
  assert.ok(pw, "Playwright مطلوب في CI");
  // الأرقام المحمية كما في البيانات اليوم (لا claim جديد: تُطابق ما ينشره الموقع منذ PR2)
  assert.deepEqual([results.runs.length, runsAll.length, cits.length, nQ, count("quran", "supported"), count("quran", "needs_review"),
    count("quran", "wrong_or_missing"), nH, count("hadith", "needs_review"), referrals], [4, 48, 46, 31, 20, 8, 3, 15, 15, 7]);

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
      const page = await (await browser.newContext({ viewport: { width, height: 900 } })).newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      const clean = (s) => s.replace(/[⁦-⁩]/g, "").replace(/\s+/g, " ");
      const open = async (pg, ready) => {
        await page.goto(base + pg, { waitUntil: "networkidle" });
        if (ready) await page.waitForSelector(ready);
        // قيم الرسوم (أعمدة وأعداد ومفاتيح ألوان، data-budget="data") بيانات لا نص؛ تُستثنى من ميزانية الكلمات،
        // وصحتها مختبرة مقابل results.json في results-core.test.mjs. عناوين الرسوم وتعليقاتها تبقى محسوبة.
        const prose = await page.evaluate(() => {
          const m = document.querySelector("main").cloneNode(true);
          for (const d of m.querySelectorAll('[data-budget="data"]')) d.remove();
          document.body.append(m); m.hidden = false; const t = m.innerText; m.remove(); return t;
        });
        return { visible: clean(await page.locator("main").innerText()), all: clean(await page.locator("main").textContent()), prose: clean(prose) };
      };
      const words = (s) => s.split(" ").filter(Boolean).length;

      await t.test(`${width}: النتائج — الأرقام والتنبيهات المحمية ظاهرة، والتفاصيل مطوية في DOM`, async () => {
        const { visible, all } = await open("results.html", "#discovered");
        const must = [
          `${officialRunsHeadline(results.runs.length)} المستودع.`,
          `${runsAll.length} إجابة مُقيَّمة`,
          `${cits.length} استشهاداً استخرجها مِعيار من ${withCit} إجابة فيها استشهاد (من ${runsAll.length})`,
          `الآيات (${nQ}): ${count("quran", "supported")} مؤيَّد، و${count("quran", "needs_review")} يحتاج تحقق، و${count("quran", "wrong_or_missing")} خاطئ أو غير موجود`,
          `الأحاديث (${nH}): ${count("hadith", "supported")} مؤيَّد، و${count("hadith", "needs_review")} يحتاج تحقق`,
          "«يحتاج تحقق» لا يعني أن الحديث خاطئ",
          `${referrals} إجابات من ${runsAll.length} أُحيلت إلى مراجعة بشرية ولم تدخل في الدرجة الآلية`,
          "في سجلي OFF-03 صُنّف الفرق wrong_or_missing / altered_text؛ والفرق المرصود حرف واحد (س/ص). وأكّده التحقق البشري النصي دون حسم أهو خطأ أم وجه رسم أو قراءة.",
          "تحقق بشري نصي للآيات",
          "صاحب المشروع، غير مستقل، ليس مراجعة شرعية",
          AGREEMENT_NOTE,
          "لا لأحكام مِعيار",
          overallScoresNote(results.gate, results.runs),
          "القرار حساس لاختيار الجولة المرجعية",
          "المراجعة الشرعية: مراجعة واحدة لحالة واحدة من 12 (OFF-06)",
          "جولة مكتملة واحدة فقط",
          ...results.gate.reasons.map((r) => `${r} ${reasonDenominator(r, results.gate, results.runs)}`),
          ...latest.map((r) => `${r.overall_score} (N = ${r.n_cases}، المحتسب ${r.n_scored})`),
        ];
        for (const s of must) assert.ok(visible.includes(clean(s)), `غير ظاهر: ${s}`);
        // تسمية الإحالة في جدول المقارنة متسقة: «لم تدخل في الدرجة الآلية»، ولا «بلا حكم آلي» في واجهة النتائج
        assert.ok((await page.locator("#compare").innerText()).includes("أُحيلت إلى مراجعة بشرية ولم تدخل في الدرجة الآلية"));
        assert.ok(!all.includes("بلا حكم آلي"), "عبارة «بلا حكم آلي» في واجهة النتائج");
        // مطوية لكنها في DOM: القاعدة وشرطها غير المُقاس
        for (const s of [results.gate.rule, gateRuleNote(results.gate.rule)]) assert.ok(all.includes(clean(s)), `مفقود: ${s}`);
        assert.ok(!visible.includes(clean(results.gate.rule)), "القاعدة يجب أن تكون مطوية");
        // رسم المقارنة: قيمة كل عمود ومقامه كما في results.json (بلا درجة → «—» لا صفر)، ورسم الأحكام بالأعداد نفسها
        const shown = await page.locator("#level-chart .chart-col").evaluateAll((cs) => cs.map((c) => [c.querySelector(".chart-val").textContent, c.querySelector(".chart-n").textContent]));
        const expect = [["overall_score", "n_scored", "n_cases"], ...["A", "B", "C", "D"]].flatMap((m) => results.runs.map((r) => {
          const src = Array.isArray(m) ? { score: r.overall_score, n_scored: r.n_scored, n_cases: r.n_cases } : r.levels[m];
          return [src.score === null ? "—" : src.score.toFixed(1), `${src.n_scored ?? 0}/${src.n_cases}`];
        }));
        assert.deepEqual(shown, expect);
        const segs = await page.locator("#verdict-chart .verdict-bar span").allTextContents();
        assert.deepEqual(segs.map(Number), [count("quran", "supported"), count("quran", "needs_review"), count("quran", "wrong_or_missing"), count("hadith", "needs_review")]);
        // تنبيه المقارنة ظاهر مرة واحدة
        assert.equal(await page.locator(".caveat:visible").count(), 1);
        // التفاصيل تُفتح بلوحة المفاتيح
        await page.locator("#gate-details > summary").focus();
        await page.keyboard.press("Enter");
        assert.equal(await page.locator("#gate-details").evaluate((d) => d.open), true);
        assert.ok(await page.locator("#gate-unmeasured").isVisible());
      });

      await t.test(`${width}: الرئيسية والحالات والحالة والحالة/Status — المحمي ظاهر`, async () => {
        let p = await open("index.html");
        for (const s of ["ولا يجيب هو عن الأسئلة الدينية", "وضع ثانوي، ليس تقييماً لمساعد", "لا يولّد آية ولا حديثاً ولا حكماً",
          "إعادة عرض لتشغيل رسمي محفوظ", "N = 12"]) assert.ok(p.visible.includes(s), s);
        p = await open("cases.html");
        const approved = meta.cases.filter((c) => c.review?.status === "approved").length;
        for (const s of ["لا حكم ولا نتيجة هنا", `المراجعة البشرية: ${approved} من ${meta.cases.length} حالة`, "مراجعة لتعريف الحالات وسلوكها المتوقع (تحقق مصادر)، لا لأحكام مِعيار"]) {
          assert.ok(p.visible.includes(s), s);
        }
        assert.equal(await page.locator("#cases tbody tr").count(), meta.cases.length);
        p = await open("case.html?id=OFF-02", ".answer-card");
        for (const s of ["إجابة المساعد المُختبَر — ليست من مِعيار", "عرض إجابة المساعد كاملة"]) assert.ok(p.visible.includes(s), s);
        const rec = records[official.findIndex((c) => c.id === "OFF-02")];
        // الإجابات المطوية هي إجابات السجل نفسها حرفياً
        const shown = await page.locator(".answer-card .answer").allTextContents();
        assert.ok(shown.length >= 1);
        for (const txt of shown) assert.ok(rec.runs.some((r) => r.answer === txt), "إجابة لا تطابق السجل حرفياً");
        p = await open("status.html");
        for (const s of ["وضع العرض:", "نتائج محفوظة", "وتحقق المصادر ليس مراجعة شرعية متخصصة"]) assert.ok(p.visible.includes(s), s);
      });

      await t.test(`${width}: ميزانية الكلمات الظاهرة (الأقسام المطوية مغلقة)`, async () => {
        for (const [pg, max] of Object.entries(BUDGET)) {
          const ready = pg.startsWith("results") ? "#discovered" : pg.startsWith("case.html") ? ".answer-card" : pg.startsWith("replay") ? ".replay-step" : null;
          const { prose } = await open(pg, ready);
          assert.ok(words(prose) <= max, `${pg}: ${words(prose)} كلمة ظاهرة > ${max}`);
        }
      });
      assert.deepEqual(errors, []);
    }
  } finally {
    await browser.close();
    server.close();
  }
});
