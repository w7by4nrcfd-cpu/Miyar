// اختبار التخطيط في متصفح حقيقي (Chromium عبر Playwright): لكل صفحة على عروض 360 و768 و1440px بالوضعين الفاتح والداكن:
// لا تمرير أفقي، وتباين كل نص مرئي ≥ 4.5:1، وأول Tab إلى «تخطَّ إلى المحتوى»، وروابط التنقل كلها قابلة للوصول بلوحة المفاتيح،
// ولا أخطاء JavaScript، ولا مفاتيح في الصفحات. وبحث صفحة الحالات يصفّي الصفوف.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, readdir } from "node:fs/promises";
import { join, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "web");
const PAGES = ["index.html", "levels.html", "sources.html", "cases.html", "status.html", "transparency.html", "results.html"];
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml" };

async function loadPlaywright() {
  for (const spec of ["playwright", "/opt/node22/lib/node_modules/playwright/index.mjs"]) {
    try { return await import(spec); } catch { /* التالي */ }
  }
  return null;
}

const pw = await loadPlaywright();
const required = Boolean(process.env.CI);

test("تخطيط الصفحات في المتصفح", { skip: !pw && !required ? "Playwright غير متوفر محلياً" : false }, async (t) => {
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
    for (const [width, scheme] of [360, 768, 1440].flatMap((w) => [[w, "dark"], [w, "light"]])) {
      const ctx = await browser.newContext({ viewport: { width, height: 800 }, colorScheme: scheme, reducedMotion: "reduce" });
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
      for (const p of PAGES) {
        await t.test(`${width} ${scheme} ${p}`, async () => {
          const res = await page.goto(base + p, { waitUntil: "networkidle" });
          assert.equal(res.status(), 200);
          const info = await page.evaluate(() => {
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
            for (const el of document.querySelectorAll("body *")) {
              if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
              if (el.closest(".sr, .skip, noscript, [hidden], svg")) continue; // نصوص SVG تُلوَّن بـ fill: أزواجها مختبرة من متغيرات CSS
              const st = getComputedStyle(el);
              if (st.display === "none" || st.visibility === "hidden") continue;
              const a = lum(st.color), b = lum(bgOf(el));
              const cr = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
              if (cr < 4.5) low.push(`${el.tagName}:${el.textContent.trim().slice(0, 25)}=${cr.toFixed(2)}`);
            }
            return { scroll: document.documentElement.scrollWidth, width: innerWidth, dir: document.dir, low, html: document.documentElement.outerHTML };
          });
          assert.equal(info.dir, "rtl");
          if (p === "index.html") {
            // نصوص رسم مسار العمل داخل صناديقها
            const spill = await page.evaluate(() => {
              const svg = document.querySelector("figure.flow > svg");
              const texts = [...svg.querySelectorAll("text")];
              return [...svg.querySelectorAll("rect.node")].flatMap((r) => {
                const rb = r.getBBox();
                return texts.filter((t) => { const tb = t.getBBox(); return tb.y >= rb.y && tb.y < rb.y + rb.height && (tb.x < rb.x || tb.x + tb.width > rb.x + rb.width); })
                  .map((t) => t.textContent);
              });
            });
            assert.deepEqual(spill, [], "نص يخرج من صندوقه في رسم مسار العمل");
          }
          assert.ok(info.scroll <= info.width, `تمرير أفقي: ${info.scroll} > ${info.width}`);
          assert.deepEqual(info.low, [], "نص بتباين أقل من 4.5:1");
          assert.ok(!/AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}/.test(info.html), "نمط مفتاح في الصفحة");
          await page.keyboard.press("Tab");
          assert.ok(await page.evaluate(() => document.activeElement.classList.contains("skip")), "أول Tab ليس رابط التخطي");
          const reached = new Set();
          for (let i = 0; i < 12; i++) {
            await page.keyboard.press("Tab");
            const h = await page.evaluate(() => document.activeElement.getAttribute("href"));
            if (h) reached.add(h);
          }
          for (const q of PAGES) assert.ok(reached.has(q), `رابط ${q} لا يُبلغ بلوحة المفاتيح`);
        });
      }
      assert.deepEqual(errors, [], "أخطاء JavaScript");
      await ctx.close();
    }

    await t.test("بحث وتصفية صفحة الحالات", async () => {
      const page = await browser.newPage({ viewport: { width: 360, height: 780 } });
      await page.goto(base + "cases.html");
      const total = await page.locator("#cases tbody tr").count();
      assert.ok(total > 0);
      await page.selectOption("#lv", "D");
      const shownD = await page.locator("#cases tbody tr:not([hidden])").count();
      assert.ok(shownD > 0 && shownD < total);
      assert.equal(await page.locator('#cases tbody tr:not([hidden])[data-level="D"]').count(), shownD);
      assert.match(await page.textContent("#count"), new RegExp(`يُعرض ${shownD} من ${total}`));
      await page.selectOption("#lv", "");
      await page.fill("#q", "OFF-05");
      assert.equal(await page.locator("#cases tbody tr:not([hidden])").count(), 1);
      await page.close();
    });
  } finally {
    await browser.close();
    server.close();
  }
});

test("لا مفاتيح في أي ملف داخل web/", async () => {
  const walk = async (d) => (await Promise.all((await readdir(d, { withFileTypes: true }))
    .map((e) => (e.isDirectory() ? walk(join(d, e.name)) : [join(d, e.name)])))).flat();
  for (const f of await walk(WEB)) {
    const s = await readFile(f, "utf-8");
    assert.ok(!/AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|BEGIN (RSA |EC )?PRIVATE KEY/.test(s), f);
  }
});
