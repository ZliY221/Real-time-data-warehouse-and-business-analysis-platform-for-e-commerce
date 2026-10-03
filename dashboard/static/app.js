import {
  apiErrorMessage,
  buildMetricQuery,
  createLocalRange,
  formatInteger,
  formatLag,
  formatMoney,
  formatTimestamp,
} from "./data.js";

const elements = {
  body: document.body,
  form: document.querySelector("#filter-form"),
  start: document.querySelector("#start-time"),
  end: document.querySelector("#end-time"),
  region: document.querySelector("#region-filter"),
  channel: document.querySelector("#channel-filter"),
  refresh: document.querySelector("#refresh-button"),
  reset: document.querySelector("#reset-button"),
  retry: document.querySelector("#retry-button"),
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
  trendChart: document.querySelector("#trend-chart"),
  regionChart: document.querySelector("#region-chart"),
  channelChart: document.querySelector("#channel-chart"),
  trendEmpty: document.querySelector("#trend-empty"),
  trendSubtitle: document.querySelector("#trend-subtitle"),
  bucketBadge: document.querySelector("#bucket-badge"),
  recentTable: document.querySelector("#recent-table-body"),
  regionTable: document.querySelector("#region-table-body"),
  channelTable: document.querySelector("#channel-table-body"),
  lastRefreshed: document.querySelector("#last-refreshed"),
  liveStatus: document.querySelector("#screen-reader-status"),
};

const reducedMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)",
).matches;
const darkMode = window.matchMedia("(prefers-color-scheme: dark)").matches;
const charts = {};
const dimensionOptions = { regions: new Set(), channels: new Set() };
const runtimeState = { dataMode: "clickhouse" };

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
  for (const chart of Object.values(charts)) chart.clear();
}

async function refreshDashboard() {
  elements.errorBanner.hidden = true;
  setLoading(true);
  try {
    const filters = currentFilters();
    const [summary, timeSeries, regions, channels, recent] = await Promise.all([
      fetchJson("/api/v1/metrics/summary", queryFor(filters)),
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
    ]);

    renderSummary(summary);
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
    setLoading(false);
  }
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  for (const button of elements.quickRanges) {
    button.classList.remove("is-active");
    button.setAttribute("aria-pressed", "false");
  }
  void refreshDashboard();
});

elements.reset.addEventListener("click", () => {
  elements.region.value = "";
  elements.channel.value = "";
  setQuickRange(24);
});

elements.retry.addEventListener("click", () => void refreshDashboard());

for (const button of elements.quickRanges) {
  button.addEventListener("click", () =>
    setQuickRange(Number(button.dataset.hours)),
  );
}

try {
  initializeCharts();
  setQuickRange(24, false);
  void refreshDashboard();
} catch (error) {
  renderFailure(error instanceof Error ? error : new Error("看板初始化失败。"));
  setLoading(false);
}
