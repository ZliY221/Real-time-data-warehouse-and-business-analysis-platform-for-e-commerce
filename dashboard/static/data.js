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
  const safeGmv = value => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const baseline = new Map((baselineItems || []).map(item => [item.name, safeGmv(item.gmv)]));
  const current = new Map((currentItems || []).map(item => [item.name, safeGmv(item.gmv)]));
  const names = new Set([...current.keys(), ...baseline.keys()]);
  return [...names].map(name => ({
    name,
    currentGmv: current.get(name) || 0,
    baselineGmv: baseline.get(name) || 0,
    deltaGmv: (current.get(name) || 0) - (baseline.get(name) || 0),
  })).sort((left, right) => Math.abs(right.deltaGmv) - Math.abs(left.deltaGmv)
    || left.name.localeCompare(right.name)).slice(0, limit);
}

export function getContributionContext(dimension, filters) {
  if (!["region", "channel"].includes(dimension)) throw new Error("unsupported contribution dimension");
  const name = String(filters?.[dimension] || "").trim();
  return name ? { dimension, name } : null;
}

export function buildDashboardShareQuery(view, now = new Date()) {
  const filters = view?.filters || {};
  createComparisonPeriod(filters, view?.comparisonMode || "previous");
  const comparisonMode = ["previous", "day", "week"].includes(view?.comparisonMode)
    ? view.comparisonMode : "previous";
  const comparisonDimension = ["region", "channel"].includes(view?.comparisonDimension)
    ? view.comparisonDimension : "region";
  const refreshSeconds = [0, 5, 15, 30].includes(Number(view?.refreshSeconds))
    ? Number(view.refreshSeconds) : 5;
  const query = new URLSearchParams({
    view: "2",
    issued: now.toISOString(),
    start: String(filters.start),
    end: String(filters.end),
    comparison: comparisonMode,
    dimension: comparisonDimension,
    refresh: String(refreshSeconds),
    expires: new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString(),
  });
  if (filters.region) query.set("region", String(filters.region));
  if (filters.channel) query.set("channel", String(filters.channel));
  const context = String(view?.handoffContext || "").trim();
  if (context) query.set("context", context.slice(0, 80));
  return query;
}

export function parseDashboardShareQuery(search, now = new Date()) {
  const query = new URLSearchParams(search);
  if (query.get("view") !== "2" || !query.get("start") || !query.get("end")) return null;
  const issuedAt = new Date(query.get("issued") || "");
  if (Number.isNaN(issuedAt.getTime()) || issuedAt > now) return null;
  const expiresAt = new Date(query.get("expires") || "");
  if (Number.isNaN(expiresAt.getTime()) || expiresAt <= now) return null;
  const comparisonMode = query.get("comparison") || "previous";
  const comparisonDimension = query.get("dimension") || "region";
  const refreshSeconds = Number(query.get("refresh") ?? 5);
  if (!["previous", "day", "week"].includes(comparisonMode)) return null;
  if (!["region", "channel"].includes(comparisonDimension)) return null;
  if (![0, 5, 15, 30].includes(refreshSeconds)) return null;
  const filters = {
    start: query.get("start"), end: query.get("end"),
    region: query.get("region") || "", channel: query.get("channel") || "",
  };
  try {
    createComparisonPeriod(filters, comparisonMode);
  } catch {
    return null;
  }
  return {
    filters, comparisonMode, comparisonDimension, refreshSeconds,
    issuedAt: issuedAt.toISOString(), handoffContext: query.get("context") || "",
  };
}

export function dashboardShareExpiry(search, now = new Date()) {
  const query = new URLSearchParams(search);
  const expiresAt = new Date(query.get("expires") || "");
  if (Number.isNaN(expiresAt.getTime())) return null;
  const remainingMs = expiresAt.getTime() - now.getTime();
  if (remainingMs <= 0) return { status: "EXPIRED", expiresAt: expiresAt.toISOString(), remainingHours: 0 };
  const remainingHours = Math.ceil(remainingMs / (60 * 60 * 1000));
  return {
    status: remainingHours <= 24 ? "EXPIRING_SOON" : "ACTIVE",
    expiresAt: expiresAt.toISOString(),
    remainingHours,
  };
}

export function inspectDashboardShareQuery(search, now = new Date()) {
  const query = new URLSearchParams(search);
  if (!query.has("view")) return { status: "NO_LINK", usable: false };
  if (query.get("view") !== "2") return { status: "UNSUPPORTED_VERSION", usable: false };
  if (!query.get("start") || !query.get("end")) return { status: "INVALID", usable: false };
  const expiry = dashboardShareExpiry(query, now);
  if (!expiry) return { status: "INVALID", usable: false };
  if (expiry.status === "EXPIRED") return { status: "EXPIRED", usable: false };
  return parseDashboardShareQuery(query, now)
    ? { status: expiry.status, usable: true }
    : { status: "INVALID", usable: false };
}

export function summarizeDashboardShareView(view) {
  if (!view?.filters?.start || !view?.filters?.end) throw new Error("分享视图缺少时间范围");
  const scope = [view.filters.region, view.filters.channel].filter(Boolean).join(" / ") || "全部地区与渠道";
  const mode = { previous: "上一时段", day: "昨日同期", week: "上周同期" }[view.comparisonMode] || "上一时段";
  return `${view.filters.start} 至 ${view.filters.end} · ${scope} · ${mode}`;
}

export function canonicalizeDashboardShareQuery(search, now = new Date()) {
  if (!parseDashboardShareQuery(search, now)) return null;
  const source = new URLSearchParams(search);
  const allowed = new Set([
    "view", "start", "end", "comparison", "dimension", "refresh",
    "issued", "expires", "region", "channel", "context",
  ]);
  for (const key of [...source.keys()]) if (!allowed.has(key)) source.delete(key);
  source.sort();
  return source;
}

export function dashboardShareFingerprint(search, now = new Date()) {
  const canonical = canonicalizeDashboardShareQuery(search, now);
  if (!canonical) return null;
  let hash = 2166136261;
  for (const character of canonical.toString()) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `VIEW-${(hash >>> 0).toString(16).toUpperCase().padStart(8, "0")}`;
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
