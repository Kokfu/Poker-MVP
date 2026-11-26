const PREFIX = "poker-coach-shell-";
const CACHE_NAME = PREFIX + "__POKER_SHELL_VERSION__";
const SHELL_FILES = "__POKER_SHELL_FILES__";

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(SHELL_FILES.map((path) => new Request(path, { cache: "reload" })));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const old = (await caches.keys()).filter((key) => key.startsWith(PREFIX) && key !== CACHE_NAME);
    await Promise.all(old.map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname === "/api" || url.pathname.startsWith("/api/")) return;
  if (request.mode === "navigate") {
    event.respondWith(navigate(request));
  } else if (SHELL_FILES.includes(url.pathname)) {
    event.respondWith(staticFile(url.pathname, request));
  }
});

async function navigate(request) {
  try {
    const response = await fetch(request);
    if (response.status < 500) return response;
  } catch {
    // The installed shell also handles an unreachable host on a connected phone.
  }
  const cache = await caches.open(CACHE_NAME);
  const shell = await cache.match("/");
  if (!shell) return Response.error();
  const html = (await shell.text()).replace('id="offline-shell" hidden', 'id="offline-shell"');
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
}

async function staticFile(path, request) {
  const cache = await caches.open(CACHE_NAME);
  return await cache.match(path) || fetch(request);
}
