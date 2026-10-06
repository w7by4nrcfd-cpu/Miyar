// صفحة النتائج: تقرأ data/results.json (ناتج scripts/publish_results.py من evaluation/official/) وتعرضه دون أي رقم مصطنع.
import {
  AGREEMENT_NOTE, comparisonCaveat, comparisonRows, gateRuleNote, interpretResults, latestByAssistant, LEVELS, officialRunsHeadline,
  overallScoresNote, reasonDenominator,
} from "./results-core.js";

const RESULTS_URL = "data/results.json";

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  for (const c of children) node.append(c); // نص فقط: لا innerHTML لبيانات خارجية
  return node;
}

const ltr = (text) => el("span", { class: "ltr", lang: "en" }, text);

function renderEmpty(root) {
  root.replaceChildren(
    el("div", { class: "notice empty", role: "status" },
      el("strong", {}, "لم يُشغَّل أي تقييم رسمي بعد"),
      el("span", {}, "لا نتائج رسمية بعد: ملف النتائج المحفوظ فارغ، ولا بيانات تجريبية فيه. التقييم الرسمي يبدأ 4 أكتوبر 2026، ولا يظهر هنا إلا ناتج تشغيل رسمي مسجّل في evaluation/official/ مع عدد الحالات (N)."))
  );
}

function renderInvalid(root, errors) {
  const list = el("ul");
  for (const e of errors.slice(0, 10)) list.append(el("li", {}, e));
  root.replaceChildren(
    el("div", { class: "notice error", role: "alert" },
      el("strong", {}, "بيانات النتائج غير صالحة"),
      el("span", {}, "لن تُعرض أي أرقام من ملف لا يطابق المخطط الموثّق. التفاصيل:"),
      list)
  );
}

function comparisonTable(latest) {
  const head = el("tr", {}, el("th", { scope: "col" }, "المقياس"));
  for (const r of latest) head.append(el("th", { scope: "col" }, ltr(r.assistant)));
  const body = el("tbody");
  for (const [label, values] of comparisonRows(latest)) {
    const tr = el("tr", {}, el("th", { scope: "row" }, label));
    values.forEach((v, i) => tr.append(el("td", { "data-label": latest[i].assistant }, v)));
    body.append(tr);
  }
  return el("div", { class: "table-wrap", role: "region", "aria-label": "جدول المقارنة", tabindex: "0" },
    el("table", { class: "stack", id: "compare" }, el("thead", {}, head), body));
}

function recordsList(runs) {
  const list = el("ul", { class: "records" });
  for (const r of runs) {
    list.append(el("li", {}, ltr(`${r.assistant} · ${r.run_id} · N = ${r.n_cases} · ${r.model} · ${r.executed_at}`),
      el("br"), "السجل: ", ltr(r.evaluation_record)));
  }
  return list;
}

// أسماء الملفات والسجلات في طبقة مطوية، لا في النص الظاهر
function techDetails(latest, runs) {
  return el("details", { class: "tech", id: "results-tech" }, el("summary", {}, "التفاصيل التقنية (السجلات والملفات)"),
    el("div", { class: "tech-body" },
      el("p", {}, "السجلات الرسمية في ", ltr("evaluation/official/"), "، والجولات الناقصة في ", ltr("evaluation/official_incomplete/"),
        "؛ وقرار البوابة محسوب بـ ", ltr("scoring.gate_decision"), "."),
      el("h3", {}, "السجلات المعروضة في المقارنة"), recordsList(latest),
      el("h3", {}, "كل التشغيلات الرسمية المنشورة"), recordsList(runs)));
}

const caveat = (runs, id) => el("p", { class: "notice demo caveat", role: "note", id }, comparisonCaveat(runs));

