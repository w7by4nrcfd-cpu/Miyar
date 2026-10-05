// أول شاشة في الرئيسية (سطران وزران) وقائمة التنقل ذات العناصر الأربعة وصفحات «عن المشروع» في متصفح حقيقي على 360 و1440، فاتح وداكن. لم يُستدعَ أي نموذج.
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

test("أول شاشة في الرئيسية: سطران وزران، والقائمة أربعة عناصر", { skip: !pw && !process.env.CI ? "Playwright غير متوفر محلياً" : false }, async (t) => {
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
  const contrast = (el) => {
    const lum = (c) => { const [r, g, b] = c.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const st = getComputedStyle(el), a = lum(st.color);
    let bgEl = el, bg = st.backgroundColor;
    while ((!bg || bg === "transparent" || /rgba\(.*,\s*0\)$/.test(bg)) && bgEl.parentElement) { bgEl = bgEl.parentElement; bg = getComputedStyle(bgEl).backgroundColor; }
    const b = lum(bg);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  };
  try {
    for (const [width, scheme] of [[360, "light"], [360, "dark"], [1440, "light"], [1440, "dark"]]) {
      const ctx = await browser.newContext({ viewport: { width, height: 800 }, colorScheme: scheme });
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await t.test(`${width} ${scheme}: سطران وزران ظاهران من أول شاشة، كبيران، وبتباين كافٍ`, async () => {
        await page.goto(base + "index.html", { waitUntil: "networkidle" });
        assert.equal(await page.locator(".hero-line").count(), 2);
        const buttons = page.locator(".hero a.btn");
        assert.equal(await buttons.count(), 2, "في أول شاشة زران فقط");
        assert.deepEqual(await buttons.allInnerTexts(), ["جرّب التحقق", "شاهد النتائج"]);
        for (let i = 0; i < 2; i++) {
          const btn = buttons.nth(i);
          const box = await btn.boundingBox();
          assert.ok(box.y + box.height <= 800, `الزر ${i} تحت الشاشة الأولى (y=${box.y})`);
          assert.ok(box.height >= 48 && box.width >= 120, `حجم الزر ${i}: ${box.width}x${box.height}`);
          assert.ok(await btn.evaluate(contrast) >= 4.5, `تباين الزر ${i}`);
        }
        for (const line of await page.locator(".hero-line").all()) assert.ok(await line.evaluate(contrast) >= 4.5, "تباين السطر");
        assert.match(await page.locator(".hero-line").nth(1).innerText(), /وضع ثانوي[\s\S]*ليس تقييماً لمساعد/);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth) <= 0, true, "تمرير أفقي");
        const items = await page.locator("nav.main a").allInnerTexts();
        assert.deepEqual(items, ["جرّب", "النتائج", "الحالات", "عن المشروع"]);
        for (const a of await page.locator("nav.main a").all()) assert.ok((await a.boundingBox()).height >= 40, "هدف نقر أصغر من 40px");
      });
      await t.test(`${width} ${scheme}: الزران يفتحان التحقق والنتائج`, async () => {
        await page.goto(base + "index.html", { waitUntil: "networkidle" });
        await page.click(".hero a.btn >> text=جرّب التحقق");
        await page.waitForURL("**/check.html");
        assert.match(await page.locator("h1").innerText(), /تحقق من نص\s*وضع ثانوي/);
        assert.match(await page.locator("#check-limits").innerText(), /ليست تقييماً لمساعد/);
        assert.equal(await page.locator('nav.main a[aria-current="page"]').innerText(), "جرّب");
        await page.goto(base + "index.html", { waitUntil: "networkidle" });
        await page.click(".hero a.btn >> text=شاهد النتائج");
        await page.waitForURL("**/results.html");
        assert.equal(await page.locator('nav.main a[aria-current="page"]').innerText(), "النتائج");
      });
      await t.test(`${width} ${scheme}: «عن المشروع» تصل المستويات والمصادر والشفافية والحالة، والقائمة تبقى مفعّلة عليها`, async () => {
        await page.goto(base + "project.html", { waitUntil: "networkidle" });
        assert.equal(await page.locator('nav.main a[aria-current="page"]').innerText(), "عن المشروع");
        for (const [href, h1] of [["levels.html", /مستويات المحتوى/], ["sources.html", /المصادر/], ["transparency.html", /الشفافية/], ["status.html", /الحالة/]]) {
          await page.goto(base + "project.html", { waitUntil: "networkidle" });
          await page.click(`.about-list a[href="${href}"]`);
          await page.waitForURL(`**/${href}`);
          assert.match(await page.locator("h1").innerText(), h1);
          assert.equal(await page.locator('nav.main a[aria-current="page"]').innerText(), "عن المشروع");
          assert.equal(await page.locator('.subnav a[aria-current="location"]').count(), 1);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth) <= 0, true, `تمرير أفقي في ${href}`);
        }
      });
      await t.test(`${width} ${scheme}: التفاصيل التقنية في الحالة مطوية وتُفتح بنقرة وفيها الملفات`, async () => {
        await page.goto(base + "status.html", { waitUntil: "networkidle" });
        const details = page.locator("details.tech").first();
        assert.equal(await details.evaluate((d) => d.open), false);
        assert.equal(await page.locator(".checklist:not(.tech-list) .evidence a").count(), 0, "اسم ملف ظاهر خارج الطبقة المطوية");
        await details.locator("summary").click();
        assert.equal(await details.evaluate((d) => d.open), true);
        assert.ok((await details.innerText()).includes("miyar/"), "أسماء الملفات غائبة من التفاصيل التقنية");
      });
      assert.deepEqual(errors, []);
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
});
