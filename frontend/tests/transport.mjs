// Build with VITE_USE_MOCK_API=false, VITE_ENABLE_FEEDBACK=true,
// VITE_MIZAN_API_URL=http://127.0.0.1:4174/engine and VITE_API_TIMEOUT_MS=100.
// Preview that build on 4174, then run: node tests/transport.mjs
import { chromium, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
const source = JSON.parse(
  await readFile(new URL("../src/mocks/fixtures/dorar.json", import.meta.url)),
);
const result = {
  check_id: "transport-check",
  status: "ok",
  lang: "ar",
  claims: [
    {
      index: 0,
      type: "hadith",
      span: "نص اختبار",
      verdict: "not_established",
      evidence: source,
      source_status: "ok",
    },
  ],
  reply_available: true,
};
const browser = await chromium.launch(
  process.env.MIZAN_BROWSER_CHANNEL
    ? { channel: process.env.MIZAN_BROWSER_CHANNEL }
    : {},
);
const page = await browser.newPage();
let responseType = "ok";
const requests = [];
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.route("**/engine/**", async (route) => {
  const req = route.request();
  requests.push({
    path: new URL(req.url()).pathname,
    method: req.method(),
    body: req.postDataJSON(),
  });
  if (responseType === "network") return route.abort("failed");
  if (responseType === "timeout") {
    await new Promise((r) => setTimeout(r, 250));
    try {
      await route.fulfill({ json: result });
    } catch {}
    return;
  }
  if (Number(responseType))
    return route.fulfill({
      status: Number(responseType),
      json: { detail: "Internal Server Error secret diagnostic" },
    });
  if (responseType === "invalid")
    return route.fulfill({
      json: {
        ...result,
        claims: [{ ...result.claims[0], evidence: { source: { bad: true } } }],
      },
    });
  const path = new URL(req.url()).pathname;
  return route.fulfill({
    json: path.endsWith("/reply")
      ? { reply: null, reply_error: "validation_failed" }
      : path.endsWith("/feedback")
        ? { ok: true }
        : result,
  });
});
try {
  async function check() {
    await page.goto("http://127.0.0.1:4174");
    await page.locator("#quote-input").fill("نص اختبار");
    await page.getByRole("button", { name: "تحقّق", exact: true }).click();
  }
  await check();
  await expect(page.locator(".verdict")).toContainText("لا يثبت");
  expect(requests.at(-1)).toEqual({
    path: "/engine/api/v1/check",
    method: "POST",
    body: { text: "نص اختبار", channel: "web", lang_hint: null },
  });
  await expect(page.locator(".demo-banner")).toHaveCount(0);
  await expect(page.locator(".demo-tools")).toHaveCount(0);
  await page.getByRole("button", { name: "تجهيز رد مهذب" }).click();
  await expect(page.locator(".reply")).toContainText("غير متاح");
  await expect(page.locator(".reply textarea")).toHaveCount(0);
  await page.getByRole("button", { name: "إبلاغ عن مشكلة" }).click();
  await page.getByLabel("نوع المشكلة").selectOption("wrong_source");
  await page.getByLabel("ملاحظة (اختياري)").fill("test note");
  await page.getByRole("button", { name: "إرسال البلاغ" }).click();
  await expect(page.getByRole("dialog")).toContainText("وصل بلاغك");
  expect(requests.at(-1).body).toEqual({
    check_id: "transport-check",
    claim_index: 0,
    issue: "wrong_source",
    note: "test note",
  });
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "فتح صفحة النتيجة" }).click();
  await expect(page.locator(".verdict")).toBeVisible();
  expect(requests.at(-1).method).toBe("GET");
  for (const type of [
    "413",
    "422",
    "429",
    "500",
    "503",
    "network",
    "timeout",
    "invalid",
  ]) {
    responseType = type;
    await check();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("alert")).not.toContainText("Internal Server");
  }
  responseType = "404";
  await page.goto("http://127.0.0.1:4174/result/missing");
  await expect(page.getByRole("alert")).toContainText("انتهت مدة حفظها");
  expect(errors).toEqual([]);
  console.log(
    "PASS: real-mode check/reply/feedback/result contracts; optional reply validation fallback; 413/422/429/500/503, network, timeout, malformed payload and expired result errors.",
  );
} finally {
  await browser.close();
}
