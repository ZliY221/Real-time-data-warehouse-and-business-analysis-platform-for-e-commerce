import test from "node:test";
import assert from "node:assert/strict";
import { normalizeSavedViews, parseSavedViews, removeSavedView, upsertSavedView } from "../static/saved_views.js";

const view = { id: "morning", name: " 早间经营 ", quickRangeHours: 6, comparisonMode: "week", filters: { start: "2026-10-15T00:00", end: "2026-10-15T06:00", region: "north", channel: "app" }, refreshSeconds: 15 };

test("saved views are normalized and bounded", () => {
  const [normalized] = normalizeSavedViews([view]);
  assert.equal(normalized.name, "早间经营");
  assert.equal(normalized.refreshSeconds, 15);
  assert.equal(normalized.comparisonMode, "week");
  assert.deepEqual(normalizeSavedViews(null), []);
  assert.deepEqual(parseSavedViews("not-json"), []);
});

test("saved views can be replaced and removed", () => {
  const saved = upsertSavedView([], view);
  const replaced = upsertSavedView(saved, { ...view, name: "早间复盘" });
  assert.equal(replaced.length, 1);
  assert.equal(replaced[0].name, "早间复盘");
  assert.deepEqual(removeSavedView(replaced, "morning"), []);
});
