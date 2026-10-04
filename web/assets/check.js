// صفحة «تحقق من نص» (وضع ثانوي): الاستخراج والمطابقة داخل المتصفح بمنطق check-core.js، بلا أي خادم ولا نموذج لغوي.
import { QuranIndex, REASONS, STATUS_LABELS, checkText, hintsFor, normalize, suraByName } from "./check-core.js";

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

// إبراز الكلمة المختلفة: يُمكن فقط حين تقابل كل كلمة خام كلمةً موحّدة واحدة (وإلا يبقى النص بلا إبراز، ويكفي سطر الفرق)
function rawWords(raw) {
  const ws = raw.split(/\s+/u).filter(Boolean);
  const toks = ws.map((w) => normalize(w));
  return toks.every((t) => t && !t.includes(" ")) && toks.join(" ") === normalize(raw) ? ws : null;
}
function marked(raw, indices) {
  const ws = rawWords(raw);
  if (!ws || !indices.length) return [raw];
  const set = new Set(indices);
  const out = [];
  ws.forEach((w, i) => {
    if (i) out.push(" ");
    out.push(set.has(i) ? el("mark", { class: "diff" }, w) : w);
  });
  return out;
}
const range = (a, b) => Array.from({ length: Math.max(0, b - a) }, (_, k) => a + k);
const mk = (t) => el("mark", { class: "diff" }, t);

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

const verseCard = (title, v, cls = "", marks = []) => el("figure", { class: `ref-card ${cls}`.trim() },
  el("figcaption", {}, title, " — ", `سورة ${v.sura_name} `, ltr(v.ref)),
  el("blockquote", { class: "quran", lang: "ar" }, ...marked(v.text, marks)));

function diffLine(diff) {
  const parts = [];
  diff.chunks.forEach((c, k) => {
    if (k) parts.push("؛ ");
    const q = c.q_words.join(" "), w = c.w_words.join(" ");
    if (q && w) parts.push("كتبتَ «", mk(q), "» والنص في البيانات «", mk(w), "»");
    else if (w) parts.push("نقص في نصك: «", mk(w), "» موجودة في البيانات");
    else parts.push("زيادة في نصك: «", mk(q), "» غير موجودة في البيانات");
  });
  return el("p", { class: "diff-line" }, "الكلمة المختلفة (بعد توحيد التشكيل والهمزات): ", ...parts, ".");
}

function quranCard(r) {
  const d = r.diff && r.diff.chunks.length ? r.diff : null;
  const qMarks = d ? d.chunks.flatMap((c) => range(c.q[0], c.q[1])) : [];
  // إبراز الكلمة في نص الآية المعروض فقط إن كان الرسم المقارَن هو الإملائي (وهو ما تعرضه البطاقة)
  const vMarks = d && d.script === "simple" ? d.chunks.flatMap((c) => range(d.offset + c.w[0], d.offset + c.w[1])) : [];
  const card = el("article", { class: "check-card" },
    el("p", { class: "check-head" }, badge(r.status), " ", el("span", { class: "kind" }, "آية"),
      r.ref_text ? el("span", { class: "muted" }, " · الموضع المذكور: ", r.ref_text) : el("span", { class: "muted" }, " · لم يُذكر موضع")),
    el("blockquote", { class: "prompt", lang: "ar", dir: "auto" }, ...marked(r.quote, qMarks)),
    el("p", {}, REASONS[r.reason] || r.reason, r.similarity !== null && r.status !== "supported" ? ` (التشابه الحرفي ${r.similarity})` : ""));
  if (d) card.append(diffLine(d));
  if (r.status === "supported") {
    for (const v of r.found_at) card.append(verseCard("مؤيَّد بموضعه من البيانات", v));
  } else {
    if (r.cited_verse) card.append(verseCard("نص الموضع المذكور في البيانات", r.cited_verse, "ref-neutral", d && d.ref === r.cited_verse.ref ? vMarks : []));
    for (const v of r.found_at) card.append(verseCard("النص موجود في البيانات هنا", v, "ref-neutral"));
    if (r.suggestions.length) {
      const list = el("div", { class: "suggestions" }, el("p", { class: "muted small" }, "أقرب الآيات في البيانات (للمقارنة فقط، لا حكم بأنها المقصودة):"));
      for (const s of r.suggestions) list.append(verseCard(`تشابه ${s.score}`, s, "ref-neutral", d && !r.cited_verse && d.ref === s.ref ? vMarks : []));
      card.append(list);
    }
  }
  return card;
}

