import { chromium, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
const base = process.env.MIZAN_TEST_URL || "http://127.0.0.1:4173";
const dir = process.env.MIZAN_QA_DIR || "test-results";
await mkdir(dir, { recursive: true });
const browser = await chromium.launch(
  process.env.MIZAN_BROWSER_CHANNEL
    ? { channel: process.env.MIZAN_BROWSER_CHANNEL }
    : {},
);
const context = await browser.newContext({
  permissions: ["clipboard-read", "clipboard-write"],
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
async function home() {
  await page.goto(base);
  await expect(
    page.getByRole("button", { name: "تحقّق", exact: true }),
  ).toBeDisabled();
}
async function scenario(id) {
  await page.locator(".demo-tools summary").click();
  await page.selectOption("#scenario", id);
  await page.getByRole("button", { name: "تحقّق", exact: true }).click();
}
try {
  await home();
  await page.getByRole("button", { name: "حديث متداول", exact: true }).click();
  await page.getByRole("button", { name: "تحقّق", exact: true }).click();
  await expect(page.locator(".loading")).toBeVisible();
  await expect(page.locator(".verdict")).toContainText("لا يثبت");
  await expect(page.locator(".alternative")).toContainText("بديل صحيح");
  await expect(page.locator(".grading")).toContainText("باطل");
  await page.getByRole("button", { name: "تجهيز رد مهذب" }).click();
  await expect(page.locator(".reply textarea")).toBeVisible();
  await page.getByRole("button", { name: "نسخ الرد" }).click();
  await expect(page.locator(".reply")).toContainText("تم نسخ الرد");
  await page.getByRole("button", { name: "إبلاغ عن مشكلة" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("الإبلاغ غير متاح");
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "إبلاغ عن مشكلة" }),
  ).toBeFocused();
  await page.locator(".original summary").click();
  await expect(page.locator(".original mark")).toHaveCount(1);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: `${dir}/desktop-result.png`, fullPage: true });
  await page.getByRole("link", { name: "فتح صفحة النتيجة" }).click();
  await expect(page.locator(".verdict")).toContainText("لا يثبت");
  await page.reload();
  await expect(page.locator(".verdict")).toContainText("لا يثبت");
  await page.goto(`${base}/r/demo-china`);
  await expect(page.locator(".verdict")).toContainText("لا يثبت");
  for (const [id, label] of [
    ["quran", "موثّق"],
    ["english", "موثّق"],
    ["urdu", "موثّق"],
    ["misquoted", "منقول بخطأ"],
    ["disputed", "اختلف المحدثون"],
    ["not_found", "لم يُعثر عليه"],
    ["needs_review", "يحتاج مراجعة مختص"],
    ["source_unavailable", "تعذر الوصول للمصدر"],
  ]) {
    await home();
    await scenario(id);
    await expect(page.locator(".verdict")).toContainText(label);
    if (["english", "urdu"].includes(id))
      await expect(page.locator(".quote")).toHaveAttribute("dir", "auto");
    if (id === "source_unavailable")
      await expect(page.locator(".verdict")).not.toContainText("لم يُعثر عليه");
    if (id === "misquoted") {
      await page.locator(".claim details summary").click();
      await expect(page.locator("del")).toBeVisible();
      await expect(page.locator("ins")).toBeVisible();
    }
  }
  for (const [id, title] of [
    ["no_claims", "لم نجد آية أو حديثًا"],
    ["evidence_request", "لا ينشئ أدلة جديدة"],
    ["referral", "جهة مؤهلة للإفتاء"],
  ]) {
    await home();
    await scenario(id);
    await expect(page.locator(".special")).toContainText(title);
    if (id === "referral") await expect(page.locator(".claim")).toHaveCount(1);
  }
  await home();
  await scenario("multiple");
  await expect(page.locator(".claim")).toHaveCount(3);
  for (const id of ["network", "server", "timeout", "expired"]) {
    await home();
    await scenario(id);
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "إعادة المحاولة" }),
    ).toBeEnabled();
  }
  await home();
  await page.locator("#quote-input").fill("a".repeat(4001));
  await expect(
    page.getByRole("button", { name: "تحقّق", exact: true }),
  ).toBeDisabled();
  await page.locator("#quote-input").fill("نص غير موجود في الأمثلة");
  await page.getByRole("button", { name: "تحقّق", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("أمثلة ثابتة");
  await page.goto(`${base}/result/missing`);
  await expect(page.getByRole("alert")).toContainText("انتهت مدة حفظها");
  for (const [width, height] of [
    [1366, 768],
    [1440, 900],
    [1920, 1080],
    [390, 844],
    [393, 852],
    [430, 932],
  ]) {
    await page.setViewportSize({ width, height });
    await home();
    await page.evaluate(() => document.fonts.ready);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    const bounds = await page
      .getByRole("button", { name: "تحقّق", exact: true })
      .boundingBox();
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(height);
    if (width < 650) {
      await page.getByRole("button", { name: "القائمة" }).click();
      await expect(page.getByRole("navigation")).toBeVisible();
      await page.getByRole("button", { name: "إغلاق", exact: true }).click();
    }
    await page.screenshot({ path: `${dir}/home-${width}.png`, fullPage: true });
    await page
      .getByRole("button", { name: "حديث متداول", exact: true })
      .click();
    await page.getByRole("button", { name: "تحقّق", exact: true }).click();
    await expect(page.locator(".verdict")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    if (width === 390)
      await page.screenshot({
        path: `${dir}/mobile-result.png`,
        fullPage: true,
      });
  }
  await page.goto(base);
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await page.reload();
  await context.setOffline(true);
  await page.goto(base);
  await expect(page.getByRole("heading")).toContainText("تحتاج إلى اتصال");
  await context.setOffline(false);
  expect(errors).toEqual([]);
  console.log(
    "PASS: demo journey, all verdicts/statuses/errors, clipboard, dialog focus, result routes, six viewport sizes, offline fallback; no browser exceptions.",
  );
} finally {
  await browser.close();
}
