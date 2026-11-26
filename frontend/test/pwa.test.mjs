import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { runInNewContext } from "node:vm";

const site = "https://poker.example.test";
const files = ["/", "/assets/app.js", "/manifest.webmanifest", "/icons/poker-coach-192.png"];
const source = await readFile(new URL("../src/service-worker.js", import.meta.url), "utf8");

function serviceWorker() {
  const handlers = new Map();
  const added = [];
  const deleted = [];
  let online = true;
  const cached = new Map([
    ["/", '<body><div id="offline-shell" hidden class="offline-shell">Offline</div><div id="root"></div></body>'],
    ["/assets/app.js", "cached script"],
  ]);
  runInNewContext(source
    .replace('"__POKER_SHELL_VERSION__"', '"test"')
    .replace('"__POKER_SHELL_FILES__"', JSON.stringify(files)), {
    self: {
      location: new URL(site), addEventListener: (name, handler) => handlers.set(name, handler),
      skipWaiting: () => Promise.resolve(), clients: { claim: () => Promise.resolve() },
    },
    URL, Response,
    Request: class extends Request {
      constructor(path, options) { super(new URL(path, site), options); }
    },
    caches: {
      open: async () => ({
        addAll: async (requests) => added.push(...requests.map((request) => new URL(request.url).pathname)),
        match: async (path) => cached.has(path) ? new Response(cached.get(path)) : undefined,
      }),
      keys: async () => ["poker-coach-shell-old", "poker-coach-shell-test", "unrelated"],
      delete: async (key) => deleted.push(key),
    },
    fetch: async () => {
      if (!online) throw new Error("network unavailable");
      return new Response("live content");
    },
  });
  return {
    added, deleted, goOffline: () => { online = false; },
    event(name) {
      let work;
      handlers.get(name)({ waitUntil: (promise) => { work = promise; } });
      return work;
    },
    request(path, { method = "GET", mode = "cors" } = {}) {
      let response;
      handlers.get("fetch")({ request: { url: new URL(path, site).href, method, mode }, respondWith: (promise) => { response = promise; } });
      return response;
    },
  };
}

test("manifest points to standalone launch and correctly sized general and maskable icons", async () => {
  const base = new URL("../public/", import.meta.url);
  const manifest = JSON.parse(await readFile(new URL("manifest.webmanifest", base), "utf8"));
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.start_url, "/");
  assert.ok(manifest.icons.some((icon) => icon.purpose === "maskable" && icon.sizes === "512x512"));
  for (const { src, sizes } of [...manifest.icons, { src: "/icons/poker-coach-180.png", sizes: "180x180" }]) {
    const png = await readFile(new URL(src.slice(1), base));
    assert.equal(`${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`, sizes);
  }
});

test("worker precaches only versioned shell files and deletes only its stale caches", async () => {
  const worker = serviceWorker();
  await worker.event("install");
  await worker.event("activate");
  assert.deepEqual(worker.added, files);
  assert.deepEqual(worker.deleted, ["poker-coach-shell-old"]);
});

test("worker opens the shell offline and leaves API and cross-origin requests on the network", async () => {
  const worker = serviceWorker();
  assert.equal(await (await worker.request("/", { mode: "navigate" })).text(), "live content");
  worker.goOffline();
  const response = await worker.request("/", { mode: "navigate" });
  assert.match(await response.text(), /id="offline-shell" class="offline-shell".*id="root"/);
  assert.equal(await (await worker.request("/assets/app.js")).text(), "cached script");
  assert.equal(worker.request("/api/coach/review"), undefined);
  assert.equal(worker.request("/api", { mode: "navigate" }), undefined);
  assert.equal(worker.request("/api/drills/start", { method: "POST" }), undefined);
  assert.equal(worker.request("https://third-party.example/", { mode: "navigate" }), undefined);
});
