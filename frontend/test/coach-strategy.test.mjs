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

test("Coach selects the newest same-kind villain size within the current total limits", async (t) => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false } });
  t.after(() => vite.close());
  const { recentVillainSize } = await vite.ssrLoadModule("/src/Coach.tsx");
  const state = {
    legal_actions: ["raise"], minimum_target: 400, maximum_target: 2500,
    villain_stack: 2400, hero_stack: 1300, to_call: 100,
  };
  const history = [
    { spot: { big_blind: 100, actions: [
      { actor: "villain", action: "raise", amount: 375 },
      { actor: "villain", action: "raise", amount: 1700 },
      { actor: "hero", action: "raise", amount: 425 },
    ] } },
    { spot: { big_blind: 100, actions: [{ actor: "villain", action: "raise", amount: 500 }] } },
  ];
  assert.equal(recentVillainSize(history, "raise", state, 200), 750);
  assert.equal(recentVillainSize(history, "raise", state, 100), 500);
  assert.equal(recentVillainSize(history, "bet", state, 100), undefined);
});