function nearFigure(n, caption) {
  const e = n.entry;
  const fig = el("figure", { class: "ref-card ref-neutral near-card" },
    el("figcaption", {}, caption, " ", ltr(n.entry_id), " — للمقارنة فقط"),
    el("blockquote", { lang: "ar" }, ...marked(e.text, [n.entry_index])),
    el("p", { class: "diff-line" }, "كتبتَ «", mk(n.q_word), "» وفي المدخل «", mk(n.entry_word), "» (بعد توحيد التشكيل والهمزات)."),
    el("dl", { class: "kv" },
      el("dt", {}, "المصدر"), el("dd", {}, e.source),
      el("dt", {}, "الحكم"), el("dd", {}, `«${e.grade}» — ${e.grade_by}`)));
  if (e.link) fig.append(el("p", { class: "small" }, el("a", { href: e.link, class: "ltr", lang: "en", rel: "noopener" }, e.link)));
  fig.append(el("p", { class: "not-support" }, "هذا ليس تأييداً: النص الذي كتبته لا يطابق المدخل حرفياً، ولا يُنسب إليه."));
  return fig;
}

function hadithCard(r) {
  const near = r.near || null;
  const card = el("article", { class: "check-card" },
    el("p", { class: "check-head" }, badge(r.status), " ",
      near ? el("span", { class: "badge b-todo" }, "لم يُطابَق حرفياً") : null, near ? " " : null,
      el("span", { class: "kind" }, "حديث"),
      el("span", { class: "muted" }, r.cited ? ` · التخريج المذكور: ${r.cited}` : " · لم يُذكر تخريج")),
    el("blockquote", { class: "prompt", lang: "ar", dir: "auto" }, ...(near ? marked(r.quote, [near.q_index]) : [r.quote])),
    el("p", {}, REASONS[r.reason] || r.reason));
  if (near) {
    card.append(nearFigure(near, "أقرب مدخل في الملف اليدوي"));
    return card;
  }
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

function hintCard(h) {
  const card = el("article", { class: "check-card hint-card" },
    el("p", { class: "check-head" }, el("span", { class: "badge b-todo" }, "لم يُفحص"), " ",
      el("span", { class: "muted" }, h.match === "literal" ? "يطابق حرفياً نص مدخل في الملف اليدوي" : "يقارب نص مدخل في الملف اليدوي")),
    el("blockquote", { class: "prompt", lang: "ar", dir: "auto" }, ...(h.near ? marked(h.quote, [h.near.q_index]) : [h.quote])),
    el("p", {}, "نص بين علامتي تنصيص لم تُقرأ له علامة نسبة (مثل «قال رسول الله ﷺ» قبله أو «رواه» بعده)، فلم يُفحص كحديث ولا حكم عليه هنا. "
      + "إن كان حديثاً فاكتب علامة النسبة أو التخريج ثم أعد التحقق."));
  if (h.near) card.append(nearFigure(h.near, "أقرب مدخل في الملف اليدوي"));
  else {
    const e = h.entry;
    const fig = el("figure", { class: "ref-card ref-neutral" }, el("figcaption", {}, "المدخل المطابق في الملف اليدوي ", ltr(h.entry_id)),
      el("blockquote", { lang: "ar" }, e.text),
      el("dl", { class: "kv" }, el("dt", {}, "المصدر"), el("dd", {}, e.source), el("dt", {}, "الحكم"), el("dd", {}, `«${e.grade}» — ${e.grade_by}`)));
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
  const hints = hintsFor(text, data.index, data.hadith, data.names);
  if (!results.length && !hints.length) {
    out.replaceChildren(notice("empty", "لم يُستخرج أي نص للفحص",
      "لا آية بين ﴿ ﴾ أو { } أو بموضع بين قوسين، ولا حديث بعلامة نسبة أو تخريج. لا يعني هذا أن النص سليم أو خاطئ."));
  } else {
    const nodes = results.length
      ? [el("h2", {}, "النتيجة"), summary(results), ...results.map((r) => (r.kind === "quran" ? quranCard(r) : hadithCard(r)))]
      : [notice("empty", "لم يُستخرج أي استشهاد للفحص", "لا آية ولا حديث بالصورة المقروءة؛ ولا يعني هذا أن النص سليم أو خاطئ.")];
    if (hints.length) nodes.push(el("h2", {}, "نصوص لم تُفحص"), ...hints.map(hintCard));
    nodes.push(el("p", { class: "muted small" }, "كل نص شرعي معروض هنا منقول من البيانات؛ والحكم آلي مساعد للمراجعة لا بديل عنها."));
    out.replaceChildren(...nodes);
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
