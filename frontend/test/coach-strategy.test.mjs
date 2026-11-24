import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

test("Coach strategy renders solver frequencies and allows an empty fallback", async (t) => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false } });
  t.after(() => vite.close());
  const { CoachStrategy } = await vite.ssrLoadModule("/src/Coach.tsx");
  const render = (options) => renderToStaticMarkup(createElement(CoachStrategy, { options }));

  assert.equal(render([]), "");
  const strategy = render([
    { label: "fold", frequency: 0.25, ev: 0 },
    { label: "call", frequency: 0.75, ev: 120 },
  ]);
  assert.match(strategy, /Fold/);
  assert.match(strategy, /25%/);
  assert.match(strategy, /EV \+0/);
  assert.match(strategy, /Call/);
  assert.match(strategy, /75%/);
  assert.match(strategy, /EV \+120/);
});
