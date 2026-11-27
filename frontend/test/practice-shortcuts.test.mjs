import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "vite";

test("practice keyboard shortcuts use only legal actions and preserve focused button Enter", async (t) => {
  const vite = await createServer({ server: { middlewareMode: true, ws: false } });
  t.after(() => vite.close());
  const { practiceShortcut } = await vite.ssrLoadModule("/src/PracticeTable.tsx");
  const facing = ["fold", "call", "raise", "all_in"];
  assert.deepEqual(practiceShortcut("f", false, false, facing, false), { action: "fold" });
  assert.deepEqual(practiceShortcut("C", false, false, facing, false), { action: "call" });
  assert.deepEqual(practiceShortcut("b", false, false, facing, false), { action: "raise" });
  assert.deepEqual(practiceShortcut("A", false, false, facing, false), { action: "all_in" });
  assert.deepEqual(practiceShortcut("c", false, false, ["check", "bet"], false), { action: "check" });
  assert.deepEqual(practiceShortcut("B", false, false, ["check", "bet"], false), { action: "bet" });
  assert.equal(practiceShortcut("b", false, false, ["check"], false), undefined);
  assert.equal(practiceShortcut("n", false, false, facing, false), undefined);
  assert.deepEqual(practiceShortcut("N", false, true, [], false), { action: "next" });
  assert.equal(practiceShortcut("f", false, true, facing, false), undefined);
  assert.deepEqual(practiceShortcut("3", false, false, facing, false), { digit: "3" });
  assert.equal(practiceShortcut("3", false, false, ["check"], false), undefined);
  assert.equal(practiceShortcut("Enter", false, false, facing, false), undefined);
  assert.deepEqual(practiceShortcut("Enter", false, false, facing, true), { action: "raise" });
  assert.equal(practiceShortcut("Enter", true, false, facing, true), undefined);
});