function gateSection(gate, latest, runs) {
  // الخلاصة أولاً: قرار البوابة في بطاقة واضحة بسببه وحساسيته
  const sec = el("section", { class: "card gate-card", "aria-labelledby": "gate-h" }, el("h2", { id: "gate-h" }, "الخلاصة: قرار البوابة"));
  if (!gate) {
    sec.append(el("p", {}, "لا قرار بوابة: يحتاج تشغيلاً رسمياً منشوراً لكل من baseline (المرجع) وrag (المرشحة)."));
    return sec;
  }
  sec.append(
    el("p", { class: "gate-verdict" },
      el("span", { class: `badge badge-lg ${gate.allow ? "b-ok" : "b-bad"}` }, gate.allow ? "نشر rag" : "حجب rag"),
      " المرشحة ", ltr(gate.candidate_run_id), " مقابل المرجع ", ltr(gate.reference_run_id), "."),
  );
  const reasons = el("ul", { class: "gate-reasons" });
  for (const r of gate.reasons) {
    const d = reasonDenominator(r, gate, runs);
    reasons.append(el("li", {}, r, d ? el("span", { class: "muted small" }, ` ${d}`) : null));
  }
  const scores = overallScoresNote(gate, runs);
  sec.append(el("h3", {}, "السبب"), reasons,
    ...(scores ? [el("p", { class: "muted small", id: "gate-overall" }, scores)] : []),
    el("p", { class: "small", id: "gate-sensitivity" },
      el("strong", {}, "القرار حساس لاختيار الجولة المرجعية"), "؛ ولا تُختار جولة مرجعية بحسب النتيجة."),
    // التفاصيل الثانوية مطوية (في DOM، وتُفتح بلوحة المفاتيح)
    el("details", { class: "tech", id: "gate-details" }, el("summary", {}, "قاعدة البوابة وحدودها"),
      el("div", { class: "tech-body" },
        el("p", { class: "small" }, "يُحسب القرار مقابل آخر جولة baseline منشورة، وجولات baseline تتفاوت درجاتها فيما بينها؛ فقد تتغير الأسباب وهوامشها بتغيير الجولة المرجعية."),
        el("p", { class: "small" }, el("strong", {}, "القاعدة: "), gate.rule),
        ...(gateRuleNote(gate.rule) ? [el("p", { class: "muted small", id: "gate-unmeasured" }, gateRuleNote(gate.rule))] : []),
        el("p", { class: "muted small" }, "القرار محسوب من السجلين الرسميين، لا من هذه الصفحة."),
        caveat(latest, "gate-caveat"))));
  return sec;
}

function stabilitySection(stability) {
  const sec = el("section", { "aria-labelledby": "stab-h" }, el("h2", { id: "stab-h" }, "الثبات عبر التشغيلات الرسمية"));
  const entries = Object.entries(stability);
  if (!entries.length) {
    sec.append(el("p", {}, "الثبات يحتاج تشغيلين رسميين أو أكثر لكل مساعد على مجموعة الحالات نفسها؛ لا يُعرض قبل ذلك."));
    return sec;
  }
  for (const [assistant, st] of entries) {
    const body = el("tbody");
    for (const [label, v] of [["الكلية", st.overall], ...LEVELS.map((lv) => [`المستوى ${lv}`, st.levels[lv]])]) {
      const cell = (x) => (x === null || x === undefined ? "—" : String(x));
      body.append(el("tr", {}, el("th", { scope: "row" }, label),
        el("td", { "data-label": "الأدنى" }, cell(v.min)), el("td", { "data-label": "الأعلى" }, cell(v.max)),
        el("td", { "data-label": "الفرق" }, cell(v.range)), el("td", { "data-label": "تشغيلات بدرجة" }, `${v.n_with_score} من ${v.n_runs}`)));
    }
    // سطر ظاهر من الملف نفسه (الكلية)، والجدول الكامل لكل مستوى في طبقة مطوية
    const o = st.overall;
    sec.append(el("p", { class: "stab-line", title: st.run_ids.join("، ") }, ltr(assistant),
      ` — الدرجة الكلية بين ${o.min} و${o.max} عبر ${o.n_runs} جولات (الفرق ${o.range}).`),
      el("details", { class: "tech" }, el("summary", {}, `ثبات ${assistant} لكل مستوى`),
        el("div", { class: "table-wrap", role: "region", "aria-label": `ثبات ${assistant}`, tabindex: "0" },
          el("table", { class: "stack" },
            el("thead", {}, el("tr", {}, ...["المقياس", "الأدنى", "الأعلى", "الفرق", "تشغيلات بدرجة"].map((h) => el("th", { scope: "col" }, h)))),
            body)),
        el("p", { class: "muted small" }, "تُعرض التشغيلات كلها؛ لا يُختار أفضلها.")));
  }
  return sec;
}

