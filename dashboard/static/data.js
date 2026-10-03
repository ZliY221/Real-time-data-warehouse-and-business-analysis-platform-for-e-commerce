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

export function apiErrorMessage(status, payload) {
  const detail = payload?.detail;
  if (detail?.code === "analytics_store_unavailable") {
    return "分析存储暂时不可用。请确认 ClickHouse 已启动后重试。";
  }
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return `请求失败（HTTP ${status}）。请稍后重试。`;
}
