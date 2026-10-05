// صفحة إعادة العرض: تشغيل رسمي محفوظ خطوة بخطوة. لا نموذج ولا خادم: قراءة ملفات data/ المنشورة فقط.
// كل محتوى منقول من السجل يُوسم data-saved (يُعرض كما هو)؛ وما عداه نصوص الواجهة.
import { buildSteps, EXAMPLES, gateSentence, officialCases, parseState, REPLAY_LIMITS, runShort, SAVED_BADGE, stateQuery,
  STEP_TITLES, UI_COPY } from "./replay-core.js";

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const c of children) if (c !== null && c !== undefined && c !== false) node.append(c); // نص فقط: لا innerHTML
  return node;
}
const saved = (tag, attrs, ...children) => el(tag, { ...attrs, "data-saved": "" }, ...children);
const ltr = (t) => el("span", { class: "ltr", lang: "en" }, t);
const badge = (cls, t) => el("span", { class: `badge ${cls}` }, t);
const STATUS_BADGE = { supported: "b-ok", needs_review: "b-rev", wrong_or_missing: "b-bad" };
const VERDICT_BADGE = { ok: "b-ok", error: "b-bad", review: "b-rev", none: "b-todo" };
const KIND = { quran: "آية", hadith: "حديث" };

async function getJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

function details(title, ...children) {
  return el("details", { class: "tech" }, el("summary", {}, title), el("div", { class: "tech-body" }, ...children));
}
function kv(...pairs) {
  const dl = el("dl", { class: "kv" });
  for (const [k, v] of pairs) if (v !== null && v !== undefined && v !== "") dl.append(el("dt", {}, k), el("dd", {}, v));
  return dl;
}

// ---------- محتوى كل خطوة ----------
function stepQuestion(s, { meta }) {
  const nodes = [el("p", {}, badge("b-level", s.level), " ", saved("span", {}, s.levelBehavior))];
  if (s.trap) nodes.push(el("p", { class: "notice demo trap", role: "note" }, saved("span", {}, meta.trap_warning)));
  nodes.push(s.masked ? saved("p", { class: "masked" }, meta.masked_text) : saved("blockquote", { class: "prompt", dir: "auto" }, s.prompt));
  if (s.injectedContext) nodes.push(details("النص المرفق بالسؤال (بيانات لا تعليمات)", saved("blockquote", { class: "prompt", dir: "auto" }, s.injectedContext)));
  if (s.references.length) {
    nodes.push(details("النص الصحيح من البيانات", ...s.references.map((r) => el("figure", { class: "ref-card" },
      el("figcaption", {}, saved("span", {}, r.ref)),
      r.text ? saved("blockquote", { lang: "ar", dir: "auto" }, r.text) : null,
      r.source ? el("p", { class: "muted small" }, "المصدر: ", saved("span", {}, r.source)) : null,
      r.grade ? el("p", { class: "small" }, "الحكم: ", saved("span", {}, `«${r.grade}» — ${r.grade_by}`)) : null))));
  }
  nodes.push(details(UI_COPY.sourceDetails, el("p", {}, "السلوك المتوقع: "), saved("p", { dir: "auto" }, s.expected)));
  return nodes;
}

function stepAnswer(s) {
  return [
    el("p", { class: "frame-label" }, UI_COPY.answerFrame),
    s.error ? el("p", { class: "notice error" }, UI_COPY.answerError) : saved("div", { class: "answer", dir: "auto" }, s.answer),
    details(UI_COPY.sourceDetails, kv(["المساعد", ltr(s.assistant)], ["النموذج", s.answerModel ? ltr(s.answerModel) : null],
      ["الجولة", ltr(s.runId)], ["وقت التشغيل", ltr(s.executedAt)])),
  ];
}

function stepCitations(s) {
  if (!s.citations.length) return [el("p", { class: "muted" }, UI_COPY.noCitations)];
  const list = el("ul", { class: "replay-cits" });
  for (const c of s.citations) {
    list.append(el("li", {}, el("strong", {}, KIND[c.kind] ?? c.kind), " ",
      saved("span", { dir: "auto" }, c.quote), c.cited ? el("span", { class: "muted small" }, " — الموضع المذكور: ", saved("span", { dir: "auto" }, c.cited)) : null));
  }
  return [list];
}

function stepMatching(s) {
  if (!s.citations.length) return [el("p", { class: "muted" }, UI_COPY.noCitations)];
  const nodes = s.citations.map((c) => el("article", { class: "replay-match" },
    el("p", {}, badge(STATUS_BADGE[c.status] ?? "b-todo", c.statusLabel), " ", el("strong", {}, KIND[c.kind] ?? c.kind)),
    saved("blockquote", { class: "prompt", dir: "auto" }, c.quote),
    c.matchedText
      ? el("figure", { class: "ref-card" }, el("figcaption", {}, "من البيانات"), saved("blockquote", { lang: "ar", dir: "auto" }, c.matchedText))
      : el("p", { class: "muted small" }, UI_COPY.noMatch),
    details(UI_COPY.sourceDetails, kv(["سبب الحكم", ltr(c.reason)], ["الموضع في البيانات", c.matchedRef ? ltr(c.matchedRef) : null]))));
  return nodes;
}

