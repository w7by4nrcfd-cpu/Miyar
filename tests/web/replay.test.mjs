// إعادة عرض تشغيل رسمي محفوظ في متصفح حقيقي: 360 و1440، فاتح وداكن، ولوحة المفاتيح. البيانات المنشورة الحقيقية (قراءة فقط)؛ لم يُستدعَ أي نموذج.
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
const pw = await loadPlaywright();
const BANNER = "إعادة عرض لتشغيل رسمي محفوظ — ليس تشغيلاً حياً";
const B3 = "official-2026-10-04-baseline-3";
const ALLOWED = /^\/(replay\.html|assets\/[\w.-]+\.(js|css)|data\/testcases\.json|data\/results\.json|data\/cases\/OFF-\d{2}\.json)$/;

test("إعادة العرض في المتصفح", { skip: !pw && !process.env.CI ? "Playwright غير متوفر محلياً" : false }, async (t) => {
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
    for (const [width, scheme] of [[360, "light"], [360, "dark"], [1440, "light"], [1440, "dark"]]) {
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
        const low = [], small = [];
        for (const el of document.querySelectorAll("main *")) {
          const st = getComputedStyle(el);
          if (st.display === "none" || st.visibility === "hidden" || el.closest("details:not([open]) > :not(summary)")) continue;
          if ([...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) && !el.closest("button[disabled]")) {
            const a = lum(st.color), b = lum(bgOf(el));
            const cr = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
            if (cr < 4.5) low.push(`${el.tagName}:${el.textContent.trim().slice(0, 20)}=${cr.toFixed(2)}`);
          }
          if (el.matches("#replay button, #replay select, #replay summary")) {
            const r = el.getBoundingClientRect();
            if (r.width && r.height < 44) small.push(`${el.tagName}:${el.textContent.trim().slice(0, 20)}`);
          }
        }
        return { overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, low, small };
      });
      // الشريط داخل الشاشة فعلاً (لا isVisible وحده): تحت شريط التنقل وفوق أسفل الشاشة، ولا يغطي عنوان الخطوة
      const bannerBox = () => page.evaluate(() => {
        const b = document.getElementById("replay-banner").getBoundingClientRect();
        const bar = document.querySelector(".topbar").getBoundingClientRect();
        const h2 = document.querySelector(".replay-step h2")?.getBoundingClientRect();
        return { top: b.top, bottom: b.bottom, height: b.height, barBottom: bar.bottom, vh: innerHeight, h2Top: h2?.top ?? null };
      });
      const assertBannerInView = async (where, heading = true) => {
        const r = await bannerBox();
        assert.ok(r.height > 0 && r.top >= r.barBottom - 1 && r.bottom <= r.vh, `${where}: الشريط خارج الشاشة أو تحت شريط التنقل ${JSON.stringify(r)}`);
        if (heading && r.h2Top !== null) assert.ok(r.h2Top >= r.bottom - 1, `${where}: الشريط يغطي عنوان الخطوة ${JSON.stringify(r)}`);
      };
      // نص الواجهة وحده: يُحذف كل محتوى منقول من السجل (data-saved) قبل الفحص
      const uiText = () => page.evaluate(() => {
        const c = document.getElementById("replay").cloneNode(true);
        c.querySelectorAll("[data-saved]").forEach((n) => n.remove());
        return c.textContent;
      });

      await t.test(`${width} ${scheme}: الافتراضي OFF-11، والشريط ظاهر بنصه، وخطوة واحدة مع المؤشر`, async () => {
        requests.length = 0;
        await page.goto(base + "replay.html", { waitUntil: "networkidle" });
        await page.waitForSelector(".replay-step");
        assert.equal((await page.locator("#replay-banner").innerText()).trim(), BANNER);
        assert.ok(await page.locator("#replay-banner").isVisible());
        await assertBannerInView("الخطوة 1");
        assert.equal(await page.locator(".replay-step").count(), 1);
        assert.match(await page.locator(".replay-step h2").innerText(), /^الخطوة 1 من 7: السؤال$/);
        assert.equal(await page.locator(".replay-progress").innerText(), "1 من 7");
        assert.match(page.url(), new RegExp(`case=OFF-11&run=${B3}&step=1`));
        assert.equal(await page.locator(".btn-example").count(), 3);
        assert.equal(await page.locator("#replay-case option").count(), 12);
        assert.equal(await page.locator("#replay-run option").count(), 4);
        for (const p of requests) assert.match(p, ALLOWED, `طلب غير متوقع ${p}`);
        const l = await layout();
        assert.ok(l.overflow <= 0, `تمرير أفقي ${l.overflow}px`);
        assert.deepEqual(l.low, [], "تباين أقل من 4.5:1");
        assert.deepEqual(l.small, [], "هدف نقر أصغر من 44px");
      });

      await t.test(`${width} ${scheme}: لوحة المفاتيح: «التالي» و«السابق» ينقلان الخطوة والتركيز والرابط`, async () => {
        await page.focus("#replay-next");
        await page.keyboard.press("Enter");
        await page.waitForFunction(() => document.querySelector(".replay-progress")?.textContent === "2 من 7");
        assert.match(page.url(), /step=2/);
        assert.equal(await page.evaluate(() => document.activeElement?.id), "step-h-2");
        await assertBannerInView("بعد الانتقال إلى الخطوة 2");
        for (let n = 3; n <= 6; n++) {  // كل خطوة لاحقة: الشريط داخل الشاشة ولا يغطي عنوانها
          await page.focus("#replay-next");
          await page.keyboard.press("Enter");
          await page.waitForFunction((k) => document.querySelector(".replay-progress")?.textContent === `${k} من 7`, n);
          await assertBannerInView(`بعد الانتقال إلى الخطوة ${n}`);
        }
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await assertBannerInView("بعد التمرير إلى أسفل الصفحة", false);  // العنوان مرّ فوق الشاشة بالتمرير؛ الشريط وحده يُفحص
        for (let i = 0; i < 5; i++) {
          await page.focus("#replay-prev");
          await page.keyboard.press("Enter");
        }
        await page.waitForFunction(() => document.querySelector(".replay-progress")?.textContent === "1 من 7");
        assert.equal(await page.locator("#replay-prev").isDisabled(), true);
      });

      await t.test(`${width} ${scheme}: OFF-02 الخطوة 4: حكم مِعيار المسجل والنص من البيانات`, async () => {
        await page.goto(base + `replay.html?case=OFF-02&run=${B3}&step=4`, { waitUntil: "networkidle" });
        await page.waitForSelector(".replay-match");
        const step = await page.locator(".replay-step").innerText();
        assert.match(step, /خاطئ أو غير موجود/);
        assert.match(step, /من البيانات/);
        assert.doesNotMatch(step, /مثبت بشري|خطأ مثبت/);
        const l = await layout();
        assert.ok(l.overflow <= 0, `تمرير أفقي ${l.overflow}px`);
        assert.deepEqual(l.low, [], "تباين أقل من 4.5:1");
      });

      await t.test(`${width} ${scheme}: الخطوة 7: قرار البوابة يُنسب إلى المرشحة لا إلى المرجع`, async () => {
        await page.goto(base + `replay.html?case=OFF-11&run=${B3}&step=7`, { waitUntil: "networkidle" });
        await page.waitForSelector("#replay-gate");
        assert.equal(await page.locator("#replay-gate").innerText(), "هذه الجولة هي المرجع في قرار البوابة. قرار البوابة على المرشحة rag-2: حجب.");
        await page.goto(base + "replay.html?case=OFF-11&run=official-2026-10-04-rag-2&step=7", { waitUntil: "networkidle" });
        await page.waitForSelector("#replay-gate");
        assert.equal(await page.locator("#replay-gate").innerText(), "هذه الجولة هي المرشحة في قرار البوابة: حجب مقارنةً بالمرجع baseline-3.");
        await assertBannerInView("الخطوة 7");
      });

      await t.test(`${width} ${scheme}: OFF-06 الخطوة 6: إحالة بلا فحوص محسومة`, async () => {
        await page.goto(base + `replay.html?case=OFF-06&run=${B3}&step=6`, { waitUntil: "networkidle" });
        await page.waitForSelector(".replay-step");
        assert.match(await page.locator(".replay-step").innerText(), /أُحيلت هذه الإجابة إلى مراجعة بشرية ولم تدخل في الدرجة الآلية/);
        assert.equal(await page.locator(".replay-step ul.checks").count(), 0);
      });

      await t.test(`${width} ${scheme}: اختيار الحالة والجولة، و«كل الخطوات»، وحدود إعادة العرض مطوية`, async () => {
        await page.selectOption("#replay-case", "OFF-05");
        await page.waitForFunction(() => /case=OFF-05/.test(location.search));
        assert.equal(await page.locator("#replay-run option").count(), 4);
        await page.selectOption("#replay-run", "official-2026-10-04-rag-2");
        await page.waitForFunction(() => /run=official-2026-10-04-rag-2/.test(location.search));
        await page.click("#replay-toggle");
        assert.equal(await page.locator(".replay-step").count(), 7);
        assert.equal(await page.locator("#replay-limits").evaluate((d) => d.open), false);
        const ui = await uiText();
        assert.doesNotMatch(ui, /الآن|مباشر|\blive\b|حياً|تشغيل حي|جارٍ التحليل|جارٍ التقييم/i, "نص واجهة يوحي بتشغيل حي");
        const l = await layout();
        assert.ok(l.overflow <= 0, `تمرير أفقي ${l.overflow}px`);
        assert.deepEqual(l.low, [], "تباين أقل من 4.5:1");
        assert.deepEqual(l.small, [], "هدف نقر أصغر من 44px");
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
