const MAX_SAVED_VIEWS = 12;

export function normalizeSavedViews(value) {
  if (!Array.isArray(value)) return [];
  return value.filter(item => item && typeof item === "object")
    .map(item => ({
      id: String(item.id || ""),
      name: String(item.name || "").trim().slice(0, 30),
      quickRangeHours: [1, 6, 24].includes(Number(item.quickRangeHours)) ? Number(item.quickRangeHours) : null,
      comparisonMode: ["previous", "day", "week"].includes(item.comparisonMode) ? item.comparisonMode : "previous",
      filters: {
        start: String(item.filters?.start || ""), end: String(item.filters?.end || ""),
        region: String(item.filters?.region || ""), channel: String(item.filters?.channel || ""),
      },
      refreshSeconds: [0, 5, 15, 30].includes(Number(item.refreshSeconds)) ? Number(item.refreshSeconds) : 5,
    }))
    .filter(item => item.id && item.name && item.filters.start && item.filters.end)
    .slice(0, MAX_SAVED_VIEWS);
}

export function parseSavedViews(serialized) {
  try { return normalizeSavedViews(JSON.parse(serialized || "[]")); }
  catch { return []; }
}

export function upsertSavedView(views, view) {
  const normalized = normalizeSavedViews([view]);
  if (!normalized.length) throw new Error("视图名称和筛选条件不能为空");
  return [normalized[0], ...normalizeSavedViews(views).filter(item => item.id !== normalized[0].id)]
    .slice(0, MAX_SAVED_VIEWS);
}

export function removeSavedView(views, id) {
  return normalizeSavedViews(views).filter(item => item.id !== id);
}
