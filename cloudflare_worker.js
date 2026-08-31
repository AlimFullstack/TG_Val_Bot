/**
 * Cloudflare Worker — прокси к Telegram Bot API.
 * Залей это в Cloudflare Workers (бесплатно).
 * Бот ходит на твой *.workers.dev, Worker — на api.telegram.org.
 */
export default {
  async fetch(request) {
    const incoming = new URL(request.url);

    // health-check
    if (incoming.pathname === "/" || incoming.pathname === "") {
      return new Response(
        JSON.stringify({ ok: true, proxy: "telegram-bot-api" }),
        { headers: { "content-type": "application/json" } }
      );
    }

    const target = new URL(request.url);
    target.hostname = "api.telegram.org";
    target.protocol = "https:";

    const init = {
      method: request.method,
      headers: request.headers,
      redirect: "follow",
    };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
      // @ts-ignore
      init.duplex = "half";
    }

    return fetch(new Request(target.toString(), init));
  },
};
