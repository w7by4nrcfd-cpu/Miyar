// منطق صفحة «تحقق من نص» بلا DOM: نقل حرفي لـ miyar/normalize.py وmiyar/quran_match.py وmiyar/hadith_match.py
// وmiyar/paste_check.py. المرجع هو بايثون؛ واختبار التطابق (tests/web/check.test.mjs) يقارن النتائج على الحالات نفسها.
// لا نموذج لغوي ولا استدعاء خارجي: البيانات من assets/check/ (نص Quranpedia ومدخلات الملف اليدوي المكتملة).

export const SUPPORTED = "supported";
export const NEEDS_REVIEW = "needs_review";
export const WRONG_OR_MISSING = "wrong_or_missing";
const TOTAL_VERSES = 6236;
const ALTERED_THRESHOLD = 0.8;
const MIN_FIND_TOKENS = 3;
const MAX_QUOTE_CHARS = 2000;
const REF_LOOKAHEAD = 12;
const REF_MAX_CHARS = 40;
const HADITH_BEFORE = 60;
const HADITH_AFTER = 80;
const MAX_SUGGESTIONS = 3;
const SUGGESTION_POOL = 25;
const QURAN_BRACKETS = [["﴿", "﴾"], ["﴾", "﴿"], ["{", "}"]];
const QUOTES = [["«", "»"], ["“", "”"], ['"', '"']];
const SALLA = "ﷺ";

// مسافات بايثون (str.isspace) بدل \s في JavaScript، لتطابق strip() و\s في re
const PY_WS = "\\t\\n\\u000b\\f\\r\\u001c-\\u001f \\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const PY_WS_RE = new RegExp(`[${PY_WS}]`, "u");
const ELLIPSIS = /\.{2,}|…|ـ{3,}/gu;

// ---------- normalize.py ----------
const DIACRITICS = /[ؐ-ًؚ-ٰٟۖ-ۭ࣓-ࣿ]/gu;
const ZERO_WIDTH = /[​-‏‪-‮⁦-⁩﻿]/gu;
const WORD_CHAR = /[\p{L}\p{N}\p{Mn}]/u;
const CHAR_MAP = new Map([
  ..."أإآٱٲٳٵ".split("").map((c) => [c, "ا"]),
  ["ؤ", "و"], ["ئ", "ي"],
  ["ى", "ي"], ["ی", "ي"], ["ې", "ي"],
  ["ة", "ه"],
  ["ک", "ك"], ["ڪ", "ك"], ["ہ", "ه"], ["ھ", "ه"],
  ...Array.from({ length: 10 }, (_, i) => [String.fromCharCode(0x0660 + i), String(i)]),
  ...Array.from({ length: 10 }, (_, i) => [String.fromCharCode(0x06f0 + i), String(i)]),
]);

export function normalize(text) {
  if (!text) return "";
  let t = text.normalize("NFC").replace(ZERO_WIDTH, "").replace(DIACRITICS, "").replaceAll("ـ", "");
  let out = "";
  for (const ch of t) {
    const m = CHAR_MAP.get(ch) ?? ch;
    out += WORD_CHAR.test(m) ? m : " ";
  }
  return out.split(" ").filter(Boolean).join(" ");
}
const words = (s) => (s ? s.split(" ") : []);

// ---------- أدوات بايثون ----------
function pyStrip(s, chars = null) {
  const a = Array.from(s);
  const drop = chars === null ? (c) => PY_WS_RE.test(c) : (c) => chars.includes(c);
  let i = 0, j = a.length;
  while (i < j && drop(a[i])) i++;
  while (j > i && drop(a[j - 1])) j--;
  return a.slice(i, j).join("");
}
function indexOfCp(cps, ch, from) {
  for (let i = from; i < cps.length; i++) if (cps[i] === ch) return i;
  return -1;
}
// round(x, 3) في بايثون: تقريب صحيح للقيمة الثنائية مع النصف إلى الزوجي
export function pyRound3(x) {
  const r = Number(x.toFixed(3));
  const t = x * 2000;
  if (Number.isInteger(t) && t % 2 !== 0 && t / 2000 === x) {
    const lo = Math.floor(x * 1000), hi = lo + 1;
    return (lo % 2 === 0 ? lo : hi) / 1000;
  }
  return r;
}
const pyRound9 = (x) => Number(x.toFixed(9));
const cmpArr = (a, b) => {
  for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  return a.length - b.length;
};

// difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
export function ratio(a, b) {
  const A = Array.from(a), B = Array.from(b);
  const b2j = new Map();
  B.forEach((c, j) => { if (!b2j.has(c)) b2j.set(c, []); b2j.get(c).push(j); });
  const longest = (alo, ahi, blo, bhi) => {
    let besti = alo, bestj = blo, bestsize = 0;
    let j2len = new Map();
    for (let i = alo; i < ahi; i++) {
      const newj2len = new Map();
      for (const j of b2j.get(A[i]) || []) {
        if (j < blo) continue;
        if (j >= bhi) break;
        const k = (j2len.get(j - 1) || 0) + 1;
        newj2len.set(j, k);
        if (k > bestsize) { besti = i - k + 1; bestj = j - k + 1; bestsize = k; }
      }
      j2len = newj2len;
    }
    while (besti > alo && bestj > blo && A[besti - 1] === B[bestj - 1]) { besti--; bestj--; bestsize++; }
    while (besti + bestsize < ahi && bestj + bestsize < bhi && A[besti + bestsize] === B[bestj + bestsize]) bestsize++;
    return [besti, bestj, bestsize];
  };
  let matches = 0;
  const queue = [[0, A.length, 0, B.length]];
  while (queue.length) {
    const [alo, ahi, blo, bhi] = queue.pop();
    const [i, j, k] = longest(alo, ahi, blo, bhi);
    if (k) {
      matches += k;
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
  }
  const la = A.length, lb = B.length;
  return la + lb ? (2 * matches) / (la + lb) : 1.0;
}

// ---------- quran_match.py ----------
function segments(quote) {
  return quote.split(ELLIPSIS).map((p) => words(normalize(p))).filter((p) => p.length);
}

class Stream {
  constructor(texts) {
    this.tokens = []; this.owner = []; this.verseSpan = [];
    texts.forEach((t, i) => {
      const toks = words(normalize(t));
      const start = this.tokens.length;
      for (const tok of toks) { this.tokens.push(tok); this.owner.push(i); }
      this.verseSpan.push([start, this.tokens.length]);
    });
    this.first = new Map();
    this.tokens.forEach((tok, pos) => { if (!this.first.has(tok)) this.first.set(tok, []); this.first.get(tok).push(pos); });
  }
  occurrences(q, lo = 0, hi = null) {
    if (!q.length) return [];
    hi = hi === null ? this.tokens.length : hi;
    const n = q.length;
    return (this.first.get(q[0]) || []).filter((p) => lo <= p && p + n <= hi && q.every((t, k) => this.tokens[p + k] === t));
  }
}

function matchRest(stream, segs, start, hi) {
  let pos = start + segs[0].length;
  for (const seg of segs.slice(1)) {
    const occ = stream.occurrences(seg, pos, hi);
    if (!occ.length) return null;
    pos = occ[0] + seg.length;
  }
  return pos;
}

function joinedMatch(segs, win) {
  const joined = win.join("");
  const bounds = new Set([0]);
  let acc = 0;
  for (const tok of win) { acc += tok.length; bounds.add(acc); }
  let pos = 0;
  for (const seg of segs) {
    const part = seg.join("");
    let i = joined.indexOf(part, pos);
    while (i >= 0 && !(bounds.has(i) && bounds.has(i + part.length))) i = joined.indexOf(part, i + 1);
    if (i < 0) return false;
    pos = i + part.length;
  }
  return true;
}

const locRef = (s, a1, a2) => (a1 === a2 ? `${s}:${a1}` : `${s}:${a1}-${a2}`);

export class QuranIndex {
  // data: {names, lens, simple, uthmani} كما يكتبه paste_check.quran_web_data
  constructor(data) {
    if (data.simple.length !== TOTAL_VERSES || data.uthmani.length !== TOTAL_VERSES) throw new Error("عدد الآيات غير صحيح");
    this.names = data.names;
    this.verses = [];
    this.pos = new Map();
    this.suraRange = new Map();
    let i = 0;
    data.lens.forEach((n, k) => {
      const sura = k + 1;
      this.suraRange.set(sura, [i, i + n]);
      for (let aya = 1; aya <= n; aya++, i++) {
        this.verses.push({ sura, aya, simple: data.simple[i], uthmani: data.uthmani[i] });
        this.pos.set(`${sura}:${aya}`, i);
      }
    });
    this.streams = [new Stream(data.simple), new Stream(data.uthmani)]; // بترتيب بايثون: simple ثم uthmani
    this.inv = new Map();
    for (const s of this.streams) {
      s.tokens.forEach((tok, p) => { if (!this.inv.has(tok)) this.inv.set(tok, new Set()); this.inv.get(tok).add(s.owner[p]); });
    }
    this.idf = new Map([...this.inv].map(([t, ids]) => [t, Math.log(TOTAL_VERSES / (1 + ids.size))]));
  }
  suraName(s) { const r = this.suraRange.get(s); return r ? this.names[s - 1] : null; }
  suraLength(s) { const r = this.suraRange.get(s); return r ? r[1] - r[0] : 0; }
  verse(s, a) { const i = this.pos.get(`${s}:${a}`); return i === undefined ? null : this.verses[i]; }
  versesRange(s, a1, a2 = a1) {
    const out = [];
    for (let a = a1; a <= a2; a++) { const v = this.verse(s, a); if (v) out.push(v); }
    return out;
  }

  find(quote, minTokens = MIN_FIND_TOKENS) {
    const segs = segments(quote);
    if (!segs.length || segs.reduce((n, s) => n + s.length, 0) < minTokens) return [];
    const results = [], seen = new Set();
    for (const stream of this.streams) {
      for (const start of stream.occurrences(segs[0])) {
        const sura = this.verses[stream.owner[start]].sura;
        const [, vhi] = this.suraRange.get(sura);
        const hi = stream.verseSpan[vhi - 1][1];
        const end = matchRest(stream, segs, start, hi);
        if (end === null) continue;
        const a1 = this.verses[stream.owner[start]].aya, a2 = this.verses[stream.owner[end - 1]].aya;
        const key = `${sura}|${a1}|${a2}`;
        if (!seen.has(key)) { seen.add(key); results.push([sura, a1, a2]); }
      }
    }
    results.sort(cmpArr);
    return results.map(([s, a1, a2]) => locRef(s, a1, a2));
  }

  inRange(quote, sura, a1, a2) {
    const segs = segments(quote);
    if (!segs.length) return false;
    const i1 = this.pos.get(`${sura}:${a1}`), i2 = this.pos.get(`${sura}:${a2}`);
    for (const stream of this.streams) {
      const lo = stream.verseSpan[i1][0], hi = stream.verseSpan[i2][1];
      for (const start of stream.occurrences(segs[0], lo, hi)) if (matchRest(stream, segs, start, hi) !== null) return true;
      if (joinedMatch(segs, stream.tokens.slice(lo, hi))) return true;
    }
    return false;
  }

  similarity(quote, sura, a1, a2 = a1) {
    const q = words(normalize(quote.replace(ELLIPSIS, " ")));
    if (!q.length) return 0.0;
    const i1 = this.pos.get(`${sura}:${a1}`), i2 = this.pos.get(`${sura}:${a2}`);
    let best = 0.0;
    const qs = q.join(" ");
    for (const stream of this.streams) {
      const lo = stream.verseSpan[i1][0], hi = stream.verseSpan[i2][1];
      const toks = stream.tokens.slice(lo, hi);
      const n = q.length;
      for (const size of new Set([Math.max(1, n - 1), n, n + 1])) {
        const windows = size >= toks.length ? [toks] : Array.from({ length: toks.length - size + 1 }, (_, j) => toks.slice(j, j + size));
        for (const w of windows) best = Math.max(best, ratio(qs, w.join(" ")));
      }
    }
    return pyRound3(best);
  }

  verify(quote, sura, aya, ayaEnd = null) {
    ayaEnd = ayaEnd === null ? aya : ayaEnd;
    const cited = locRef(sura, aya, ayaEnd);
    const n = this.suraLength(sura);
    if (n === 0 || !(1 <= aya && aya <= ayaEnd && ayaEnd <= n)) {
      return { status: WRONG_OR_MISSING, reason: "invalid_reference", cited, foundAt: this.find(quote), similarity: null };
    }
    const qTokens = segments(quote).flat();
    if (qTokens.length < 2) return { status: NEEDS_REVIEW, reason: "quote_too_short", cited, foundAt: [], similarity: null };
    if (this.inRange(quote, sura, aya, ayaEnd)) return { status: SUPPORTED, reason: "exact_match", cited, foundAt: [cited], similarity: 1.0 };
    const elsewhere = this.find(quote, 2);
    if (elsewhere.length) return { status: WRONG_OR_MISSING, reason: "wrong_reference", cited, foundAt: elsewhere, similarity: null };
    const sim = this.similarity(quote, sura, aya, ayaEnd);
    if (sim >= ALTERED_THRESHOLD) return { status: WRONG_OR_MISSING, reason: "altered_text", cited, foundAt: [], similarity: sim };
    return { status: NEEDS_REVIEW, reason: "not_found", cited, foundAt: [], similarity: sim };
  }
}

// ---------- paste_check.py ----------
const REF_FILLER = new Set(["سوره", "الايه", "ايه", "الايات", "ايات", "رقم", "اية", "الاية"]);
const HADITH_MARKERS_BEFORE = ["قال رسول الله", "قال النبي", "عن النبي", "عن رسول الله", "صلي الله عليه وسلم"];
const HADITH_MARKERS_AFTER = ["رواه", "اخرجه", "متفق عليه"];
const DIGITS = /^[0-9]+$/;
const REF_RE = new RegExp(`^[${PY_WS}،,:.\\-–]{0,${REF_LOOKAHEAD}}[(\\[]([^()\\[\\]]{1,${REF_MAX_CHARS}})[)\\]]`, "u");

const stripAl = (name) => (name.startsWith("ال") ? pyStrip(name.slice(2)) : name);

export function suraByName(index) {
  const out = new Map();
  for (let s = 1; s <= 114; s++) {
    const n = normalize(index.suraName(s) || "");
    if (!out.has(n)) out.set(n, s);
    if (!out.has(stripAl(n))) out.set(stripAl(n), s);
  }
  return out;
}

export function parseReference(after, names) {
  const m = REF_RE.exec(after);
  if (!m) return null;
  const toks = words(normalize(m[1]));
  const nums = toks.filter((t) => DIGITS.test(t)).map(Number);
  const ws = toks.filter((t) => !DIGITS.test(t) && !REF_FILLER.has(t));
  let sura, aya, ayaEnd;
  if (ws.length) {
    const name = ws.join(" ");
    sura = names.get(name) || names.get(stripAl(name));
    if (sura === undefined || !(nums.length >= 1 && nums.length <= 2)) return null;
    [aya, ayaEnd] = [nums[0], nums.length === 2 ? nums[1] : null];
  } else {
    if (!(nums.length >= 2 && nums.length <= 3)) return null;
    [sura, aya, ayaEnd] = [nums[0], nums[1], nums.length === 3 ? nums[2] : null];
  }
  return { text: pyStrip(m[0], " ،,:.-–"), sura, aya, aya_end: ayaEnd };
}

function spans(cps, pairs) {
  const out = [];
  for (const [o, c] of pairs) {
    let i = 0, a;
    while ((a = indexOfCp(cps, o, i)) >= 0) {
      const b = indexOfCp(cps, c, a + 1);
      if (b < 0) break;
      if (b - a - 1 > 0 && b - a - 1 <= MAX_QUOTE_CHARS) out.push([a, a + 1, b, b + 1]);
      i = b + 1;
    }
  }
  out.sort(cmpArr);
  const kept = [];
  let last = -1;
  for (const s of out) if (s[0] >= last) { kept.push(s); last = s[3]; }
  return kept;
}

export function extract(text, index, names = suraByName(index)) {
  const cps = Array.from(text);
  const sl = (a, b) => cps.slice(Math.max(0, a), b).join("");
  const found = [], taken = [];
  for (const [a, qs, qe, b] of spans(cps, QURAN_BRACKETS)) {
    const quote = pyStrip(sl(qs, qe));
    if (quote) {
      found.push({ kind: "quran", quote, start: a, ref: parseReference(sl(b, cps.length), names) });
      taken.push([a, b]);
    }
  }
  for (const [a, qs, qe, b] of spans(cps, QUOTES)) {
    if (taken.some(([x, y]) => x < b && a < y)) continue;
    const quote = pyStrip(sl(qs, qe));
    if (!quote) continue;
    const ref = parseReference(sl(b, cps.length), names);
    if (ref !== null) { found.push({ kind: "quran", quote, start: a, ref }); continue; }
    const beforeRaw = sl(a - HADITH_BEFORE, a);
    const before = ` ${normalize(beforeRaw)} `;
    const afterRaw = sl(b, b + HADITH_AFTER).split(/[.\n!؟?]/u)[0];
    const after = normalize(afterRaw);
    const hasBefore = beforeRaw.includes(SALLA) || HADITH_MARKERS_BEFORE.some((m) => before.includes(` ${normalize(m)} `));
    const hasAfter = HADITH_MARKERS_AFTER.some((m) => ` ${after} `.includes(` ${normalize(m)} `));
    if (hasBefore || hasAfter) {
      const cited = hasAfter ? pyStrip(afterRaw, " ،,:-–()[]") : null;
      found.push({ kind: "hadith", quote, start: a, cited: cited || null });
    }
  }
  found.sort((x, y) => x.start - y.start);
  return found;
}

export function suggestions(index, quote, limit = MAX_SUGGESTIONS) {
  const q = words(normalize(quote.replace(ELLIPSIS, " ")));
  if (!q.length) return [];
  const weights = new Map();
  for (const tok of [...new Set(q)].sort()) {
    for (const vid of index.inv.get(tok) || []) weights.set(vid, (weights.get(vid) || 0) + (index.idf.get(tok) || 0));
  }
  const pool = [...weights.keys()].sort((x, y) => (pyRound9(weights.get(y)) - pyRound9(weights.get(x))) || x - y).slice(0, SUGGESTION_POOL);
  const scored = pool.map((vid) => { const v = index.verses[vid]; return [-index.similarity(quote, v.sura, v.aya), v.sura, v.aya]; });
  scored.sort(cmpArr);
  return scored.slice(0, limit).map(([neg, s, a]) => ({ ref: `${s}:${a}`, score: -neg }));
}

export function versePayload(index, ref) {
  const [s, rest] = ref.split(":");
  const [a1, a2] = rest.split("-");
  const vs = index.versesRange(Number(s), Number(a1), Number(a2 || a1));
  return { ref, sura_name: index.suraName(Number(s)), text: vs.map((v) => v.simple).join(" ") };
}

export function checkQuran(item, index) {
  const { quote, ref } = item;
  let status, reason, sim, foundAt, cited, validRef;
  if (ref) {
    const c = index.verify(quote, ref.sura, ref.aya, ref.aya_end);
    ({ status, reason, similarity: sim, foundAt, cited } = c);
    validRef = reason !== "invalid_reference";
  } else {
    cited = null; validRef = false;
    if (segments(quote).reduce((n, s) => n + s.length, 0) < MIN_FIND_TOKENS) {
      [status, reason, sim, foundAt] = [NEEDS_REVIEW, "quote_too_short", null, []];
    } else {
      foundAt = index.find(quote);
      if (foundAt.length) [status, reason, sim] = [SUPPORTED, "exact_match_unreferenced", 1.0];
      else {
        const sugg = suggestions(index, quote, 1);
        sim = sugg.length ? sugg[0].score : 0.0;
        status = sim >= ALTERED_THRESHOLD ? WRONG_OR_MISSING : NEEDS_REVIEW;
        reason = status === WRONG_OR_MISSING ? "altered_text_unreferenced" : "not_found";
      }
    }
  }
  const out = {
    kind: "quran", quote, ref_text: ref ? ref.text : null, cited, status, reason, similarity: sim,
    found_at: foundAt.map((r) => versePayload(index, r)),
    cited_verse: cited && validRef ? versePayload(index, cited) : null,
    suggestions: [],
  };
  if (status !== SUPPORTED && !foundAt.length) {
    out.suggestions = suggestions(index, quote).map((s) => ({ ...versePayload(index, s.ref), score: s.score }));
  }
  return out;
}

// ---------- hadith_match.py (على المدخلات المكتملة وحدها) ----------
const COLLECTIONS = {
  bukhari: ["البخاري"], muslim: ["مسلم"], ibn_majah: ["ابن ماجه"],
  abu_dawud: ["ابو داود"], tirmidhi: ["الترمذي"], nasai: ["النسائي"],
};
const BOTH_SAHIHS = ["الصحيحين", "الصحيحان"];
const MIN_MATCH_WORDS = 3;
const KINDS = { found: ["text", "source", "link", "grade", "grade_by"], not_found: ["query", "searched_in", "link"], collection_range: ["source", "max_number", "link"] };
const COMMON = ["entered_by", "entered_at"];
const filled = (v) => !(v === null || v === undefined || v === "" || (typeof v === "string" && !pyStrip(v)));

export function entryStatus(e) {
  return [...(KINDS[e.kind] || []), ...COMMON].every((k) => filled(e[k])) ? "complete" : "pending";
}
function citedCollections(cited) {
  const n = ` ${normalize(cited || "")} `;
  const found = new Set(Object.entries(COLLECTIONS).filter(([, ns]) => ns.some((nm) => n.includes(` ${nm} `))).map(([k]) => k));
  if (BOTH_SAHIHS.some((b) => n.includes(` ${b} `))) { found.add("bukhari"); found.add("muslim"); }
  return found;
}
function citedNumber(cited) {
  const nums = normalize(cited || "").match(/\d+/g) || [];
  return nums.length === 1 ? Number(nums[0]) : null;
}
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function sourceNumbers(source, collection) {
  const n = normalize(source || "");
  const out = new Set();
  for (const name of COLLECTIONS[collection]) {
    for (const m of n.matchAll(new RegExp(`(?<!\\S)${escapeRe(name)}\\s+(?:رقم\\s+)?(\\d+)`, "g"))) out.add(Number(m[1]));
  }
  return out;
}
function findEntries(quote, doc) {
  const q = normalize(quote || "");
  if (words(q).length < MIN_MATCH_WORDS) return [];
  return doc.entries.filter((e) => {
    if (!["found", "not_found"].includes(e.kind)) return false;
    const p = normalize(e.text || e.query || "");
    return words(p).length >= MIN_MATCH_WORDS && (q.includes(p) || p.includes(q));
  });
}
const H = (status, reason, e = null) => ({ status, reason, entry_id: e ? e.id : null, entry: e });
function rangeCheck(cited, doc) {
  const number = citedNumber(cited), cols = citedCollections(cited);
  if (number === null || !cols.size) return null;
  for (const e of doc.entries) {
    if (e.kind !== "collection_range" || ![...citedCollections(e.source)].some((c) => cols.has(c))) continue;
    if (!Number.isInteger(e.max_number) || number <= e.max_number) continue;
    if (entryStatus(e) !== "complete") return H(NEEDS_REVIEW, "manual_entry_pending", e);
    return H(WRONG_OR_MISSING, "number_out_of_range", e);
  }
  return null;
}
export function verifyHadith(quote, cited, doc) {
  const ranged = rangeCheck(cited, doc);
  if (ranged) return ranged;
  const entries = findEntries(quote, doc);
  if (!entries.length) return H(NEEDS_REVIEW, "no_manual_entry");
  const complete = entries.filter((e) => entryStatus(e) === "complete");
  if (!complete.length) return H(NEEDS_REVIEW, "manual_entry_pending", entries[0]);
  const e = complete[0];
  if (e.kind === "not_found") return H(NEEDS_REVIEW, "not_found_in_manual_search", e);
  const cols = citedCollections(cited), number = citedNumber(cited);
  if (!cols.size) return H(NEEDS_REVIEW, "location_not_stated", e);
  if (number === null) return H(NEEDS_REVIEW, "number_not_stated", e);
  if ([...cols].every((c) => sourceNumbers(e.source, c).has(number))) return H(SUPPORTED, "matched_manual_entry", e);
  return H(NEEDS_REVIEW, "cited_location_not_in_entry_source", e);
}

const ENTRY_KEYS = ["kind", "text", "query", "source", "grade", "grade_by", "link", "max_number"];
export function checkHadith(item, doc) {
  const c = verifyHadith(item.quote, item.cited ?? null, doc);
  const entry = c.entry ? Object.fromEntries(ENTRY_KEYS.filter((k) => k in c.entry).map((k) => [k, c.entry[k]])) : null;
  return { kind: "hadith", quote: item.quote, cited: item.cited ?? null, status: c.status, reason: c.reason, entry_id: c.entry_id, entry };
}

// doc: {entries} — المدخلات المكتملة فقط، كما يكتبها paste_check.complete_manual
export function checkText(text, index, doc, names = suraByName(index)) {
  return extract(text, index, names).map((i) => (i.kind === "quran" ? checkQuran(i, index) : checkHadith(i, doc)));
}

// ---------- العرض ----------
export const STATUS_LABELS = { [SUPPORTED]: "مؤيَّد", [WRONG_OR_MISSING]: "لم تُطابَق", [NEEDS_REVIEW]: "يحتاج تحقق" };
export const REASONS = {
  exact_match: "النص مطابق حرفياً للآية في الموضع المذكور.",
  exact_match_unreferenced: "لم يُذكر موضع، والنص مطابق حرفياً لآية في الموضع المبيَّن.",
  wrong_reference: "النص موجود في المصحف، لكن في غير الموضع المذكور.",
  invalid_reference: "الموضع المذكور غير موجود في المصحف.",
  altered_text: "النص قريب جداً من الآية المذكورة لكنه ليس نصها: نقل محرّف.",
  altered_text_unreferenced: "لم يُذكر موضع، والنص قريب جداً من آية لكنه ليس نصها: نقل محرّف.",
  not_found: "لم يُعثر على النص في المصحف ولا على آية قريبة منه بما يكفي.",
  quote_too_short: "النص أقصر من أن يُطابَق بثقة.",
  matched_manual_entry: "طابق مدخلاً مكتملاً في الملف اليدوي، والموضع المذكور يطابق مصدره.",
  no_manual_entry: "لا مدخل مكتمل في الملف اليدوي يطابق هذا النص.",
  not_found_in_manual_search: "سُجّل في الملف اليدوي أنه لم يُعثر عليه في البحث اليدوي.",
  location_not_stated: "طابق مدخلاً في الملف اليدوي، لكن لم يُذكر كتاب التخريج.",
  number_not_stated: "طابق مدخلاً في الملف اليدوي، لكن لم يُذكر رقم الحديث.",
  cited_location_not_in_entry_source: "طابق مدخلاً في الملف اليدوي، لكن الموضع المذكور لا يظهر في مصدره.",
  number_out_of_range: "رقم الحديث المذكور يتجاوز ترقيم الكتاب في الملف اليدوي.",
  manual_entry_pending: "المدخل المطابق في الملف اليدوي غير مكتمل.",
};
