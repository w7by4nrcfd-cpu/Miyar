// صفحة النتائج: تقرأ data/results.json (ناتج scripts/publish_results.py من evaluation/official/) وتعرضه دون أي رقم مصطنع.
import {
  comparisonCaveat, comparisonRows, interpretResults, latestByAssistant, LEVELS, noSpecialistReview, officialRunsHeadline,
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

const caveat = (runs, id) => el("p", { class: "notice demo caveat", role: "note", id }, comparisonCaveat(runs));

function gateSection(gate, latest) {
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
  for (const r of gate.reasons) reasons.append(el("li", {}, r));
  sec.append(el("h3", {}, "السبب"), reasons,
    el("p", { class: "notice demo", role: "note", id: "gate-sensitivity" },
      el("strong", {}, "القرار حساس لاختيار الجولة المرجعية. "),
      "يُحسب القرار مقابل آخر جولة baseline منشورة، وجولات baseline تتفاوت درجاتها فيما بينها؛ فقد تتغير الأسباب وهوامشها بتغيير الجولة المرجعية. "
      + "لا تُختار جولة مرجعية بحسب النتيجة."),
    el("p", { class: "small" }, el("strong", {}, "القاعدة: "), gate.rule),
    el("p", { class: "muted small" }, "القرار محسوب بـ scoring.gate_decision من السجلين الرسميين، لا من هذه الصفحة."),
    caveat(latest, "gate-caveat"));
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
    sec.append(el("h3", {}, ltr(assistant), ` — التشغيلات: ${st.run_ids.join("، ")}`),
      el("div", { class: "table-wrap", role: "region", "aria-label": `ثبات ${assistant}`, tabindex: "0" },
        el("table", { class: "stack" },
          el("thead", {}, el("tr", {}, ...["المقياس", "الأدنى", "الأعلى", "الفرق", "تشغيلات بدرجة"].map((h) => el("th", { scope: "col" }, h)))),
          body)));
  }
  sec.append(el("p", { class: "muted" }, "تُعرض التشغيلات كلها؛ لا يُختار أفضلها."));
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
      ? " السبب في هذا التشغيل حد Groq اليومي المجاني: الجولات الناقصة لم تُحتسب وحُفظت في evaluation/official_incomplete/."
      : "";
    notes.push(el("p", { class: "notice demo single-run", role: "note" },
      el("strong", {}, `لـ ${assistant} جولة مكتملة واحدة فقط، فالثبات غير قابل للقياس له. `),
      "ولا يصح الاستدلال من جولة واحدة على استقراره." + why));
  }
  return notes;
}

function renderOk(root, view) {
  const latest = latestByAssistant(view.runs);
  const nodes = [
    el("div", { class: "notice", role: "status", id: "results-notice" },
      el("strong", {}, officialRunsHeadline(view.runs.length), " ", ltr("evaluation/official/"), "."),
      el("span", {}, " كل رقم من سجله المذكور ومعه عدد الحالات N، ويحسبه سكربت النشر من أحكام السجلات. الحكم الآلي مساعد للمراجعة لا بديل عنها.")),
    gateSection(view.gate, latest),
    el("h2", { id: "compare-h" }, "المقارنة: baseline مقابل rag"),
    el("p", {}, "rag هو نموذج baseline نفسه مع بحث في المصادر المعتمدة فقط (آيات Quranpedia ومدخلات الملف اليدوي المكتملة)، "
      + "ومِعيار لا يستعمل محرك حكمه داخل أي مساعد. الحالة المحالة إلى مراجعة بشرية أو المتعذّرة لا تُحتسب في الدرجة."),
    comparisonTable(latest),
    caveat(latest, "compare-caveat"),
  ];
  if (noSpecialistReview(view.runs)) {
    nodes.push(el("p", { class: "notice demo", role: "note" },
      el("strong", {}, "لم تُجرَ مراجعة شرعية متخصصة. "),
      "تحقق المصادر (source_check) يجريه المشارك، وليس مراجعة شرعية متخصصة."));
  }
  nodes.push(
    el("h3", {}, "السجلات المعروضة في المقارنة"), recordsList(latest),
    stabilitySection(view.stability),
    ...singleRunNotes(view.runs, view.stability),
    el("h2", {}, "كل التشغيلات الرسمية المنشورة"), recordsList(view.runs),
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
    response = null; // تعذّر الوصول = لا نتائج
  }
  const view = interpretResults(response);
  if (view.state === "ok") renderOk(root, view);
  else if (view.state === "invalid") renderInvalid(root, view.errors);
  else renderEmpty(root);
}

main();
