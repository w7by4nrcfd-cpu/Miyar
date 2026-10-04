// صفحة «تحقق من نص» (وضع ثانوي): الاستخراج والمطابقة داخل المتصفح بمنطق check-core.js، بلا أي خادم ولا نموذج لغوي.
import { QuranIndex, REASONS, STATUS_LABELS, checkText, suraByName } from "./check-core.js";

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const c of children) if (c !== null && c !== undefined) node.append(c); // نص فقط: لا innerHTML
  return node;
}
const ltr = (t) => el("span", { class: "ltr", lang: "en" }, t);
const STATUS_BADGE = { supported: "b-ok", needs_review: "b-rev", wrong_or_missing: "b-bad" };
const badge = (status) => el("span", { class: `badge ${STATUS_BADGE[status]}` }, STATUS_LABELS[status]);
const notice = (cls, title, text) => el("div", { class: `notice ${cls}`, role: "status" }, el("strong", {}, title), text ? el("span", {}, text) : null);

let loaded = null; // {index, names, hadith}
async function loadData() {
  if (loaded) return loaded;
  const [q, h] = await Promise.all(["assets/check/quran.json", "assets/check/hadith.json"].map(async (u) => {
    const res = await fetch(u);
    if (!res.ok) throw new Error(`${u}: ${res.status}`);
    return res.json();
  }));
  const index = new QuranIndex(q);
  loaded = { index, names: suraByName(index), hadith: h };
  return loaded;
}

const verseCard = (title, v, cls = "") => el("figure", { class: `ref-card ${cls}`.trim() },
  el("figcaption", {}, title, " — ", `سورة ${v.sura_name} `, ltr(v.ref)),
  el("blockquote", { class: "quran", lang: "ar" }, v.text));

function quranCard(r) {
  const card = el("article", { class: "check-card" },
    el("p", { class: "check-head" }, badge(r.status), " ", el("span", { class: "kind" }, "آية"),
      r.ref_text ? el("span", { class: "muted" }, " · الموضع المذكور: ", r.ref_text) : el("span", { class: "muted" }, " · لم يُذكر موضع")),
    el("blockquote", { class: "prompt", lang: "ar", dir: "auto" }, r.quote),
    el("p", {}, REASONS[r.reason] || r.reason, r.similarity !== null && r.status !== "supported" ? ` (التشابه الحرفي ${r.similarity})` : ""));
  if (r.status === "supported") {
    for (const v of r.found_at) card.append(verseCard("مؤيَّد بموضعه من البيانات", v));
  } else {
    if (r.cited_verse) card.append(verseCard("نص الموضع المذكور في البيانات", r.cited_verse, "ref-neutral"));
    for (const v of r.found_at) card.append(verseCard("النص موجود في البيانات هنا", v, "ref-neutral"));
    if (r.suggestions.length) {
      const list = el("div", { class: "suggestions" }, el("p", { class: "muted small" }, "أقرب الآيات في البيانات (للمقارنة فقط، لا حكم بأنها المقصودة):"));
      for (const s of r.suggestions) list.append(verseCard(`تشابه ${s.score}`, s, "ref-neutral"));
      card.append(list);
    }
  }
  return card;
}

function hadithCard(r) {
  const card = el("article", { class: "check-card" },
    el("p", { class: "check-head" }, badge(r.status), " ", el("span", { class: "kind" }, "حديث"),
      el("span", { class: "muted" }, r.cited ? ` · التخريج المذكور: ${r.cited}` : " · لم يُذكر تخريج")),
    el("blockquote", { class: "prompt", lang: "ar", dir: "auto" }, r.quote),
    el("p", {}, REASONS[r.reason] || r.reason));
  const e = r.entry;
  if (e) {
    const fig = el("figure", { class: "ref-card ref-neutral" }, el("figcaption", {}, "المدخل المطابق في الملف اليدوي ", ltr(r.entry_id)));
    if (e.kind === "found") {
      fig.append(el("blockquote", { lang: "ar" }, e.text), el("dl", { class: "kv" },
        el("dt", {}, "المصدر"), el("dd", {}, e.source),
        el("dt", {}, "الحكم"), el("dd", {}, `«${e.grade}» — ${e.grade_by}`)));
    } else if (e.kind === "not_found") {
      fig.append(el("p", {}, `لم يُعثر على «${e.query}» في البحث اليدوي.`));
    }
    if (e.link) fig.append(el("p", { class: "small" }, el("a", { href: e.link, class: "ltr", lang: "en", rel: "noopener" }, e.link)));
    card.append(fig);
  }
  return card;
}

function summary(results) {
  const n = (s) => results.filter((r) => r.status === s).length;
  return el("p", { class: "check-summary" },
    `استُخرج ${results.length}: `, badge("supported"), ` ${n("supported")} · `, badge("wrong_or_missing"), ` ${n("wrong_or_missing")} · `,
    badge("needs_review"), ` ${n("needs_review")}`);
}

async function run(text, out, button) {
  button.disabled = true;
  out.replaceChildren(notice("empty", "جارٍ التحميل والمطابقة…"));
  let data;
  try {
    data = await loadData();
  } catch {
    out.replaceChildren(notice("error", "تعذّر تحميل البيانات", "لا يصدر أي حكم دون البيانات. أعد المحاولة."));
    button.disabled = false;
    return;
  }
  const results = checkText(text, data.index, data.hadith, data.names);
  if (!results.length) {
    out.replaceChildren(notice("empty", "لم يُستخرج أي نص للفحص",
      "لا آية بين ﴿ ﴾ أو { } أو بموضع بين قوسين، ولا حديث بعلامة نسبة أو تخريج. لا يعني هذا أن النص سليم أو خاطئ."));
  } else {
    out.replaceChildren(el("h2", {}, "النتيجة"), summary(results),
      ...results.map((r) => (r.kind === "quran" ? quranCard(r) : hadithCard(r))),
      el("p", { class: "muted small" }, "كل نص شرعي معروض هنا منقول من البيانات؛ والحكم آلي مساعد للمراجعة لا بديل عنها."));
  }
  button.disabled = false;
}

const form = document.getElementById("check-form");
const textarea = document.getElementById("check-text");
const out = document.getElementById("check-results");
const button = document.getElementById("check-run");
form.addEventListener("submit", (ev) => {
  ev.preventDefault();
  if (!textarea.value.trim()) {
    out.replaceChildren(notice("empty", "الصق نصاً أولاً"));
    return;
  }
  run(textarea.value, out, button);
});
document.getElementById("check-clear").addEventListener("click", () => { textarea.value = ""; out.replaceChildren(); textarea.focus(); });
fetch("assets/check/hadith.json").then((r) => (r.ok ? r.json() : null)).then((h) => {
  if (h) document.getElementById("hadith-count").textContent = `المدخلات المكتملة (${h.entries.length}) فقط`;
}).catch(() => {});
