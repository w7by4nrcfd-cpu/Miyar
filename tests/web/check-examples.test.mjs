// أزرار الأمثلة في «تحقق من نص»: تملأ مربع النص بنص من بيانات المشروع وتتحقق منه، في متصفح حقيقي على 360 و1440. لم يُستدعَ أي نموذج.
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

test("أزرار الأمثلة فوق مربع النص", { skip: !pw && !process.env.CI ? "Playwright غير متوفر محلياً" : false }, async (t) => {
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
      await t.test(`${width}: ثلاثة أمثلة قبل مربع النص تعطي «مؤيَّد» و«لم تُطابَق» و«يحتاج تحقق»`, async () => {
        await page.goto(base + "check.html", { waitUntil: "networkidle" });
        const buttons = page.locator(".btn-example");
        assert.equal(await buttons.count(), 3);
        const ta = await page.locator("#check-text").boundingBox();
        for (let i = 0; i < 3; i++) {
          const bb = await buttons.nth(i).boundingBox();
          assert.ok(bb.height >= 44, `هدف نقر ${bb.height}px`);
          assert.ok(bb.y < ta.y, "زر المثال ليس فوق مربع النص");
        }
        const expected = ["مؤيَّد", "لم تُطابَق", "يحتاج تحقق"];
        for (let i = 0; i < 3; i++) {
          await buttons.nth(i).click();
          await page.waitForFunction((want) => (document.getElementById("check-results")?.innerText || "").includes(want), expected[i], { timeout: 15000 });
          const text = await page.locator("#check-results").innerText();
          assert.ok(text.includes(expected[i]), `${expected[i]} غائب بعد المثال ${i + 1}`);
          assert.equal(await page.locator("#check-text").inputValue(), await buttons.nth(i).getAttribute("data-text"));
        }
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth) <= 0, "تمرير أفقي");
      });
      assert.deepEqual(errors, []);
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
});