// مساعد له جولة رسمية مكتملة واحدة فقط: لا ثبات يُقاس له، وتُذكر الحدود صراحةً
function singleRunNotes(runs, stability) {
  const counts = {};
  for (const r of runs) counts[r.assistant] = (counts[r.assistant] || 0) + 1;
  const notes = [];
  for (const [assistant, n] of Object.entries(counts)) {
    if (n !== 1 || stability[assistant]) continue;
    const why = assistant === "rag"
      ? " (حد Groq اليومي المجاني؛ والجولات الناقصة محفوظة منفصلة)"
      : "";
    notes.push(el("p", { class: "notice demo single-run", role: "note" },
      el("strong", {}, `لـ ${assistant} جولة مكتملة واحدة فقط`), why,
      "، فلا يُقاس ثباته ولا يُستدل منها على استقراره."));
  }
  return notes;
}

function renderOk(root, view) {
  const latest = latestByAssistant(view.runs);
  const nodes = [
    el("div", { class: "notice", role: "status", id: "results-notice" },
      el("strong", {}, officialRunsHeadline(view.runs.length), " المستودع."),
      el("span", {}, " الحكم الآلي مساعد للمراجعة لا بديل عنها.")),
    gateSection(view.gate, latest, view.runs),
    // «ماذا اكتشف مِعيار؟» قسم ثابت مولَّد من السجلات الرسمية؛ يُنقل إلى ما بعد قرار البوابة مباشرة
    ...(document.getElementById("discovered") ? [document.getElementById("discovered")] : []),
    el("h2", { id: "compare-h" }, "المقارنة: baseline مقابل rag"),
    el("p", {}, "rag هو baseline نفسه مع بحث في المصادر المعتمدة فقط؛ ومِعيار لا يستعمل محرك حكمه داخل أي مساعد."),
    comparisonTable(latest),
    caveat(latest, "compare-caveat"),
  ];
  nodes.push(el("p", { class: "notice demo", role: "note", id: "specialist-note" },
    el("strong", {}, "المراجعة الشرعية: "),
    "مراجعة واحدة لحالة واحدة من 12 (OFF-06) أجراها خريج شريعة هو قريب لصاحب المشروع، لا لجنة مستقلة؛ "
    + "وما عداها تحقق مصادر (source_check) يجريه المشارك وليس مراجعة شرعية."));
  nodes.push(el("p", { class: "muted small", id: "agreement-line" },
    "وتحقق المصادر لتعريف الحالات، لا لأحكام مِعيار. ", AGREEMENT_NOTE));
  nodes.push(
    stabilitySection(view.stability),
    ...singleRunNotes(view.runs, view.stability),
    techDetails(latest, view.runs),
  );
  root.replaceChildren(...nodes);
}

async function main() {
  const root = document.getElementById("results");
  let response = null;
  try {
    const res = await fetch(RESULTS_URL, { cache: "no-store" });
    response = { status: res.status, ok: res.ok, text: res.ok ? await res.text() : "" };
  } catch {
    // تعذّر الاتصال: رسالة خطأ بخطوة تالية، لا «لا نتائج»
    root.replaceChildren(el("div", { class: "notice error", role: "alert" },
      el("strong", {}, "تعذّر تحميل ملف النتائج"),
      el("span", {}, "تحقق من اتصالك ثم أعد تحميل الصفحة. لا تُعرض أي أرقام دون الملف.")));
    return;
  }
  const view = interpretResults(response);
  if (view.state === "ok") renderOk(root, view);
  else if (view.state === "invalid") renderInvalid(root, view.errors);
  else renderEmpty(root);
}

main();
