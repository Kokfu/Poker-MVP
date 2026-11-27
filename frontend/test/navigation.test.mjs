import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "vite";

test("top-level tabs and both drill views have stable location fragments", async (t) => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false } });
  t.after(() => vite.close());
  const { routeFromHash, hashForRoute } = await vite.ssrLoadModule("/src/App.tsx");
  for (const route of ["coach", "drills", "drills/leaks", "practice", "analyzer", "simulator", "match", "replay"]) {
    assert.equal(routeFromHash(hashForRoute(route)), route);
  }
  assert.equal(hashForRoute("coach"), "");
  assert.equal(hashForRoute("drills/leaks"), "#drills/leaks");
  assert.equal(routeFromHash("#coach"), "coach");
  assert.equal(routeFromHash("#unknown"), "coach");
});
