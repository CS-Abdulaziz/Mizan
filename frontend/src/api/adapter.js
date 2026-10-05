export const VERDICTS = {
  verified: ["✓", "موثّق"],
  misquoted: ["⚠", "منقول بخطأ"],
  not_established: ["✕", "لا يثبت"],
  disputed: ["⚖", "اختلف المحدثون"],
  not_found: ["?", "لم يُعثر عليه"],
  needs_review: ["?", "يحتاج مراجعة مختص"],
};
export function safeUrl(value) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}
export function normalizeResult(data) {
  if (
    !data ||
    typeof data !== "object" ||
    !["ok", "success", "no_claims", "evidence_request", "referral"].includes(
      data.status,
    ) ||
    !Array.isArray(data.claims) ||
    typeof data.check_id !== "string" ||
    !data.check_id
  )
    throw new Error("invalid_response");
  const textFields = (object, keys) => {
    for (const key of keys)
      if (object[key] != null && typeof object[key] !== "string")
        throw new Error("invalid_response");
  };
  const record = (object) => {
    if (!object || typeof object !== "object" || Array.isArray(object))
      throw new Error("invalid_response");
  };
  function validateEvidence(object) {
    record(object);
    textFields(object, [
      "source",
      "text_arabic",
      "translation",
      "url",
      "attribution",
    ]);
    for (const key of ["gradings", "locations"])
      if (object[key] != null && !Array.isArray(object[key]))
        throw new Error("invalid_response");
    for (const grade of object.gradings || []) {
      record(grade);
      textFields(grade, ["mohaddith", "book", "grade_text", "grade_class"]);
      if (
        grade.page != null &&
        !["number", "string"].includes(typeof grade.page)
      )
        throw new Error("invalid_response");
    }
    for (const location of object.locations || []) {
      record(location);
      textFields(location, ["surah_name_ar", "surah_name_en", "url"]);
      for (const key of ["surah", "ayah"])
        if (
          location[key] != null &&
          !["number", "string"].includes(typeof location[key])
        )
          throw new Error("invalid_response");
    }
  }
  textFields(data, ["lang", "message", "disclaimer", "expires_at"]);
  if (data.referral != null) {
    record(data.referral);
    textFields(data.referral, ["reason", "text", "url"]);
  }
  const indexes = new Set();
  return {
    ...data,
    status: data.status === "success" ? "ok" : data.status,
    claims: data.claims.map((claim, index) => {
      if (
        !claim ||
        typeof claim.span !== "string" ||
        !Number.isInteger(claim.index) ||
        indexes.has(claim.index) ||
        typeof claim.type !== "string"
      )
        throw new Error("invalid_response");
      indexes.add(claim.index);
      textFields(claim, ["verdict", "relation", "lang", "source_status"]);
      if (claim.evidence != null) validateEvidence(claim.evidence);
      if (claim.alternative != null) {
        record(claim.alternative);
        textFields(claim.alternative, [
          "source",
          "text_arabic",
          "translation",
          "attribution",
          "url",
          "label",
        ]);
      }
      if (claim.diff != null) {
        record(claim.diff);
        textFields(claim.diff, ["kind", "details"]);
        if (claim.diff.ops != null && !Array.isArray(claim.diff.ops))
          throw new Error("invalid_response");
        for (const op of claim.diff.ops || []) {
          record(op);
          textFields(op, ["op", "quoted", "source"]);
        }
      }
      if (
        claim.notes != null &&
        (!Array.isArray(claim.notes) ||
          claim.notes.some((note) => typeof note !== "string"))
      )
        throw new Error("invalid_response");
      return {
        ...claim,
        index: claim.index ?? index,
        verdict: VERDICTS[claim.verdict] ? claim.verdict : "needs_review",
        notes: Array.isArray(claim.notes) ? claim.notes : [],
        evidence: claim.evidence || null,
      };
    }),
  };
}
export function checkRequest(text) {
  return { text, channel: "web", lang_hint: null };
}
// Backend offsets are Unicode character positions (Python), not UTF-16 units.
export function quoteSegments(text, claims) {
  const chars = Array.from(text),
    segments = [];
  let cursor = 0;
  const spans = claims
    .filter(
      (c) => Number.isInteger(c.span_start) && Number.isInteger(c.span_end),
    )
    .sort((a, b) => a.span_start - b.span_start);
  for (const claim of spans) {
    const start = claim.span_start,
      end = claim.span_end;
    if (
      start < cursor ||
      end <= start ||
      end > chars.length ||
      chars.slice(start, end).join("") !== claim.span
    )
      continue;
    if (start > cursor)
      segments.push({
        text: chars.slice(cursor, start).join(""),
        marked: false,
      });
    segments.push({ text: chars.slice(start, end).join(""), marked: true });
    cursor = end;
  }
  if (cursor < chars.length)
    segments.push({ text: chars.slice(cursor).join(""), marked: false });
  return segments;
}