function stepVerdict(s) {
  return [
    el("p", { class: "verdict-line" }, badge(VERDICT_BADGE[s.verdict.kind], s.verdict.text)),
    el("p", { class: "muted small" }, UI_COPY.savedJudgement),
    s.rationale ? el("figure", { class: "replay-rationale" }, el("figcaption", { class: "small muted" }, "سبب الحكم كما كتبه الحَكَم الآلي"),
      saved("blockquote", { dir: "auto" }, s.rationale)) : null,
    details(UI_COPY.sourceDetails, kv(["ثقة الحَكَم", s.confidence === null ? null : s.confidence.toFixed(2)],
      ["نموذج الحَكَم", s.judgeModel ? ltr(s.judgeModel) : null], ["الأصناف", s.categories.length ? ltr(s.categories.join(", ")) : null],
      ["سبب الإحالة", s.reviewReason ? ltr(s.reviewReason) : null])),
  ];
}

function stepChecks(s) {
  if (s.referred) return [el("p", {}, badge("b-rev", "إحالة"), " ", UI_COPY.referralChecks)];
  const list = el("ul", { class: "checks" });
  for (const k of s.checks) {
    list.append(el("li", {}, badge(k.value === true ? "b-ok" : k.value === false ? "b-bad" : "b-todo", k.text), " ",
      saved("span", { dir: "auto" }, k.description)));
  }
  return [list, details(UI_COPY.sourceDetails, el("p", {}, ...s.checks.flatMap((k, i) => [i ? "، " : "", ltr(k.name)])))];
}

function stepResult(s, { caseId }) {
  const nodes = [el("p", { class: "verdict-line" }, badge(VERDICT_BADGE[s.verdict.kind], s.verdict.text))];
  if (s.summary) nodes.push(el("p", {}, "فحوص السلوك: ", s.summary));
  if (s.runScore) {
    const sc = s.runScore.score === null ? "بلا درجة" : String(s.runScore.score);
    nodes.push(el("p", {}, `${UI_COPY.runScore}: ${sc} (محتسبة من ${s.runScore.nScored} من ${s.runScore.nCases} حالة)`));
  }
  if (s.gateRole) {
    nodes.push(el("p", { id: "replay-gate" }, gateSentence(s)));
    if (s.gateReasons.length) {
      const ul = el("ul", { class: "gate-reasons" });
      for (const r of s.gateReasons) ul.append(saved("li", {}, r));
      nodes.push(ul);
    }
  } else {
    nodes.push(el("p", { class: "muted small" }, UI_COPY.gateNone));
  }
  nodes.push(el("p", { class: "more" }, el("a", { href: `case.html?id=${encodeURIComponent(caseId)}` }, "صفحة الحالة كاملة"), " · ",
    el("a", { href: "results.html" }, "النتائج")));
  return nodes;
}

const RENDER = [stepQuestion, stepAnswer, stepCitations, stepMatching, stepVerdict, stepChecks, stepResult];

// ---------- الصفحة ----------
// الشريط يلتصق تحت شريط التنقل العلوي؛ ارتفاع ذلك الشريط يتغير بين الجوال والحاسوب
function syncBannerOffset() {
  const bar = document.querySelector(".topbar");
  if (bar) document.documentElement.style.setProperty("--replay-top", `${Math.ceil(bar.getBoundingClientRect().height)}px`);
}

// عند تغيير الخطوة: التركيز على عنوانها، ووضعه تحت الشريط الملتصق مباشرة (لا تحته) مهما كان طول الصفحة
function showStepHeading(h2) {
  if (!h2) return;
  h2.focus({ preventScroll: true });
  const banner = document.getElementById("replay-banner");
  const top = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--replay-top")) || 0;
  const clear = top + (banner ? banner.getBoundingClientRect().height : 0) + 16;
  const card = h2.closest(".replay-step") ?? h2;  // بطاقة الخطوة كاملة (شارتها وعنوانها) تحت الشريط
  scrollTo({ top: Math.max(0, scrollY + card.getBoundingClientRect().top - clear) });
}

