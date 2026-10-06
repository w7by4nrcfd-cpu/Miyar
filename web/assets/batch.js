// «اختبر مساعدك»: فحص إسناد إجابات مساعد على الحالات الرسمية دفعة واحدة، داخل المتصفح بمنطق check-core.js نفسه.
// لا خادم ولا نموذج لغوي: لا يحكم على السلوك ولا يصدر درجة ولا قرار بوابة؛ يعدّ أحكام الآيات والأحاديث فقط.
import { QuranIndex, REASONS, STATUS_LABELS, checkText, suraByName, SUPPORTED, NEEDS_REVIEW, WRONG_OR_MISSING } from "./check-core.js";

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const c of children) if (c !== null && c !== undefined) node.append(c); // نص فقط: لا innerHTML
  return node;
}
const ltr = (t) => el("span", { class: "ltr", lang: "en" }, t);
const STATUS_BADGE = { [SUPPORTED]: "b-ok", [NEEDS_REVIEW]: "b-rev", [WRONG_OR_MISSING]: "b-bad" };
const ORDER = [SUPPORTED, NEEDS_REVIEW, WRONG_OR_MISSING];
const badge = (status, n) => el("span", { class: `badge ${STATUS_BADGE[status]}` }, n === undefined ? STATUS_LABELS[status] : `${STATUS_LABELS[status]} ${n}`);

async function getJSON(u) {
  const res = await fetch(u);
  if (!res.ok) throw new Error(`${u}: ${res.status}`);
  return res.json();
}

// عدّ الأحكام: مجموع لكل حكم (منطق نقي، يختبره tests/web/batch.test.mjs)
export function tally(items) {
  const t = { [SUPPORTED]: 0, [NEEDS_REVIEW]: 0, [WRONG_OR_MISSING]: 0 };
  for (const i of items) t[i.status] += 1;
  return t;
}

let data = null;
async function load() {
  if (data) return data;
  const [q, h, meta] = await Promise.all([getJSON("assets/check/quran.json"), getJSON("assets/check/hadith.json"), getJSON("data/testcases.json")]);
  const cases = meta.cases.filter((c) => c.testset === "official_v0");
  const index = new QuranIndex(q);
  data = { index, names: suraByName(index), hadith: h, cases };
  return data;
}

function build(root) {
  const form = el("form", { id: "batch-form", class: "check-form", autocomplete: "off" });
  const runSel = el("select", { id: "batch-run", "aria-label": "جولة رسمية محفوظة" });
  const fill = el("button", { type: "button", class: "btn ghost", id: "batch-fill" }, "املأ بإجابات جولة محفوظة");
  const list = el("ol", { class: "batch-list" });
  const run = el("button", { type: "submit", class: "btn", id: "batch-run-btn" }, "افحص كل الإجابات");
  const out = el("div", { id: "batch-results", "aria-live": "polite" });
  form.append(el("div", { class: "check-actions" }, runSel, fill), list, el("div", { class: "check-actions" }, run), out);
  root.append(form);

  load().then(({ cases }) => {
    for (const c of cases) {
      const id = `batch-${c.id}`;
      list.append(el("li", { class: "batch-item" },
        el("label", { for: id }, ltr(c.id), " · ", el("span", { class: "muted" }, `المستوى ${c.level}`), el("br"), c.prompt),
        el("textarea", { id, rows: "4", dir: "auto", maxlength: "20000", "data-case": c.id, placeholder: "الصق إجابة مساعدك عن هذا السؤال" })));
    }
  }).catch(() => out.replaceChildren(el("div", { class: "notice error", role: "alert" }, el("strong", {}, "تعذّر تحميل البيانات"), el("span", {}, " أعد تحميل الصفحة."))));

  // الجولات الرسمية المحفوظة: الإجابات كما سُجّلت في web/data/cases/ (إجابات المساعد المُختبَر، لا من مِعيار)
  getJSON("data/results.json").then((r) => {
    for (const x of r.runs) runSel.append(el("option", { value: x.run_id }, x.run_id.replace(/^official-\d{4}-\d{2}-\d{2}-/, "")));
  }).catch(() => {});

  fill.addEventListener("click", async () => {
    const { cases } = await load();
    await Promise.all(cases.map(async (c) => {
      const rec = await getJSON(`data/cases/${c.id}.json`);
      const r = rec.runs.find((x) => x.run_id === runSel.value);
      const ta = document.getElementById(`batch-${c.id}`);
      if (ta) ta.value = r?.answer ?? "";
    }));
    out.replaceChildren(el("p", { class: "notice demo", role: "note" },
      "مُلئت الحقول بإجابات المساعد المُختبَر في ", ltr(runSel.value.replace(/^official-\d{4}-\d{2}-\d{2}-/, "")), " كما سُجّلت (ليست من مِعيار). اضغط «افحص كل الإجابات»."));
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const { index, names, hadith, cases } = await load();
    const rows = [];
    for (const c of cases) {
      const text = document.getElementById(`batch-${c.id}`)?.value ?? "";
      const items = text.trim() ? checkText(text, index, hadith, names) : [];
      rows.push({ case: c.id, level: c.level, answered: Boolean(text.trim()), items });
    }
    render(out, rows);
    out.scrollIntoView({ block: "start" });
  });
}

