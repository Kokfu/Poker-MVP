import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

test("leak breakdown displays the largest cost first and preserves missing estimates", async (t) => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false } });
  t.after(() => vite.close());
  const { LeakBreakdown } = await vite.ssrLoadModule("/src/MyLeaks.tsx");
  const rows = [
    { label: "preflop_open", decisions: 1, different: 1, costed: 0, deviation_rate: 1, total_cost_bb: null, average_cost_bb: null },
    { label: "flop_defend", decisions: 2, different: 1, costed: 2, deviation_rate: 0.5, total_cost_bb: 3.4, average_cost_bb: 1.7 },
  ];
  const markup = renderToStaticMarkup(createElement(LeakBreakdown, { title: "By spot type", rows }));
  assert.match(markup, /Flop defend.*50%.*3\.40 BB.*1\.70 BB.*Preflop open.*100%.*—/);
  assert.match(markup, /0 of 1 decisions had an EV estimate/);
});
