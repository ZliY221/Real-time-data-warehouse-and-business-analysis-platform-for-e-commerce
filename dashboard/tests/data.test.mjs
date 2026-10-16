import test from "node:test";
import assert from "node:assert/strict";

import {
  anomalyReasonLabel,
  anomalyTypeLabel,
  apiErrorMessage,
  buildMetricQuery,
  buildContributionRows,
  buildDashboardShareQuery,
  createLocalRange,
  createComparisonPeriod,
  filterAssetHealth,
  getContributionContext,
  formatGrowthRate,
  formatInteger,
  formatLag,
  formatMoney,
  qualityPassRate,
  parseDashboardShareQuery,
  summarizeDashboardShareView,
  toApiTimestamp,
} from "../static/data.js";

test("anomaly codes have stable dashboard labels", () => {
  assert.equal(anomalyTypeLabel("rejected"), "拒绝事件");
  assert.equal(anomalyTypeLabel("late"), "迟到事件");
  assert.equal(anomalyReasonLabel("malformed_json"), "JSON 解析失败");
  assert.equal(anomalyReasonLabel("custom_reason"), "custom_reason");
});

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

test("comparison helpers derive the prior equal period and readable growth", () => {
  const period = createComparisonPeriod({
    start: "2026-10-15T08:00:00Z",
    end: "2026-10-15T10:00:00Z",
  });
  assert.equal(period.baseline_start, "2026-10-15T06:00:00.000Z");
  assert.equal(period.baseline_end, "2026-10-15T08:00:00.000Z");
  const day = createComparisonPeriod({
    start: "2026-10-15T08:00:00Z", end: "2026-10-15T10:00:00Z",
  }, "day");
  assert.equal(day.baseline_start, "2026-10-14T08:00:00.000Z");
  const week = createComparisonPeriod({
    start: "2026-10-15T08:00:00Z", end: "2026-10-15T10:00:00Z",
  }, "week");
  assert.equal(week.baseline_end, "2026-10-08T10:00:00.000Z");
  assert.equal(formatGrowthRate(0.125), "+12.5%");
  assert.equal(formatGrowthRate(-0.04), "-4.0%");
  assert.equal(formatGrowthRate(null), "暂无基准");
});

test("contribution rows merge missing dimensions and rank absolute GMV change", () => {
  const rows = buildContributionRows(
    [{ name: "north", gmv: "150.00" }, { name: "east", gmv: "80.00" }],
    [{ name: "north", gmv: "100.00" }, { name: "south", gmv: "120.00" }],
  );
  assert.deepEqual(rows.map(row => [row.name, row.deltaGmv]), [
    ["south", -120], ["north", 50], ["east", 80],
  ].sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])));
});

test("contribution rows normalize non-finite GMV values", () => {
  const rows = buildContributionRows(
    [{ name: "north", gmv: "Infinity" }, { name: "east", gmv: "invalid" }],
    [{ name: "north", gmv: "10.00" }],
  );
  assert.deepEqual(rows.map(row => [row.name, row.currentGmv, row.deltaGmv]), [
    ["north", 0, -10], ["east", 0, 0],
  ]);
  assert.ok(rows.every(row => Number.isFinite(row.deltaGmv)));
});

test("contribution context identifies an active drilldown", () => {
  assert.deepEqual(getContributionContext("region", { region: "north" }), { dimension: "region", name: "north" });
  assert.equal(getContributionContext("channel", { channel: "" }), null);
  assert.throws(() => getContributionContext("unknown", {}), /unsupported contribution dimension/);
});

test("dashboard share query restores filters and interaction settings", () => {
  const now = new Date("2026-10-16T00:00:00Z");
  const query = buildDashboardShareQuery({
    filters: {
      start: "2026-10-15T08:00", end: "2026-10-15T10:00",
      region: "华北&重点", channel: "web",
    },
    comparisonMode: "day", comparisonDimension: "channel", refreshSeconds: 15,
  }, now);
  assert.deepEqual(parseDashboardShareQuery(query, now), {
    filters: {
      start: "2026-10-15T08:00", end: "2026-10-15T10:00",
      region: "华北&重点", channel: "web",
    },
    comparisonMode: "day", comparisonDimension: "channel", refreshSeconds: 15,
  });
  assert.equal(parseDashboardShareQuery("?view=1&start=invalid&end=invalid"), null);
  assert.equal(parseDashboardShareQuery("?start=2026-10-15T08:00&end=2026-10-15T10:00"), null);
  assert.equal(parseDashboardShareQuery(query, new Date("2026-10-23T00:00:01Z")), null);
  assert.equal(query.get("expires"), "2026-10-23T00:00:00.000Z");
});

test("dashboard share view has a concise handoff summary", () => {
  const summary = summarizeDashboardShareView({
    filters: { start: "2026-10-15T08:00", end: "2026-10-15T10:00", region: "华北", channel: "web" },
    comparisonMode: "day",
  });
  assert.equal(summary, "2026-10-15T08:00 至 2026-10-15T10:00 · 华北 / web · 昨日同期");
  assert.throws(() => summarizeDashboardShareView({ filters: {} }), /时间范围/);
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

test("asset health filters combine status and owner", () => {
  const items = [
    { asset_id: "a", status: "fresh", owner: "warehouse", priority_score: 0 },
    { asset_id: "b", status: "stale", owner: "warehouse", priority_score: 121 },
    { asset_id: "c", status: "stale", owner: "api", priority_score: 140 },
  ];
  assert.deepEqual(
    filterAssetHealth(items, { status: "stale", owner: "warehouse" }).map((item) => item.asset_id),
    ["b"],
  );
  assert.equal(filterAssetHealth(items, { owner: "api" }).length, 1);
  assert.deepEqual(filterAssetHealth(items).map((item) => item.asset_id), ["c", "b", "a"]);
  assert.deepEqual(filterAssetHealth(null), []);
});
