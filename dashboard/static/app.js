import {
  anomalyReasonLabel,
  anomalyTypeLabel,
  apiErrorMessage,
  buildContributionRows,
  buildMetricQuery,
  createLocalRange,
  createComparisonPeriod,
  filterAssetHealth,
  formatInteger,
  formatLag,
  formatGrowthRate,
  formatMoney,
  formatTimestamp,
  qualityPassRate,
} from "./data.js";
import { parseSavedViews, removeSavedView, upsertSavedView } from "./saved_views.js";

const elements = {
  body: document.body,
  form: document.querySelector("#filter-form"),
  start: document.querySelector("#start-time"),
  end: document.querySelector("#end-time"),
  region: document.querySelector("#region-filter"),
  channel: document.querySelector("#channel-filter"),
  comparisonMode: document.querySelector("#comparison-mode"),
  comparisonDimension: document.querySelector("#comparison-dimension"),
  refresh: document.querySelector("#refresh-button"),
  reset: document.querySelector("#reset-button"),
  retry: document.querySelector("#retry-button"),
  autoRefreshInterval: document.querySelector("#auto-refresh-interval"),
  autoRefreshCountdown: document.querySelector("#auto-refresh-countdown"),
  liveRefreshToggle: document.querySelector("#live-refresh-toggle"),
  savedView: document.querySelector("#saved-view"),
  savedViewName: document.querySelector("#saved-view-name"),
  saveView: document.querySelector("#save-view-button"),
  deleteView: document.querySelector("#delete-view-button"),
  quickRanges: [...document.querySelectorAll("[data-hours]")],
  status: document.querySelector("#connection-status"),
  statusText: document.querySelector("#connection-status-text"),
  errorBanner: document.querySelector("#error-banner"),
  errorMessage: document.querySelector("#error-message"),
  previewBanner: document.querySelector("#preview-banner"),
  kpiGmv: document.querySelector("#kpi-gmv"),
  kpiOrders: document.querySelector("#kpi-orders"),
  kpiAov: document.querySelector("#kpi-aov"),
  kpiLag: document.querySelector("#kpi-lag"),
  kpiUpdatedAt: document.querySelector("#kpi-updated-at"),
  comparisonPeriod: document.querySelector("#comparison-period"),
  comparisonOrders: document.querySelector("#comparison-orders"),
  comparisonGmv: document.querySelector("#comparison-gmv"),
  comparisonAov: document.querySelector("#comparison-aov"),
  comparisonContributions: document.querySelector("#comparison-contributions"),
  trendChart: document.querySelector("#trend-chart"),
  regionChart: document.querySelector("#region-chart"),
  channelChart: document.querySelector("#channel-chart"),
  qualityTrendChart: document.querySelector("#quality-trend-chart"),
  trendEmpty: document.querySelector("#trend-empty"),
  qualityTrendEmpty: document.querySelector("#quality-trend-empty"),
  trendSubtitle: document.querySelector("#trend-subtitle"),
  bucketBadge: document.querySelector("#bucket-badge"),
  recentTable: document.querySelector("#recent-table-body"),
  regionTable: document.querySelector("#region-table-body"),
  channelTable: document.querySelector("#channel-table-body"),
  lastRefreshed: document.querySelector("#last-refreshed"),
  qualityRuleBadge: document.querySelector("#quality-rule-badge"),
  qualityLatestStatus: document.querySelector("#quality-latest-status"),
  qualityLatestTime: document.querySelector("#quality-latest-time"),
  qualityPassRate: document.querySelector("#quality-pass-rate"),
  qualityFailedRules: document.querySelector("#quality-failed-rules"),
  qualityRunCount: document.querySelector("#quality-run-count"),
  qualityHistoryNote: document.querySelector("#quality-history-note"),
  qualityHistoryTable: document.querySelector("#quality-history-table-body"),
  anomalyStatusBadge: document.querySelector("#anomaly-status-badge"),
  anomalyTotalCount: document.querySelector("#anomaly-total-count"),
  anomalyRejectedCount: document.querySelector("#anomaly-rejected-count"),
  anomalyLateCount: document.querySelector("#anomaly-late-count"),
  anomalyGroupCount: document.querySelector("#anomaly-group-count"),
  anomalyChart: document.querySelector("#anomaly-chart"),
  anomalyEmpty: document.querySelector("#anomaly-empty"),
  anomalyTableNote: document.querySelector("#anomaly-table-note"),
  anomalyTable: document.querySelector("#anomaly-table-body"),
  assetStatusBadge: document.querySelector("#asset-status-badge"),
  assetMonitoredCount: document.querySelector("#asset-monitored-count"),
  assetFreshCount: document.querySelector("#asset-fresh-count"),
  assetIssueCount: document.querySelector("#asset-issue-count"),
  assetImpactCount: document.querySelector("#asset-impact-count"),
  assetStatusFilter: document.querySelector("#asset-status-filter"),
  assetOwnerFilter: document.querySelector("#asset-owner-filter"),
  assetTableNote: document.querySelector("#asset-table-note"),
  assetTable: document.querySelector("#asset-health-table-body"),
  liveStatus: document.querySelector("#screen-reader-status"),
};

const reducedMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)",
).matches;
const darkMode = window.matchMedia("(prefers-color-scheme: dark)").matches;
const charts = {};
const dimensionOptions = { regions: new Set(), channels: new Set() };
const runtimeState = {
  dataMode: "clickhouse",
  assetHealthItems: [],
  quickRangeHours: 24,
  refreshTimer: undefined,
  countdownTimer: undefined,
  autoRefreshSeconds: 5,
  previousAutoRefreshSeconds: 5,
  nextRefreshAt: 0,
  refreshing: false,
  savedViews: parseSavedViews(localStorage.getItem("commerce.savedViews")),
};

function renderSavedViews() {
  const selected = elements.savedView.value;
  elements.savedView.replaceChildren(new Option("选择已保存视图", ""), ...runtimeState.savedViews.map(view => new Option(view.name, view.id)));
  elements.savedView.value = runtimeState.savedViews.some(view => view.id === selected) ? selected : "";
  elements.deleteView.disabled = !elements.savedView.value;
  localStorage.setItem("commerce.savedViews", JSON.stringify(runtimeState.savedViews));
}

function applySavedView(view) {
  if (view.quickRangeHours) setQuickRange(view.quickRangeHours, false);
  else {
    runtimeState.quickRangeHours = null;
    elements.start.value = view.filters.start;
    elements.end.value = view.filters.end;
    for (const button of elements.quickRanges) button.classList.remove("is-active");
  }
  elements.region.value = view.filters.region;
  elements.channel.value = view.filters.channel;
  elements.comparisonMode.value = view.comparisonMode;
  elements.comparisonDimension.value = view.comparisonDimension;
  setAutoRefresh(view.refreshSeconds);
  void refreshDashboard();
}

function cssToken(name) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

function initializeCharts() {
  if (!window.echarts) {
    throw new Error("图表组件加载失败，请检查网络连接后刷新页面。");
  }

  const theme = darkMode ? "dark" : undefined;
  charts.trend = window.echarts.init(elements.trendChart, theme, {
    renderer: "canvas",
  });
  charts.region = window.echarts.init(elements.regionChart, theme, {
    renderer: "canvas",
  });
  charts.channel = window.echarts.init(elements.channelChart, theme, {
    renderer: "canvas",
  });
  charts.quality = window.echarts.init(elements.qualityTrendChart, theme, {
    renderer: "canvas",
  });
  charts.anomaly = window.echarts.init(elements.anomalyChart, theme, {
    renderer: "canvas",
  });

  const observer = new ResizeObserver(() => {
    for (const chart of Object.values(charts)) chart.resize();
  });
  observer.observe(document.querySelector(".shell"));

  window.addEventListener("beforeunload", () => {
    observer.disconnect();
    for (const chart of Object.values(charts)) chart.dispose();
  });
}

function setConnectionState(state, text) {
  elements.status.className = `status-chip status-chip--${state}`;
  elements.statusText.textContent = text;
}

function setLoading(loading) {
  elements.body.classList.toggle("is-loading", loading);
  elements.refresh.disabled = loading;
  elements.reset.disabled = loading;
  elements.refresh.setAttribute("aria-busy", String(loading));
  if (loading) {
    setConnectionState("pending", "正在刷新数据");
    for (const chart of Object.values(charts)) {
      chart.showLoading("default", {
        text: "正在读取指标",
        color: cssToken("--color-primary"),
        textColor: cssToken("--color-text-muted"),
        maskColor: darkMode
          ? "rgba(17, 27, 45, 0.72)"
          : "rgba(255, 255, 255, 0.72)",
      });
    }
  } else {
    for (const chart of Object.values(charts)) chart.hideLoading();
  }
}

function setQuickRange(hours, refresh = true) {
  runtimeState.quickRangeHours = hours;
  const range = createLocalRange(hours);
  elements.start.value = range.start;
  elements.end.value = range.end;
  for (const button of elements.quickRanges) {
    button.classList.toggle(
      "is-active",
      Number(button.dataset.hours) === hours,
    );
    button.setAttribute(
      "aria-pressed",
      String(Number(button.dataset.hours) === hours),
    );
  }
  if (refresh) void refreshDashboard();
}

function currentFilters() {
  return {
    start: elements.start.value,
    end: elements.end.value,
    region: elements.region.value,
    channel: elements.channel.value,
  };
}

async function fetchJson(path, query) {
  const response = await fetch(`${path}?${query.toString()}`, {
    headers: { Accept: "application/json" },
  });
  const payload = await response.json().catch(() => null);
  runtimeState.dataMode =
    response.headers.get("x-data-mode") || runtimeState.dataMode;
  if (!response.ok) {
    throw new Error(apiErrorMessage(response.status, payload));
  }
  return payload;
}

function queryFor(filters, extras) {
  return buildMetricQuery(filters, extras);
}

function displayDimension(value) {
  const labels = {
    app: "移动端 App",
    web: "网页端",
    mini_program: "小程序",
    direct: "直接访问",
  };
  return labels[value] || value;
}

