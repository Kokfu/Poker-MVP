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

test("Coach publishes quick advice only while the matching full request is pending", async (t) => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false } });
  t.after(() => vite.close());
  const { requestCoachAdvice } = await vite.ssrLoadModule("/src/Coach.tsx");
  const preview = { status: "quick", advice: { action: "check" } };
  const complete = { status: "hero_to_act", advice: { action: "bet", amount: 175 } };
  const flush = () => new Promise(setImmediate);

  await t.test("an early preview is followed by the full response", async (scenario) => {
    let finish;
    const full = new Promise((resolve) => { finish = resolve; });
    scenario.mock.method(globalThis, "fetch", (url) => url.endsWith("/quick") ? Promise.resolve(Response.json(preview)) : full);
    const observed = [];
    const request = requestCoachAdvice({}, (value) => observed.push(value));
    await flush();
    assert.deepEqual(observed, [preview]);
    finish(Response.json(complete));
    assert.deepEqual(await request, complete);
  });

  await t.test("a late preview cannot overwrite full advice", async (scenario) => {
    let finish;
    const quick = new Promise((resolve) => { finish = resolve; });
    scenario.mock.method(globalThis, "fetch", (url) => url.endsWith("/quick") ? quick : Promise.resolve(Response.json(complete)));
    const observed = [];
    assert.deepEqual(await requestCoachAdvice({}, (value) => observed.push(value)), complete);
    finish(Response.json(preview));
    await flush();
    assert.deepEqual(observed, []);
  });

  await t.test("aborting suppresses a stale preview and a preview failure leaves full advice available", async (scenario) => {
    const controller = new AbortController();
    const observed = [];
    const fetch = scenario.mock.method(globalThis, "fetch", (url) => {
      return Promise.resolve(Response.json(url.endsWith("/quick") ? preview : complete));
    });
    const obsolete = requestCoachAdvice({ signal: controller.signal }, (value) => observed.push(value));
    controller.abort();
    await obsolete;
    await flush();
    assert.deepEqual(observed, []);

    fetch.mock.mockImplementation((url) => url.endsWith("/quick")
      ? Promise.reject(new Error("preview failed"))
      : Promise.resolve(Response.json(complete)));
    assert.deepEqual(await requestCoachAdvice({}, (value) => observed.push(value)), complete);
    assert.deepEqual(observed, []);
  });
});