async function main() {
  const root = document.getElementById("replay");
  if (!root) return;
  syncBannerOffset();
  addEventListener("resize", syncBannerOffset);
  let meta, results;
  try {
    [meta, results] = await Promise.all([getJson("data/testcases.json"), getJson("data/results.json")]);
  } catch {
    root.replaceChildren(el("div", { class: "notice error", role: "alert" }, el("strong", {}, UI_COPY.loadError), " ", UI_COPY.loadErrorNext));
    return;
  }
  const cases = officialCases(meta);
  const state = { ...parseState(location.search), all: false };
  const records = new Map();

  async function record(id) {
    if (!records.has(id)) records.set(id, await getJson(`data/cases/${encodeURIComponent(id)}.json`).catch(() => null));
    return records.get(id);
  }

  async function render(focus = false) {
    history.replaceState(null, "", stateQuery(state));
    const caseMeta = cases.find((c) => c.id === state.caseId);
    const rec = caseMeta ? await record(state.caseId) : null;
    const run = rec?.runs?.find((r) => r.run_id === state.runId) ?? null;

    // الأمثلة الثلاثة
    const ex = el("div", { class: "examples", role: "group", "aria-label": UI_COPY.examples },
      el("span", { class: "examples-label" }, UI_COPY.examples),
      ...EXAMPLES.map((e) => {
        const on = e.case === state.caseId && e.run === state.runId;
        const b = el("button", { type: "button", class: `btn ghost btn-example${on ? " on" : ""}`, "aria-pressed": on ? "true" : "false" },
          `${e.label} (${e.case})`);
        b.addEventListener("click", () => { Object.assign(state, { caseId: e.case, runId: e.run, step: 1 }); render(true); });
        return b;
      }));

    // اختيار الحالة والجولة (كل السجلات الـ48)
    const caseSel = el("select", { id: "replay-case" }, ...cases.map((c) => {
      const o = el("option", { value: c.id }, `${c.id} — المستوى ${c.level}`);
      if (c.id === state.caseId) o.selected = true;
      return o;
    }));
    const runs = rec?.runs ?? [];
    const runSel = el("select", { id: "replay-run" }, ...runs.map((r) => {
      const o = el("option", { value: r.run_id }, runShort(r.run_id));
      if (r.run_id === state.runId) o.selected = true;
      return o;
    }));
    caseSel.addEventListener("change", async () => {
      state.caseId = caseSel.value; state.step = 1;
      const r = await record(state.caseId);
      if (!r?.runs?.some((x) => x.run_id === state.runId)) state.runId = r?.runs?.[0]?.run_id ?? state.runId;
      render();
    });
    runSel.addEventListener("change", () => { state.runId = runSel.value; state.step = 1; render(); });
    const pickers = el("form", { class: "filters replay-pickers", "aria-label": "اختيار الحالة والجولة" },
      el("div", {}, el("label", { for: "replay-case" }, UI_COPY.caseLabel), caseSel),
      el("div", {}, el("label", { for: "replay-run" }, UI_COPY.runLabel), runSel));
    pickers.addEventListener("submit", (e) => e.preventDefault());

    const limits = el("details", { class: "tech", id: "replay-limits" }, el("summary", {}, UI_COPY.limits),
      el("ul", { class: "limits-list" }, ...REPLAY_LIMITS.map((t) => el("li", {}, t))));

    if (!caseMeta || !run) {
      root.replaceChildren(ex, pickers, el("div", { class: "notice empty", role: "status" }, el("strong", {}, UI_COPY.notFound)), limits);
      return;
    }

    const steps = buildSteps(caseMeta, run, results, meta);
    const section = (i) => el("section", { class: "case-card replay-step", "aria-labelledby": `step-h-${i + 1}` },
      el("p", { class: "replay-step-meta" }, badge("b-todo", SAVED_BADGE), " ",
        el("span", { class: "muted small" }, `${state.caseId} · `, ltr(runShort(run.run_id)))),
      el("h2", { id: `step-h-${i + 1}`, tabindex: "-1" }, `الخطوة ${i + 1} من ${STEP_TITLES.length}: ${STEP_TITLES[i]}`),
      ...RENDER[i](steps[i], { meta, caseId: state.caseId }));

    let body;
    if (state.all) {
      body = el("div", { class: "replay-all" }, ...STEP_TITLES.map((_, i) => section(i)));
    } else {
      const i = state.step - 1;
      const prev = el("button", { type: "button", class: "btn ghost", id: "replay-prev" }, UI_COPY.prev);
      const next = el("button", { type: "button", class: "btn", id: "replay-next" }, UI_COPY.next);
      if (i === 0) prev.disabled = true;
      if (i === STEP_TITLES.length - 1) next.disabled = true;
      prev.addEventListener("click", () => { state.step -= 1; render(true); });
      next.addEventListener("click", () => { state.step += 1; render(true); });
      body = el("div", {}, section(i),
        el("nav", { class: "replay-nav", "aria-label": "التنقل بين الخطوات" }, prev,
          el("span", { class: "replay-progress", "aria-live": "polite" }, `${state.step} من ${STEP_TITLES.length}`), next));
    }
    const toggle = el("button", { type: "button", class: "btn ghost", id: "replay-toggle" }, state.all ? UI_COPY.showOne : UI_COPY.showAll);
    toggle.addEventListener("click", () => { state.all = !state.all; render(true); });

    root.replaceChildren(ex, pickers, body, el("p", {}, toggle), limits);
    if (focus) showStepHeading(root.querySelector(".replay-step h2"));
  }
  render();
}

main();
