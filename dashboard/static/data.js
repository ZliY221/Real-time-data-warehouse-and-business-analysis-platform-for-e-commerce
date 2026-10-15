const MONEY_PATTERN = /^(-?)(\d+)(?:\.(\d+))?$/;

export function toApiTimestamp(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("请输入有效的开始和结束时间。");
  }
  return parsed.toISOString();
}

export function buildMetricQuery(filters, extras = {}) {
  const parameters = new URLSearchParams({
    start: toApiTimestamp(filters.start),
    end: toApiTimestamp(filters.end),
  });
  if (filters.region) parameters.set("region", filters.region);
  if (filters.channel) parameters.set("channel", filters.channel);
  for (const [name, value] of Object.entries(extras)) {
    if (value !== undefined && value !== null && value !== "") {
      parameters.set(name, String(value));
    }
  }
  return parameters;
}

export function formatMoney(value) {
  const match = MONEY_PATTERN.exec(String(value));
  if (!match) return "—";
  const [, sign, integer, fraction = ""] = match;
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const decimals = fraction.padEnd(2, "0").slice(0, 2);
  return `${sign}¥${grouped}.${decimals}`;
}

export function formatInteger(value) {
  try {
    return BigInt(String(value)).toLocaleString("zh-CN");
  } catch {
    return "—";
  }
}

export function formatTimestamp(value, options = {}) {
  if (!value) return "暂无处理时间";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "时间格式异常";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: options.seconds ? "2-digit" : undefined,
    hour12: false,
  }).format(parsed);
}

export function formatLag(value, now = new Date()) {
  if (!value) return "暂无数据";
  const processedAt = new Date(value);
  if (Number.isNaN(processedAt.getTime())) return "时间异常";
  const seconds = Math.max(
    0,
    Math.floor((now.getTime() - processedAt.getTime()) / 1000),
  );
  if (seconds < 60) return `${seconds} 秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}

export function formatLocalInput(value) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}

export function createLocalRange(hours, now = new Date()) {
  return {
    start: formatLocalInput(new Date(now.getTime() - hours * 60 * 60 * 1000)),
    end: formatLocalInput(now),
  };
}

export function createComparisonPeriod(filters, mode = "previous") {
  const start = new Date(filters.start);
  const end = new Date(filters.end);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) {
    throw new Error("请输入有效的开始和结束时间。");
  }
  const duration = end.getTime() - start.getTime();
  const offset = mode === "previous" ? duration
    : mode === "day" ? 24 * 60 * 60 * 1000
      : mode === "week" ? 7 * 24 * 60 * 60 * 1000 : NaN;
  if (!Number.isFinite(offset)) throw new Error("请选择有效的对比基准。");
  return {
    baseline_start: new Date(start.getTime() - offset).toISOString(),
    baseline_end: new Date(end.getTime() - offset).toISOString(),
  };
}

export function formatGrowthRate(value) {
  if (value === null || value === undefined) return "暂无基准";
  const rate = Number(value);
  if (!Number.isFinite(rate)) return "暂无基准";
  return `${rate > 0 ? "+" : ""}${(rate * 100).toFixed(1)}%`;
}

export function buildContributionRows(currentItems, baselineItems, limit = 5) {
  const baseline = new Map((baselineItems || []).map(item => [item.name, Number(item.gmv)]));
  const current = new Map((currentItems || []).map(item => [item.name, Number(item.gmv)]));
  const names = new Set([...current.keys(), ...baseline.keys()]);
  return [...names].map(name => ({
    name,
    currentGmv: current.get(name) || 0,
    baselineGmv: baseline.get(name) || 0,
    deltaGmv: (current.get(name) || 0) - (baseline.get(name) || 0),
  })).sort((left, right) => Math.abs(right.deltaGmv) - Math.abs(left.deltaGmv)
    || left.name.localeCompare(right.name)).slice(0, limit);
}

export function qualityPassRate(runs) {
  if (!Array.isArray(runs) || runs.length === 0) return null;
  const passed = runs.filter((run) => run?.passed === true).length;
  return passed / runs.length;
}

export function filterAssetHealth(items, { status = "", owner = "" } = {}) {
  if (!Array.isArray(items)) return [];
  return items.filter((item) =>
    (!status || item?.status === status) && (!owner || item?.owner === owner))
    .sort((left, right) =>
      (Number(right?.priority_score) - Number(left?.priority_score)) ||
      String(left?.asset_id).localeCompare(String(right?.asset_id)));
}

export function anomalyTypeLabel(value) {
  return { rejected: "拒绝事件", late: "迟到事件" }[value] || value;
}

export function anomalyReasonLabel(value) {
  return {
    window_late: "窗口迟到",
    empty_payload: "空载荷",
    invalid_json_shape: "JSON 结构错误",
    malformed_json: "JSON 解析失败",
    invalid_field: "字段校验失败",
  }[value] || value;
}

export function apiErrorMessage(status, payload) {
  const detail = payload?.detail;
  if (detail?.code === "analytics_store_unavailable") {
    return "分析存储暂时不可用。请确认 ClickHouse 已启动后重试。";
  }
  if (detail?.code === "quality_history_unavailable") {
    return "质量历史暂时不可用。请确认 SQLite 历史库可读后重试。";
  }
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return `请求失败（HTTP ${status}）。请稍后重试。`;
}
