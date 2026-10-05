// صفحة تفصيل الحالة: بيانات الحالة من data/testcases.json، وسجلها الرسمي من data/cases/<id>.json إن وُجد.
import { caseIdFrom, checksSummary, checkText, findCase, interpretRecord, latestRuns, verdict } from "./case-core.js";

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const c of children) if (c !== null && c !== undefined) node.append(c); // نص فقط: لا innerHTML لبيانات خارجية
  return node;
}
const ltr = (t) => el("span", { class: "ltr", lang: "en" }, t);
const badge = (cls, t) => el("span", { class: `badge ${cls}` }, t);
const STATUS_BADGE = { supported: "b-ok", needs_review: "b-rev", wrong_or_missing: "b-bad" };

async function fetchText(url) {
  try {
    const res = await fetch(url, { cache: "no-store" });
    return { status: res.status, ok: res.ok, text: res.ok ? await res.text() : "" };
  } catch {
    return null;
  }
}

function notice(cls, title, text) {
  return el("div", { class: `notice ${cls}`, role: "status" }, el("strong", {}, title), text ? el("span", {}, text) : null);
}

function reviewBadge(review, specialistCount) {
  if (review.status === "approved" && review.role === "specialist") return badge("b-ok", "معتمدة شرعياً");
  if (review.status === "approved" && review.role === "source_check") return badge("b-rev", "تحقق مصادر (ليس مراجعة شرعية)");
  if (review.status === "rejected") return badge("b-bad", "مرفوضة");
  return badge("b-todo", specialistCount === 0 ? "لم يُتحقق منها بعد" : "لم تُراجَع بعد");
}

function referenceBlock(ref) {
  if (ref.kind === "quran") {
    return el("figure", { class: "ref-card" },
      el("figcaption", {}, "النص الصحيح من البيانات — ", ref.ref),
      el("blockquote", { class: "quran", lang: "ar" }, ref.text),
      el("p", { class: "muted small" }, "المصدر: ", ref.source));
  }
  if (ref.pending) {
    return el("figure", { class: "ref-card" }, el("figcaption", {}, "مدخل الملف اليدوي ", ltr(ref.ref)),
      el("p", {}, badge("b-todo", "ناقص"), " ", ref.note));
  }
  const body = el("figure", { class: "ref-card" }, el("figcaption", {}, "من الملف اليدوي للأحاديث ", ltr(ref.ref)));
  if (ref.entry_kind === "found") {
    body.append(el("blockquote", { lang: "ar" }, ref.text),
      el("dl", { class: "kv" },
        el("dt", {}, "المصدر"), el("dd", {}, ref.source),
        el("dt", {}, "الحكم"), el("dd", {}, `«${ref.grade}» — ${ref.grade_by}`)));
  } else if (ref.entry_kind === "not_found") {
    body.append(el("p", {}, `لم يُعثر على «${ref.query}» في ${ref.searched_in}.`));
  } else {
    body.append(el("p", {}, `أعلى رقم في ${ref.source}: ${ref.max_number}.`));
  }
  if (ref.link) body.append(el("p", { class: "small" }, el("a", { href: ref.link, class: "ltr", lang: "en", rel: "noopener" }, ref.link)));
  return body;
}

function caseHeader(c, meta) {
  const facts = el("dl", { class: "kv case-facts" },
    el("dt", {}, "المستوى"), el("dd", {}, badge("b-level", c.level), " ", c.level_behavior),
    el("dt", {}, "نوع الحالة"), el("dd", {}, c.type),
    el("dt", {}, "آلية المعالجة"), el("dd", {}, c.handling),
    el("dt", {}, "حرجة"), el("dd", {}, c.critical ? "نعم" : "لا"),
    el("dt", {}, "المراجعة"), el("dd", {}, reviewBadge(c.review, meta.specialist_reviews)));
  return el("section", { class: "case-card", "aria-labelledby": "case-h" },
    el("h2", { id: "case-h" }, el("span", { class: "mono" }, c.id)), facts);
}

function questionSection(c, meta) {
  const sec = el("section", { class: "case-card", "aria-labelledby": "q-h" }, el("h2", { id: "q-h" }, "السؤال"));
  if (c.trap) sec.append(el("p", { class: "notice demo trap", role: "note" }, el("strong", {}, "تنبيه: "), meta.trap_warning));
  sec.append(c.prompt_masked
    ? el("p", { class: "masked" }, meta.masked_text)
    : el("blockquote", { class: "prompt", dir: "auto" }, c.prompt));
  if (c.injected_context) {
    sec.append(el("details", {}, el("summary", {}, "النص المرفق بالسؤال (بيانات لا تعليمات)"),
      el("blockquote", { class: "prompt", dir: "auto" }, c.injected_context)));
  }
  if (c.references.length) sec.append(el("div", { class: "refs" }, ...c.references.map(referenceBlock)));
  return sec;
}

function expectedSection(c) {
  const list = el("ul", { class: "checks" });
  for (const k of c.checks) list.append(el("li", {}, el("code", {}, k.name), " — ", k.description));
  return el("section", { class: "case-card", "aria-labelledby": "e-h" }, el("h2", { id: "e-h" }, "السلوك المتوقع"),
    el("p", { dir: "auto" }, c.expected_behavior), el("h3", {}, "الفحوص"), list);
}

