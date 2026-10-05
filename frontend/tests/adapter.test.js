import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeResult,
  safeUrl,
  quoteSegments,
  checkRequest,
} from "../src/api/adapter.js";
test("rejects invalid responses and preserves source outages without positive fallback", () => {
  assert.throws(() => normalizeResult({ status: "ok", claims: [] }));
  const result = normalizeResult({
    check_id: "abc",
    status: "ok",
    claims: [
      {
        index: 0,
        type: "hadith",
        span: "quote",
        verdict: "unexpected",
        source_status: "source_unavailable",
      },
    ],
  });
  assert.equal(result.claims[0].verdict, "needs_review");
  assert.equal(result.claims[0].source_status, "source_unavailable");
});
test("source links reject executable URLs", () => {
  assert.equal(safeUrl("javascript:alert(1)"), null);
  assert.equal(safeUrl("data:text/html,test"), null);
  assert.equal(
    safeUrl("https://dorar.net/h/example"),
    "https://dorar.net/h/example",
  );
});
test("Unicode offsets highlight exact text and ignore malformed or overlapping spans", () => {
  const input = "😀 hello world";
  const result = quoteSegments(input, [
    { span: "hello", span_start: 2, span_end: 7 },
    { span: "hello world", span_start: 2, span_end: 13 },
    { span: "wrong", span_start: 8, span_end: 13 },
  ]);
  assert.deepEqual(result, [
    { text: "😀 ", marked: false },
    { text: "hello", marked: true },
    { text: " world", marked: false },
  ]);
});
test("web requests match the current contract", () =>
  assert.deepEqual(checkRequest("quote"), {
    text: "quote",
    channel: "web",
    lang_hint: null,
  }));
