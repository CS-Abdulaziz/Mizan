import { normalizeResult, checkRequest } from "./adapter.js";
import {
  mockCheck,
  mockReply,
  fixture,
  scenarios,
} from "../mocks/responses.js";
export const USE_MOCK = import.meta.env.VITE_USE_MOCK_API !== "false";
export const FEATURES = {
  reply: import.meta.env.VITE_ENABLE_REPLY !== "false",
  feedback: import.meta.env.VITE_ENABLE_FEEDBACK === "true",
};
const baseUrl = (
  import.meta.env.VITE_MIZAN_API_URL ||
  import.meta.env.VITE_API_URL ||
  ""
).replace(/\/$/, "");
const configuredTimeout = Number(import.meta.env.VITE_API_TIMEOUT_MS);
const timeout =
  Number.isFinite(configuredTimeout) && configuredTimeout > 0
    ? configuredTimeout
    : 30000;
// Change endpoint names here when the contract changes, not in components.
const paths = {
  check: "/api/v1/check",
  result: (id) => `/api/v1/check/${encodeURIComponent(id)}`,
  reply: "/api/v1/reply",
  feedback: "/api/v1/feedback",
  sources: "/api/v1/sources",
};
export const errorMessages = {
  network: "تعذر الاتصال بالخدمة. تأكد من اتصالك ثم حاول مرة أخرى.",
  server: "تعذر إكمال التحقق الآن. حاول مرة أخرى بعد قليل.",
  timeout: "استغرق التحقق وقتًا أطول من المتوقع. حاول مرة أخرى.",
  unavailable: "خدمة التحقق غير متاحة حاليًا. حاول لاحقًا.",
  expired:
    "هذه النتيجة غير متاحة أو انتهت مدة حفظها. يمكنك التحقق من النص مجددًا.",
  invalid_response: "وصلت نتيجة لا يمكن عرضها بأمان. حاول مرة أخرى لاحقًا.",
  configuration: "خدمة التحقق لم تُربط بعد. حاول لاحقًا.",
  too_long: "النص طويل. اختصره إلى 4000 حرف ثم حاول مرة أخرى.",
  invalid_input: "أدخل نصًا صالحًا للتحقق.",
  rate_limit: "وصلت إلى حد الطلبات مؤقتًا. انتظر قليلًا ثم حاول مرة أخرى.",
  demo_only:
    "هذه نسخة تجريبية تعرض أمثلة ثابتة. اختر أحد الأمثلة لتجربتها؛ التحقق من نصوص أخرى يتطلب ربط الخدمة.",
};
export function humanError(error) {
  return errorMessages[error?.message] || errorMessages.server;
}
export async function request(path, { body, signal } = {}) {
  if (!baseUrl) throw new Error("configuration");
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort();
  if (signal?.aborted) cancel();
  else signal?.addEventListener("abort", cancel, { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeout);
  try {
    const response = await fetch(baseUrl + path, {
      method: body ? "POST" : "GET",
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: controller.signal,
    });
    if (!response.ok)
      throw new Error(
        {
          404: "expired",
          413: "too_long",
          422: "invalid_input",
          429: "rate_limit",
          503: "unavailable",
        }[response.status] || "server",
      );
    try {
      return await response.json();
    } catch {
      throw new Error("invalid_response");
    }
  } catch (error) {
    if (timedOut) throw new Error("timeout");
    if (error.name === "AbortError") throw error;
    if (error instanceof TypeError) throw new Error("network");
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}
export async function checkText(text, { scenario, signal } = {}) {
  if (!text.trim()) throw new Error("invalid_input");
  if (Array.from(text).length > 4000) throw new Error("too_long");
  const data = USE_MOCK
    ? await mockCheck(text, scenario, signal)
    : await request(paths.check, { body: checkRequest(text), signal });
  return normalizeResult(data);
}
export async function getResult(id, { signal } = {}) {
  if (!USE_MOCK)
    return normalizeResult(await request(paths.result(id), { signal }));
  const key = id.replace(/^demo-/, "");
  if (
    !id.startsWith("demo-") ||
    !scenarios.some((s) => s[0] === key) ||
    ["network", "server", "timeout", "expired"].includes(key)
  )
    throw new Error("expired");
  return normalizeResult(fixture(key));
}
export async function generateReply(result) {
  if (USE_MOCK) return mockReply(result);
  const data = await request(paths.reply, {
    body: { check_id: result.check_id, lang: result.lang },
  });
  if (data.reply_error || typeof data.reply !== "string" || !data.reply.trim())
    return null;
  return data.reply;
}
export async function submitFeedback(body) {
  if (USE_MOCK || !FEATURES.feedback) throw new Error("feedback_disabled");
  const data = await request(paths.feedback, { body });
  if (data.ok !== true) throw new Error("invalid_response");
  return data;
}
export function getSources() {
  return request(paths.sources);
}