function renderSummary(summary) {
  elements.kpiGmv.textContent = formatMoney(summary.gmv);
  elements.kpiOrders.textContent = formatInteger(summary.order_count);
  elements.kpiAov.textContent = formatMoney(summary.average_order_value);
  elements.kpiLag.textContent = formatLag(summary.latest_processed_at);
  elements.kpiUpdatedAt.textContent = summary.latest_processed_at
    ? `最近处理：${formatTimestamp(summary.latest_processed_at, { seconds: true })}`
    : "筛选范围内暂无处理记录";
}

function renderComparison(comparison) {
  const metrics = [
    [elements.comparisonOrders, comparison.delta.order_count_rate],
    [elements.comparisonGmv, comparison.delta.gmv_rate],
    [elements.comparisonAov, comparison.delta.average_order_value_rate],
  ];
  for (const [element, rate] of metrics) {
    element.textContent = formatGrowthRate(rate);
    element.classList.toggle("comparison-card__value--up", Number(rate) > 0);
    element.classList.toggle("comparison-card__value--down", Number(rate) < 0);
  }
  const baseline = comparison.baseline.filters;
  const modeLabel = elements.comparisonMode.selectedOptions[0]?.textContent || "对比区间";
  elements.comparisonPeriod.textContent = `${modeLabel} · ${formatTimestamp(baseline.start)} 至 ${formatTimestamp(baseline.end)}`;
}

function renderContributions(currentItems, baselineItems) {
  const rows = buildContributionRows(currentItems, baselineItems);
  elements.comparisonContributions.innerHTML = rows.length ? rows.map(row => `
    <li><span>${displayDimension(row.name)}</span><strong class="${row.deltaGmv >= 0 ? "is-positive" : "is-negative"}">${row.deltaGmv > 0 ? "+" : ""}${formatMoney(String(row.deltaGmv))}</strong></li>
  `).join("") : "<li><span>当前维度暂无可对比数据</span></li>";
}

function baseChartOption(description) {
  return {
    backgroundColor: "transparent",
    animation: !reducedMotion,
    animationDuration: reducedMotion ? 0 : 260,
    textStyle: {
      color: cssToken("--color-text"),
      fontFamily: '"Fira Sans", "Segoe UI", "Microsoft YaHei", sans-serif',
    },
    aria: {
      enabled: true,
      show: true,
      description,
      decal: { show: true },
    },
  };
}

function renderTrend(response) {
  const items = response.items;
  const hasData = items.length > 0;
  elements.trendChart.hidden = !hasData;
  elements.trendEmpty.hidden = hasData;
  elements.bucketBadge.textContent = `时间桶 ${response.bucket}`;
  elements.trendSubtitle.textContent = hasData
    ? `共 ${items.length} 个时间点，时间桶 ${response.bucket}。可滚轮缩放查看局部。`
    : "系统会根据时间范围自动选择聚合粒度。";

  if (!hasData) {
    charts.trend.clear();
    return;
  }

  charts.trend.resize();

  charts.trend.setOption(
    {
      ...baseChartOption("筛选时段内成交额和有效订单量随时间变化的组合图。"),
      color: [cssToken("--chart-gmv"), cssToken("--chart-orders")],
      grid: { left: 58, right: 58, top: 46, bottom: 55, containLabel: false },
      legend: {
        top: 4,
        right: 4,
        textStyle: { color: cssToken("--color-text-muted") },
        data: ["成交额", "订单量"],
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        renderMode: "richText",
        formatter: (parameters) => {
          const [gmv, orders] = parameters;
          return [
            gmv?.axisValue || "",
            `成交额  ${formatMoney(String(gmv?.value ?? 0))}`,
            `订单量  ${formatInteger(orders?.value ?? 0)}`,
          ].join("\n");
        },
      },
      xAxis: {
        type: "category",
        boundaryGap: true,
        data: items.map((item) => formatTimestamp(item.bucket_start)),
        axisLabel: { color: cssToken("--color-text-muted"), hideOverlap: true },
        axisLine: { lineStyle: { color: cssToken("--chart-grid") } },
      },
      yAxis: [
        {
          type: "value",
          name: "成交额（元）",
          nameTextStyle: { color: cssToken("--color-text-muted") },
          axisLabel: { color: cssToken("--color-text-muted") },
          splitLine: {
            lineStyle: { color: cssToken("--chart-grid"), type: "dashed" },
          },
        },
        {
          type: "value",
          name: "订单量",
          nameTextStyle: { color: cssToken("--color-text-muted") },
          axisLabel: { color: cssToken("--color-text-muted"), precision: 0 },
          splitLine: { show: false },
        },
      ],
      dataZoom: [{ type: "inside", filterMode: "none" }],
      series: [
        {
          name: "成交额",
          type: "line",
          yAxisIndex: 0,
          smooth: 0.18,
          showSymbol: items.length < 80,
          symbol: "circle",
          symbolSize: 6,
          lineStyle: { width: 2.5 },
          areaStyle: { opacity: 0.1 },
          data: items.map((item) => item.gmv),
        },
        {
          name: "订单量",
          type: "bar",
          yAxisIndex: 1,
          barMaxWidth: 16,
          itemStyle: { borderRadius: [4, 4, 0, 0], opacity: 0.72 },
          data: items.map((item) => item.order_count),
        },
      ],
    },
    { notMerge: true },
  );
}

