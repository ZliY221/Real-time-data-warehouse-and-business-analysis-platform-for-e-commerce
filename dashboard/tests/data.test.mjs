import test from "node:test";
import assert from "node:assert/strict";

import {
  apiErrorMessage,
  buildMetricQuery,
  createLocalRange,
  formatInteger,
  formatLag,
  formatMoney,
  qualityPassRate,
  toApiTimestamp,
} from "../static/data.js";

test("money formatting preserves an exact decimal string", () => {
  assert.equal(formatMoney("123456789012345.60"), "¥123,456,789,012,345.60");
  assert.equal(formatMoney("8"), "¥8.00");
  assert.equal(formatMoney("invalid"), "—");
});

test("integer formatting supports values outside JavaScript safe integer range", () => {
  assert.equal(formatInteger("9007199254740993"), "9,007,199,254,740,993");
});

test("metric query encodes values and omits blank optional filters", () => {
  const query = buildMetricQuery(
    {
      start: "2026-10-03T00:00:00Z",
      end: "2026-10-04T00:00:00Z",
      region: "辽宁&x=1",
      channel: "",
    },
    { bucket: "auto", limit: 12 },
  );

  assert.equal(query.get("region"), "辽宁&x=1");
  assert.equal(query.has("channel"), false);
  assert.equal(query.get("bucket"), "auto");
  assert.equal(query.get("limit"), "12");
});

test("timestamps and quick ranges are deterministic for an injected clock", () => {
  assert.equal(
    toApiTimestamp("2026-10-03T00:00:00Z"),
    "2026-10-03T00:00:00.000Z",
  );
  const now = new Date("2026-10-03T08:00:00Z");
  const range = createLocalRange(6, now);
  assert.equal(
    new Date(range.end).getTime() - new Date(range.start).getTime(),
    21_600_000,
  );
});

test("lag and API errors provide clear user-facing states", () => {
  assert.equal(
    formatLag("2026-10-03T07:58:30Z", new Date("2026-10-03T08:00:00Z")),
    "1 分钟前",
  );
  assert.match(
    apiErrorMessage(503, { detail: { code: "analytics_store_unavailable" } }),
    /ClickHouse/,
  );
  assert.equal(
    apiErrorMessage(422, { detail: "时间范围错误" }),
    "时间范围错误",
  );
});

test("invalid timestamps are rejected before sending a request", () => {
  assert.throws(() => toApiTimestamp("not-a-time"), /有效/);
});

test("quality pass rate handles mixed and empty history", () => {
  assert.equal(qualityPassRate([{ passed: true }, { passed: false }]), 0.5);
  assert.equal(qualityPassRate([{ passed: true }, { passed: true }]), 1);
  assert.equal(qualityPassRate([]), null);
});

test("quality history errors have a focused recovery message", () => {
  assert.match(
    apiErrorMessage(503, { detail: { code: "quality_history_unavailable" } }),
    /SQLite/,
  );
});