function render(out, rows) {
  const answered = rows.filter((r) => r.answered);
  const all = answered.flatMap((r) => r.items);
  const t = tally(all);
  const withCit = answered.filter((r) => r.items.length).length;
  const summary = el("div", { class: "card batch-summary" },
    el("h3", {}, "الخلاصة"),
    el("p", {}, `${answered.length} إجابة من ${rows.length} · ${all.length} استشهاداً في ${withCit} إجابة`),
    el("p", { class: "batch-badges" }, ...ORDER.map((s) => badge(s, t[s]))),
    el("p", { class: "muted small" }, "فحص الإسناد فقط: لا حكم على السلوك ولا درجة ولا قرار بوابة. والاستخراج هنا بقواعد ثابتة، وفي التشغيل الرسمي بنموذج، فقد تختلف الأعداد عن السجل الرسمي."));
  const table = el("table", { class: "stack" },
    el("thead", {}, el("tr", {}, ...["الحالة", "المستوى", ...ORDER.map((s) => STATUS_LABELS[s])].map((h) => el("th", { scope: "col" }, h)))));
  const body = el("tbody");
  for (const r of rows) {
    const rt = tally(r.items);
    body.append(el("tr", {}, el("th", { scope: "row" }, el("a", { href: `case.html?id=${r.case}` }, ltr(r.case))),
      el("td", { "data-label": "المستوى" }, r.level),
      ...ORDER.map((s) => el("td", { "data-label": STATUS_LABELS[s] }, r.answered ? String(rt[s]) : "—"))));
  }
  table.append(body);
  const details = el("details", { class: "tech" }, el("summary", {}, "كل استشهاد وسببه"));
  const ul = el("ul", { class: "limits-list" });
  for (const r of rows) for (const i of r.items) {
    ul.append(el("li", {}, ltr(r.case), " · ", i.kind === "quran" ? "آية" : "حديث", " ", badge(i.status), " «", i.quote, "» — ", REASONS[i.reason] ?? i.reason));
  }
  details.append(ul.childElementCount ? ul : el("p", { class: "muted" }, "لا استشهادات مستخرجة."));
  const dl = el("button", { type: "button", class: "btn ghost", id: "batch-download" }, "نزّل التقرير (JSON)");
  dl.addEventListener("click", () => {
    const report = { tool: "مِعيار — فحص إسناد إجابات مساعد (داخل المتصفح)", scope: "citations_only", generated_at: new Date().toISOString(), totals: t,
      cases: rows.map((r) => ({ case: r.case, level: r.level, answered: r.answered, totals: tally(r.items),
        citations: r.items.map((i) => ({ kind: i.kind, quote: i.quote, status: i.status, reason: i.reason })) })) };
    const a = el("a", { href: URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" })), download: "miyar-citation-report.json" });
    document.body.append(a); a.click(); a.remove();
  });
  out.replaceChildren(summary, el("div", { class: "table-wrap", role: "region", "aria-label": "نتيجة كل حالة", tabindex: "0" }, table), details, dl);
}

const root = typeof document !== "undefined" ? document.getElementById("batch-root") : null;
const box = root ? document.getElementById("batch") : null;
if (root && box) {
  let done = false;
  box.addEventListener("toggle", () => { if (box.open && !done) { done = true; build(root); } });
}