function renderRegion(items) {
  const ordered = [...items].reverse();
  charts.region.setOption(
    {
      ...baseChartOption("各地区成交额的横向柱状排行。"),
      color: [cssToken("--chart-gmv")],
      grid: { left: 12, right: 30, top: 12, bottom: 18, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        renderMode: "richText",
        valueFormatter: (value) => formatMoney(String(value)),
      },
      xAxis: {
        type: "value",
        axisLabel: { color: cssToken("--color-text-muted") },
        splitLine: {
          lineStyle: { color: cssToken("--chart-grid"), type: "dashed" },
        },
      },
      yAxis: {
        type: "category",
        data: ordered.map((item) => displayDimension(item.name)),
        axisLabel: {
          color: cssToken("--color-text-muted"),
          width: 90,
          overflow: "truncate",
        },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          name: "成交额",
          type: "bar",
          barMaxWidth: 24,
          label: {
            show: true,
            position: "right",
            color: cssToken("--color-text-muted"),
            formatter: ({ value }) => formatMoney(String(value)),
          },
          itemStyle: { borderRadius: [0, 5, 5, 0] },
          data: ordered.map((item) => item.gmv),
        },
      ],
    },
    { notMerge: true },
  );
  renderBreakdownTable(elements.regionTable, items);
}

function renderChannel(items) {
  charts.channel.setOption(
    {
      ...baseChartOption("各渠道成交额占比的环形图，并使用纹理辅助区分颜色。"),
      color: ["#2563eb", "#d97706", "#0f766e", "#7c3aed", "#be123c", "#4f46e5"],
      tooltip: {
        trigger: "item",
        renderMode: "richText",
        formatter: ({ name, value, percent }) =>
          `${name}\n${formatMoney(String(value))} · ${percent}%`,
      },
      legend: {
        type: "scroll",
        bottom: 0,
        textStyle: { color: cssToken("--color-text-muted") },
      },
      series: [
        {
          name: "渠道成交额",
          type: "pie",
          radius: ["48%", "72%"],
          center: ["50%", "44%"],
          avoidLabelOverlap: true,
          itemStyle: {
            borderColor: cssToken("--color-surface"),
            borderWidth: 3,
          },
          label: {
            color: cssToken("--color-text-muted"),
            formatter: "{b}\n{d}%",
          },
          data: items.map((item) => ({
            name: displayDimension(item.name),
            value: item.gmv,
          })),
        },
      ],
    },
    { notMerge: true },
  );
  renderBreakdownTable(elements.channelTable, items);
}

function appendCell(row, text) {
  const cell = document.createElement("td");
  cell.textContent = text;
  row.append(cell);
}

function renderBreakdownTable(target, items) {
  const rows = items.map((item) => {
    const row = document.createElement("tr");
    appendCell(row, displayDimension(item.name));
    appendCell(row, formatInteger(item.order_count));
    appendCell(row, formatMoney(item.gmv));
    return row;
  });
  if (rows.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 3;
    cell.className = "table-message";
    cell.textContent = "当前筛选范围暂无数据";
    row.append(cell);
    rows.push(row);
  }
  target.replaceChildren(...rows);
}

function renderRecent(items) {
  const rows = items.map((item) => {
    const row = document.createElement("tr");
    appendCell(row, formatTimestamp(item.window_start, { seconds: true }));
    appendCell(row, displayDimension(item.region));
    appendCell(row, displayDimension(item.channel));
    appendCell(row, formatInteger(item.order_count));
    appendCell(row, formatMoney(item.gmv));
    appendCell(row, formatMoney(item.average_order_value));
    return row;
  });
  if (rows.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "table-message";
    cell.textContent = "当前筛选范围暂无分钟指标";
    row.append(cell);
    rows.push(row);
  }
  elements.recentTable.replaceChildren(...rows);
}

function appendQualityStatus(row, passed) {
  const cell = document.createElement("td");
  const status = document.createElement("span");
  status.className = `quality-pill quality-pill--${passed ? "pass" : "fail"}`;
  status.textContent = passed ? "通过" : "失败";
  cell.append(status);
  row.append(cell);
}