function citationsTable(cits, labels) {
  if (!cits.length) return el("p", { class: "muted" }, "لم يُستخرج من الإجابة أي آية أو حديث.");
  const body = el("tbody");
  for (const c of cits) {
    body.append(el("tr", {},
      el("td", { "data-label": "النوع" }, c.kind === "quran" ? "آية" : c.kind === "hadith" ? "حديث" : c.kind),
      el("td", { "data-label": "كما ورد في الإجابة", dir: "auto" }, c.quote, c.cited ? el("span", { class: "muted small" }, ` (${c.cited})`) : null),
      el("td", { "data-label": "الحكم" }, badge(STATUS_BADGE[c.status] ?? "b-todo", labels[c.status] ?? c.status),
        el("br"), el("code", { class: "small" }, c.reason)),
      el("td", { "data-label": "من البيانات", dir: "auto" }, c.matched_text ?? "—",
        c.matched_ref ? el("span", { class: "muted small" }, ` (${c.matched_ref})`) : null)));
  }
  return el("div", { class: "table-wrap", role: "region", "aria-label": "الاستشهادات المستخرجة", tabindex: "0" },
    el("table", { class: "stack cits" },
      el("thead", {}, el("tr", {}, ...["النوع", "كما ورد في الإجابة", "الحكم", "من البيانات"].map((h) => el("th", { scope: "col" }, h)))),
      body));
}

function runCard(run, c, meta) {
  const j = run.judgement;
  const v = verdict(j, meta.categories);
  const card = el("article", { class: "answer-card", "aria-label": `إجابة ${run.assistant}` },
    el("header", {}, el("h3", {}, ltr(run.assistant)),
      el("p", { class: "muted small" }, ltr(run.run_id), " · ", ltr(run.answer_model ?? "—"))),
    el("p", { class: "frame-label" }, "إجابة المساعد المُختبَر — ليست من مِعيار"));
  card.append(run.error
    ? el("p", { class: "notice error" }, "تعذّر جواب المساعد في هذا التشغيل.")
    : el("div", { class: "answer", dir: "auto" }, run.answer ?? ""));
  card.append(el("h4", {}, "الاستشهادات المستخرجة وحكم كل منها"), citationsTable(j?.citations ?? [], meta.citation_status_labels));
  const verdictCls = { ok: "b-ok", error: "b-bad", review: "b-rev", none: "b-todo" }[v.kind];
  card.append(el("h4", {}, "الحكم"), el("p", { class: "verdict-line" }, badge(verdictCls, v.text)));
  if (j && !j.needs_human_review) {
    const list = el("ul", { class: "checks" });
    for (const k of c.checks) {
      const val = j.checks[k.name];
      list.append(el("li", {}, badge(val === true ? "b-ok" : val === false ? "b-bad" : "b-todo", checkText(val)), " ", el("code", {}, k.name)));
    }
    const summary = checksSummary(j);
    card.append(list, summary ? el("p", { class: "muted small" }, summary) : null);
  }
  if (j) {
    card.append(el("dl", { class: "kv" },
      el("dt", {}, "ثقة الحَكَم"), el("dd", {}, j.confidence.toFixed(2)),
      el("dt", {}, "سبب الحكم"), el("dd", { dir: "auto" }, j.rationale || "—"),
      el("dt", {}, "نموذج الحَكَم"), el("dd", {}, ltr(j.judge_model || "—"))));
  }
  return card;
}

function recordSection(view, c, meta) {
  const sec = el("section", { class: "case-card", "aria-labelledby": "r-h" }, el("h2", { id: "r-h" }, "السجل الرسمي"));
  if (view.state === "none") {
    sec.append(notice("empty", "ليست ضمن الحالات الاثنتي عشرة المُشغَّلة رسمياً",
      "فلا إجابة ولا حكم يُعرض لها، ولا بيانات تجريبية."));
    return sec;
  }
  if (view.state === "invalid") {
    const list = el("ul");
    for (const e of view.errors.slice(0, 8)) list.append(el("li", {}, e));
    sec.append(el("div", { class: "notice error", role: "alert" }, el("strong", {}, "سجل الحالة غير صالح"),
      el("span", {}, "لن يُعرض أي حكم من ملف لا يطابق العقد. التفاصيل:"), list));
    return sec;
  }
  sec.append(el("p", { class: "muted" }, "آخر تشغيل رسمي لكل مساعد. الحكم الآلي مساعد للمراجعة لا بديل عنها."),
    el("div", { class: "answers" }, ...latestRuns(view.runs).map((r) => runCard(r, c, meta))));
  if (meta.specialist_reviews === 0) {
    sec.append(el("p", { class: "muted small" }, "لم تُجرَ مراجعة شرعية متخصصة."));
  }
  return sec;
}

async function main() {
  const root = document.getElementById("case");
  const id = caseIdFrom(location.search);
  const dataRes = await fetchText("data/testcases.json");
  let meta = null;
  try { meta = dataRes?.ok ? JSON.parse(dataRes.text) : null; } catch { meta = null; }
  if (!meta) {
    root.replaceChildren(notice("error", "تعذّر تحميل بيانات الحالات", ""));
    return;
  }
  const c = id ? findCase(meta, id) : null;
  if (!c) {
    root.replaceChildren(notice("empty", id ? `لا توجد حالة بالمعرّف ${id}` : "اختر حالة من قائمة الحالات",
      "افتح «حالات الاختبار» واضغط معرّف الحالة."));
    return;
  }
  document.title = `${c.id} — تفصيل الحالة — مِعيار`;
  const view = interpretRecord(await fetchText(`data/cases/${encodeURIComponent(c.id)}.json`), c.id);
  root.replaceChildren(caseHeader(c, meta), questionSection(c, meta), expectedSection(c), recordSection(view, c, meta));
}

main();
