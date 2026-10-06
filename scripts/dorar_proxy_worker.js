// Cloudflare Worker: forwards Dorar's official search API for the Mizan backend (D-32).
// Why: dorar.net's Cloudflare answers 403 (challenge page) to requests from Render's datacenter IPs.
// Scope: only GET /dorar_api.json?<query>; requires the shared key header; identifies itself honestly;
// caches each response for 24 h (fewer requests to Dorar). Secrets: set PROXY_KEY in the Worker settings.
const UPSTREAM = "https://dorar.net/dorar_api.json";
const UA = "Mizan/0.1 (Islamic quotation verifier; hackathon project; via Cloudflare Worker)";
const TTL = 24 * 3600;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method !== "GET" || url.pathname !== "/dorar_api.json")
      return new Response("not found", { status: 404 });
    if (!env.PROXY_KEY || request.headers.get("X-Mizan-Key") !== env.PROXY_KEY)
      return new Response("forbidden", { status: 403 });
    if (!url.searchParams.get("skey") || url.search.length > 2000)
      return new Response("bad request", { status: 400 });

    const upstream = UPSTREAM + url.search;
    const cache = caches.default;
    const cacheKey = new Request(upstream, { method: "GET" });
    const hit = await cache.match(cacheKey);
    if (hit) return hit;

    const r = await fetch(upstream, { headers: { "User-Agent": UA, Accept: "application/json" } });
    const body = await r.text();
    const isJson = (r.headers.get("content-type") || "").includes("json") && body.includes('"ahadith"');
    const resp = new Response(body, {
      status: isJson ? 200 : 502,
      headers: { "content-type": isJson ? "application/json; charset=utf-8" : "text/plain", "cache-control": `public, max-age=${TTL}` },
    });
    if (isJson) ctx.waitUntil(cache.put(cacheKey, resp.clone()));
    return resp;
  },
};