function renderQualityRuns(response) {
  const items = response.items;
  const latest = items[0];
  const passRate = qualityPassRate(items);
  elements.qualityRunCount.textContent = formatInteger(response.count);
  elements.qualityPassRate.textContent =
    passRate === null ? "—" : `${Math.round(passRate * 100)}%`;
  elements.qualityFailedRules.textContent = latest
    ? formatInteger(latest.failed_rules)
    : "—";
  elements.qualityLatestStatus.textContent = latest
    ? latest.passed
      ? "通过"
      : "失败"
    : "暂无";
  elements.qualityLatestStatus.className = latest
    ? `quality-status quality-status--${latest.passed ? "pass" : "fail"}`
    : "quality-status";
  elements.qualityLatestTime.textContent = latest
    ? `运行于 ${formatTimestamp(latest.generated_at, { seconds: true })}`
    : "尚未写入质量检查记录";
  elements.qualityHistoryNote.textContent = items.length
    ? `已读取 ${items.length} 次 SQLite 历史摘要。`
    : "SQLite 历史库可用，但暂无运行记录。";

  const rows = items.map((item) => {
    const row = document.createElement("tr");
    appendCell(row, formatTimestamp(item.generated_at, { seconds: true }));
    appendQualityStatus(row, item.passed);
    appendCell(row, formatInteger(item.total_records));
    appendCell(row, formatInteger(item.failed_rules));
    appendCell(
      row,
      formatInteger(item.invalid_json_records + item.invalid_contract_records),
    );
    appendCell(row, formatInteger(item.duplicate_records));
    appendCell(row, formatInteger(item.late_records));
    return row;
  });
  if (rows.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.className = "table-message";
    cell.textContent = "暂无质量检查历史";
    row.append(cell);
    rows.push(row);
  }
  elements.qualityHistoryTable.replaceChildren(...rows);
}

function renderQualityTrend(response) {
  const items = response.items;
  const hasData = items.length > 0;
  elements.qualityTrendChart.hidden = !hasData;
  elements.qualityTrendEmpty.hidden = hasData;
  elements.qualityRuleBadge.textContent = `规则：${response.rule_id}`;
  if (!hasData) {
    charts.quality.clear();
    return;
  }

  charts.quality.resize();
  charts.quality.setOption(
    {
      ...baseChartOption("渠道分布漂移观测值与质量门禁阈值的时间趋势图。"),
      color: [cssToken("--chart-gmv"), cssToken("--color-warning")],
      grid: { left: 52, right: 22, top: 42, bottom: 45, containLabel: false },
      legend: {
        top: 0,
        right: 0,
        textStyle: { color: cssToken("--color-text-muted") },
        data: ["观测值", "门禁阈值"],
      },
      tooltip: {
        trigger: "axis",
        renderMode: "richText",
        valueFormatter: (value) => `${(Number(value) * 100).toFixed(1)}%`,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: items.map((item) => formatTimestamp(item.generated_at)),
        axisLabel: { color: cssToken("--color-text-muted"), hideOverlap: true },
        axisLine: { lineStyle: { color: cssToken("--chart-grid") } },
      },
      yAxis: {
        type: "value",
        min: 0,
        axisLabel: {
          color: cssToken("--color-text-muted"),
          formatter: (value) => `${Math.round(value * 100)}%`,
        },
        splitLine: {
          lineStyle: { color: cssToken("--chart-grid"), type: "dashed" },
        },
      },
      series: [
        {
          name: "观测值",
          type: "line",
          smooth: 0.16,
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2.5 },
          areaStyle: { opacity: 0.08 },
          data: items.map((item) => ({
            value: item.observed_value,
            itemStyle: {
              color: item.passed
                ? cssToken("--color-success")
                : cssToken("--color-danger"),
            },
          })),
        },
        {
          name: "门禁阈值",
          type: "line",
          symbol: "none",
          lineStyle: { width: 1.5, type: "dashed" },
          data: items.map((item) => item.threshold),
        },
      ],
    },
    { notMerge: true },
  );
}

function renderQualityFailure(error) {
  elements.qualityLatestStatus.textContent = "不可用";
  elements.qualityLatestStatus.className =
    "quality-status quality-status--fail";
  elements.qualityLatestTime.textContent = "等待质量历史恢复";
  elements.qualityPassRate.textContent = "—";
  elements.qualityFailedRules.textContent = "—";
  elements.qualityRunCount.textContent = "—";
  elements.qualityRuleBadge.textContent = "质量历史不可用";
  elements.qualityHistoryNote.textContent = error.message;
  elements.qualityHistoryTable.innerHTML =
    '<tr><td colspan="7" class="table-message">质量历史暂时不可用</td></tr>';
  elements.qualityTrendChart.hidden = true;
  elements.qualityTrendEmpty.hidden = false;
  charts.quality.clear();
}

