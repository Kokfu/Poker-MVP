import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

test("recent attempt reviews show a timeout, earlier cards, and the stored solver mix", async (t) => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false } });
  t.after(() => vite.close());
  const { AttemptReview } = await vite.ssrLoadModule("/src/DrillAttempts.tsx");
  const attempt = { id: "saved-turn", created_at: "2026-11-26T00:00:00+00:00", spot: {
    category: "river_call", hero_cards: ["As", "8h"], board: ["Qs", "6c", "Ad", "Js", "5h"], history: [
      { street: "river", actor: "villain", action: "bet", amount: 250 },
    ],
  }, feedback: {
    action: "timeout", amount: null, elapsed_ms: 15000, cost_bb: null, correct: false, reference: null,
    best: { action: "call", amount: null }, options: [{ action: "call", amount: null, frequency: 0.8 }],
  } };
  const markup = renderToStaticMarkup(createElement(AttemptReview, { attempt }));
  assert.match(markup, /River call.*Time expired · 15\.0 s.*Cost unavailable/);
  assert.match(markup, /ace of spades.*Best action.*Call.*Solver mix Call 80%.*Opponent · Bet to 250/);
});
