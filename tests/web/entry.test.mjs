// زر «جرّب مِعيار بنفسك» وترتيب القائمة في متصفح حقيقي على 360 و1440، فاتح وداكن. لم يُستدعَ أي نموذج.
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

test("الزر البارز في أعلى الرئيسية والقائمة", { skip: !pw && !process.env.CI ? "Playwright غير متوفر محلياً" : false }, async (t) => {
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
    for (const [width, scheme] of [[360, "light"], [360, "dark"], [1440, "light"], [1440, "dark"]]) {
      const ctx = await browser.newContext({ viewport: { width, height: 800 }, colorScheme: scheme });
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await t.test(`${width} ${scheme}: الزر ظاهر من أول شاشة، كبير، وبتباين كافٍ، والقائمة تبدأ بـ«تحقق من نص»`, async () => {
        await page.goto(base + "index.html", { waitUntil: "networkidle" });
        const btn = page.locator("a.btn-try");
        assert.equal(await btn.innerText(), "جرّب مِعيار بنفسك");
        const box = await btn.boundingBox();
        assert.ok(box.y + box.height <= 800, `الزر تحت الشاشة الأولى (y=${box.y})`);
        assert.ok(box.height >= 48 && box.width >= 150, `حجم الزر ${box.width}x${box.height}`);
        const ratio = await btn.evaluate((el) => {
          const lum = (c) => { const [r, g, b] = c.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
          const st = getComputedStyle(el), a = lum(st.color), b = lum(st.backgroundColor);
          return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        });
        assert.ok(ratio >= 4.5, `تباين الزر ${ratio.toFixed(2)}`);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth) <= 0, true, "تمرير أفقي");
        const first = await page.locator("nav.main a").first().innerText();
        assert.equal(first, "تحقق من نص");
        assert.match(await page.locator(".try-note").innerText(), /وضع ثانوي[\s\S]*ليس تقييماً لمساعد/);
      });
      await t.test(`${width} ${scheme}: الضغط يفتح الصفحة وفيها وسم «وضع ثانوي» وحدودها`, async () => {
        await page.goto(base + "index.html", { waitUntil: "networkidle" });
        await page.click("a.btn-try");
        await page.waitForURL("**/check.html");
        assert.match(await page.locator("h1").innerText(), /تحقق من نص\s*وضع ثانوي/);
        assert.match(await page.locator("#check-limits").innerText(), /ليست تقييماً لمساعد/);
        assert.equal(await page.locator('nav.main a[aria-current="page"]').innerText(), "تحقق من نص");
      });
      assert.deepEqual(errors, []);
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }
});