function renderAnomalySummary(response) {
  const items = response.items;
  const hasData = items.length > 0;
  elements.anomalyTotalCount.textContent = formatInteger(response.total_count);
  elements.anomalyRejectedCount.textContent = formatInteger(
    response.rejected_count,
  );
  elements.anomalyLateCount.textContent = formatInteger(response.late_count);
  elements.anomalyGroupCount.textContent = formatInteger(response.count);
  elements.anomalyStatusBadge.textContent = hasData
    ? `${response.count} 个异常分组`
    : "当前范围无异常";
  elements.anomalyTableNote.textContent = hasData
    ? `已聚合 ${response.total_count} 条异常记录。`
    : "ClickHouse 异常汇总视图可用，当前范围无记录。";
  elements.anomalyChart.hidden = !hasData;
  elements.anomalyEmpty.hidden = hasData;

  const rows = items.map((item) => {
    const row = document.createElement("tr");
    appendCell(row, anomalyTypeLabel(item.anomaly_type));
    appendCell(row, anomalyReasonLabel(item.reason));
    appendCell(row, formatInteger(item.anomaly_count));
    appendCell(row, formatTimestamp(item.latest_at, { seconds: true }));
    return row;
  });
  if (!hasData) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "table-message";
    cell.textContent = "当前时间范围没有异常记录";
    row.append(cell);
    rows.push(row);
    charts.anomaly.clear();
  } else {
    charts.anomaly.resize();
    charts.anomaly.setOption(
      {
        ...baseChartOption("按异常类型和原因汇总的事件数量。"),
        color: [cssToken("--color-danger")],
        grid: { left: 28, right: 24, top: 20, bottom: 68, containLabel: true },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
        xAxis: {
          type: "category",
          data: items.map(
            (item) =>
              `${anomalyTypeLabel(item.anomaly_type)}\n${anomalyReasonLabel(item.reason)}`,
          ),
          axisLabel: {
            color: cssToken("--color-text-muted"),
            interval: 0,
            hideOverlap: true,
          },
          axisLine: { lineStyle: { color: cssToken("--chart-grid") } },
        },
        yAxis: {
          type: "value",
          minInterval: 1,
          axisLabel: { color: cssToken("--color-text-muted") },
          splitLine: {
            lineStyle: { color: cssToken("--chart-grid"), type: "dashed" },
          },
        },
        series: [
          {
            name: "异常数量",
            type: "bar",
            barMaxWidth: 42,
            data: items.map((item) => item.anomaly_count),
          },
        ],
      },
      { notMerge: true },
    );
  }
  elements.anomalyTable.replaceChildren(...rows);
}

function renderAnomalyFailure(error) {
  elements.anomalyStatusBadge.textContent = "异常汇总不可用";
  elements.anomalyTotalCount.textContent = "—";
  elements.anomalyRejectedCount.textContent = "—";
  elements.anomalyLateCount.textContent = "—";
  elements.anomalyGroupCount.textContent = "—";
  elements.anomalyTableNote.textContent = error.message;
  elements.anomalyTable.innerHTML =
    '<tr><td colspan="4" class="table-message">异常汇总暂时不可用</td></tr>';
  elements.anomalyChart.hidden = true;
  elements.anomalyEmpty.hidden = false;
  charts.anomaly.clear();
}

async function refreshAnomalies(filters) {
  try {
    const summary = await fetchJson(
      "/api/v1/anomalies/summary",
      queryFor(filters, { limit: 20 }),
    );
    renderAnomalySummary(summary);
  } catch (error) {
    renderAnomalyFailure(
      error instanceof Error ? error : new Error("异常汇总读取失败。"),
    );
  }
}

async function refreshQuality() {
  try {
    const [runs, trend] = await Promise.all([
      fetchJson("/api/v1/quality/runs", new URLSearchParams({ limit: "12" })),
      fetchJson(
        "/api/v1/quality/trend",
        new URLSearchParams({ rule_id: "channel-share-drift", limit: "50" }),
      ),
    ]);
    renderQualityRuns(runs);
    renderQualityTrend(trend);
  } catch (error) {
    renderQualityFailure(
      error instanceof Error ? error : new Error("质量历史读取失败。"),
    );
  }
}

function assetStatusLabel(status) {
  return { fresh: "正常", stale: "延迟", no_data: "无数据" }[status] ?? status;
}

function renderAssetHealthTable() {
  const items = filterAssetHealth(runtimeState.assetHealthItems, {
    status: elements.assetStatusFilter.value,
    owner: elements.assetOwnerFilter.value,
  });
  elements.assetTableNote.textContent = `显示 ${formatInteger(items.length)} / ${formatInteger(runtimeState.assetHealthItems.length)} 项`;
  elements.assetTable.innerHTML = items.length
    ? items.map((item) => `<tr>
        <td><strong>#${formatInteger(item.priority_rank)}</strong><br><small>${formatInteger(item.priority_score)} 分</small></td>
        <td>${item.asset_id}</td>
        <td>${item.owner}</td>
        <td><span class="quality-pill quality-pill--${item.status === "fresh" ? "pass" : "fail"}">${assetStatusLabel(item.status)}</span></td>
        <td>${item.lag_seconds === null ? "—" : `${formatInteger(item.lag_seconds)} 秒`}</td>
        <td>${item.impacted_assets.length ? item.impacted_assets.join("、") : "—"}</td>
      </tr>`).join("")
    : '<tr><td colspan="6" class="table-message">当前筛选条件下没有资产</td></tr>';
}

