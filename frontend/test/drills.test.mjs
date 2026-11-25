import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

test("drills render accessible public cards and ordered street-total actions", async (t) => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false } });
  t.after(() => vite.close());
  const { DrillCards, DrillHistory } = await vite.ssrLoadModule("/src/Drills.tsx");

  const cards = renderToStaticMarkup(createElement(DrillCards, { label: "Your cards", cards: ["As", "Th"] }));
  assert.match(cards, /aria-label="ace of spades"/);
  assert.match(cards, /aria-label="ten of hearts"/);
  const empty = renderToStaticMarkup(createElement(DrillCards, { label: "Board", cards: [] }));
  assert.match(empty, /Preflop/);

  const history = renderToStaticMarkup(createElement(DrillHistory, { history: [
    { street: "preflop", actor: "hero", action: "raise", amount: 250 },
    { street: "preflop", actor: "villain", action: "call", amount: 250 },
    { street: "flop", actor: "villain", action: "check", amount: null },
  ] }));
  assert.match(history, /preflop.*You · Raise to 250.*preflop.*Opponent · Call to 250.*flop.*Opponent · Check/);
});