async function refreshAssetHealth() {
  try {
    const response = await fetchJson("/api/v1/operations/assets/health");
    const issueCount = response.status_counts.stale + response.status_counts.no_data;
    elements.assetStatusBadge.textContent = `链路状态：${assetStatusLabel(response.status)}`;
    elements.assetMonitoredCount.textContent = formatInteger(response.monitored_count);
    elements.assetFreshCount.textContent = formatInteger(response.status_counts.fresh);
    elements.assetIssueCount.textContent = formatInteger(issueCount);
    elements.assetImpactCount.textContent = formatInteger(response.impacted_assets.length);
    runtimeState.assetHealthItems = response.items;
    const selectedOwner = elements.assetOwnerFilter.value;
    const owners = [...new Set(response.items.map((item) => item.owner))].sort((left, right) => left.localeCompare(right, "zh-CN"));
    elements.assetOwnerFilter.replaceChildren(new Option("全部责任团队", ""), ...owners.map((owner) => new Option(owner, owner)));
    elements.assetOwnerFilter.value = owners.includes(selectedOwner) ? selectedOwner : "";
    renderAssetHealthTable();
  } catch (error) {
    elements.assetStatusBadge.textContent = "资产健康不可用";
    elements.assetMonitoredCount.textContent = "—";
    elements.assetFreshCount.textContent = "—";
    elements.assetIssueCount.textContent = "—";
    elements.assetImpactCount.textContent = "—";
    runtimeState.assetHealthItems = [];
    elements.assetTableNote.textContent = "筛选不可用";
    elements.assetTable.innerHTML = `<tr><td colspan="6" class="table-message">${error instanceof Error ? error.message : "资产健康读取失败"}</td></tr>`;
  }
}

elements.assetStatusFilter.addEventListener("change", renderAssetHealthTable);
elements.assetOwnerFilter.addEventListener("change", renderAssetHealthTable);

function syncSelect(select, values, emptyLabel) {
  const selected = select.value;
  const options = [new Option(emptyLabel, "")];
  for (const value of [...values].sort((left, right) =>
    left.localeCompare(right, "zh-CN"),
  )) {
    options.push(new Option(displayDimension(value), value));
  }
  select.replaceChildren(...options);
  select.value = selected;
}

function updateDimensionOptions(regions, channels) {
  for (const item of regions) dimensionOptions.regions.add(item.name);
  for (const item of channels) dimensionOptions.channels.add(item.name);
  syncSelect(elements.region, dimensionOptions.regions, "全部地区");
  syncSelect(elements.channel, dimensionOptions.channels, "全部渠道");
}

function renderFailure(error) {
  elements.errorMessage.textContent = error.message;
  elements.errorBanner.hidden = false;
  elements.kpiGmv.textContent = "—";
  elements.kpiOrders.textContent = "—";
  elements.kpiAov.textContent = "—";
  elements.kpiLag.textContent = "不可用";
  elements.kpiUpdatedAt.textContent = "等待分析存储恢复";
  elements.recentTable.innerHTML =
    '<tr><td colspan="6" class="table-message">数据服务暂时不可用</td></tr>';
  setConnectionState("error", "数据服务不可用");
  elements.liveStatus.textContent = `数据刷新失败：${error.message}`;
  for (const chart of [charts.trend, charts.region, charts.channel])
    chart.clear();
}

async function refreshDashboard() {
  if (runtimeState.refreshing) return;
  runtimeState.refreshing = true;
  if (runtimeState.quickRangeHours !== null) {
    setQuickRange(runtimeState.quickRangeHours, false);
  }
  elements.errorBanner.hidden = true;
  setLoading(true);
  const filters = currentFilters();
  const qualityRefresh = refreshQuality();
  const anomalyRefresh = refreshAnomalies(filters);
  const assetRefresh = refreshAssetHealth();
  try {
    const comparisonPeriod = createComparisonPeriod(filters, elements.comparisonMode.value);
    const contributionDimension = elements.comparisonDimension.value;
    const baselineFilters = {
      ...filters, start: comparisonPeriod.baseline_start, end: comparisonPeriod.baseline_end,
    };
    const [summary, comparison, timeSeries, regions, channels, recent, baselineBreakdown] = await Promise.all([
      fetchJson("/api/v1/metrics/summary", queryFor(filters)),
      fetchJson(
        "/api/v1/metrics/comparison",
        queryFor(filters, comparisonPeriod),
      ),
      fetchJson(
        "/api/v1/metrics/timeseries",
        queryFor(filters, { bucket: "auto" }),
      ),
      fetchJson(
        "/api/v1/metrics/breakdown",
        queryFor(filters, { dimension: "region", limit: 12 }),
      ),
      fetchJson(
        "/api/v1/metrics/breakdown",
        queryFor(filters, { dimension: "channel", limit: 12 }),
      ),
      fetchJson("/api/v1/metrics/minutes", queryFor(filters, { limit: 12 })),
      fetchJson(
        "/api/v1/metrics/breakdown",
        queryFor(baselineFilters, { dimension: contributionDimension, limit: 12 }),
      ),
    ]);

    renderSummary(summary);
    renderComparison(comparison);
    renderContributions(
      contributionDimension === "region" ? regions.items : channels.items,
      baselineBreakdown.items,
    );
    renderTrend(timeSeries);
    renderRegion(regions.items);
    renderChannel(channels.items);
    renderRecent(recent.items);
    updateDimensionOptions(regions.items, channels.items);
    elements.lastRefreshed.textContent = `页面刷新 ${formatTimestamp(new Date(), { seconds: true })}`;
    elements.previewBanner.hidden = runtimeState.dataMode !== "preview";
    if (runtimeState.dataMode === "preview") {
      setConnectionState("pending", "演示数据 · 非实时");
    } else {
      setConnectionState(
        "connected",
        summary.has_data ? "指标已更新" : "连接正常 · 暂无数据",
      );
    }
    elements.liveStatus.textContent = summary.has_data
      ? `数据刷新成功，共加载 ${timeSeries.count} 个时间点。`
      : "数据刷新成功，当前筛选范围没有指标。";
  } catch (error) {
    renderFailure(error instanceof Error ? error : new Error("发生未知错误。"));
  } finally {
    await Promise.all([qualityRefresh, anomalyRefresh, assetRefresh]);
    setLoading(false);
    runtimeState.refreshing = false;
  }
}

function setAutoRefresh(seconds) {
  if (runtimeState.refreshTimer) window.clearInterval(runtimeState.refreshTimer);
  if (runtimeState.countdownTimer) window.clearInterval(runtimeState.countdownTimer);
  runtimeState.refreshTimer = undefined;
  runtimeState.countdownTimer = undefined;
  runtimeState.autoRefreshSeconds = seconds;
  elements.autoRefreshInterval.value = String(seconds);
  if (seconds > 0) {
    runtimeState.previousAutoRefreshSeconds = seconds;
    runtimeState.nextRefreshAt = Date.now() + seconds * 1000;
    runtimeState.refreshTimer = window.setInterval(() => {
      runtimeState.nextRefreshAt = Date.now() + seconds * 1000;
      if (!document.hidden) void refreshDashboard();
    }, seconds * 1000);
    runtimeState.countdownTimer = window.setInterval(() => {
      const remaining = Math.max(0, Math.ceil((runtimeState.nextRefreshAt - Date.now()) / 1000));
      elements.autoRefreshCountdown.textContent = `${remaining} 秒后更新`;
    }, 1000);
    elements.liveRefreshToggle.textContent = "暂停实时刷新";
    elements.autoRefreshCountdown.textContent = `${seconds} 秒后更新`;
  } else {
    elements.liveRefreshToggle.textContent = "继续实时刷新";
    elements.autoRefreshCountdown.textContent = "实时刷新已暂停";
  }
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  runtimeState.quickRangeHours = null;
  for (const button of elements.quickRanges) {
    button.classList.remove("is-active");
    button.setAttribute("aria-pressed", "false");
  }
  void refreshDashboard();
});

elements.reset.addEventListener("click", () => {
  elements.region.value = "";
  elements.channel.value = "";
  elements.comparisonMode.value = "previous";
  elements.comparisonDimension.value = "region";
  setQuickRange(24);
});

elements.retry.addEventListener("click", () => void refreshDashboard());
elements.autoRefreshInterval.addEventListener("change", () => {
  setAutoRefresh(Number(elements.autoRefreshInterval.value));
  void refreshDashboard();
});
elements.comparisonMode.addEventListener("change", () => void refreshDashboard());
elements.comparisonDimension.addEventListener("change", () => void refreshDashboard());
elements.liveRefreshToggle.addEventListener("click", () => {
  const next = runtimeState.autoRefreshSeconds > 0 ? 0 : runtimeState.previousAutoRefreshSeconds;
  setAutoRefresh(next);
  if (next > 0) void refreshDashboard();
});
elements.saveView.addEventListener("click", () => {
  const name = elements.savedViewName.value.trim();
  const id = elements.savedView.value || `view-${Date.now()}`;
  try {
    runtimeState.savedViews = upsertSavedView(runtimeState.savedViews, {
      id, name, quickRangeHours: runtimeState.quickRangeHours,
      filters: currentFilters(), comparisonMode: elements.comparisonMode.value,
      comparisonDimension: elements.comparisonDimension.value,
      refreshSeconds: runtimeState.autoRefreshSeconds,
    });
    renderSavedViews(); elements.savedView.value = id; elements.savedViewName.value = ""; elements.deleteView.disabled = false;
  } catch (error) { renderFailure(error); }
});
elements.savedView.addEventListener("change", () => {
  const view = runtimeState.savedViews.find(item => item.id === elements.savedView.value);
  elements.deleteView.disabled = !view;
  if (view) applySavedView(view);
});
elements.deleteView.addEventListener("click", () => {
  runtimeState.savedViews = removeSavedView(runtimeState.savedViews, elements.savedView.value);
  renderSavedViews();
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && Number(elements.autoRefreshInterval.value) > 0) {
    void refreshDashboard();
  }
});

for (const button of elements.quickRanges) {
  button.addEventListener("click", () =>
    setQuickRange(Number(button.dataset.hours)),
  );
}

try {
  initializeCharts();
  setQuickRange(24, false);
  setAutoRefresh(Number(elements.autoRefreshInterval.value));
  renderSavedViews();
  void refreshDashboard();
} catch (error) {
  renderFailure(error instanceof Error ? error : new Error("看板初始化失败。"));
  setLoading(false);
}
