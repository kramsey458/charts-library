export const CHECKLIST_FIELDS = [
  { key: "red_candle", label: "Red Candle" },
  { key: "yellow_candle", label: "Yellow Candle" },
  { key: "trend_bullish", label: "Trend Bullish" },
  { key: "whale_over_50", label: "Whale Accumulation" },
  { key: "momentum_green", label: "MACD Positive" },
  { key: "macd_blue_cross_over_orange", label: "MACD Cross" },
];

const apiBaseUrl = (import.meta.env?.VITE_API_BASE_URL || "").trim().replace(/\/$/, "");

export const withApiBase = (path) => {
  if (!apiBaseUrl || /^https?:\/\//i.test(path)) {
    return path;
  }
  if (!/^https?:\/\//i.test(apiBaseUrl)) {
    return path;
  }
  return `${apiBaseUrl}${path}`;
};

export const fetchJson = async (url, options) => {
  const response = await fetch(withApiBase(url), options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "Request failed");
  }
  return response.json();
};

export const buildChartPath = (chart) =>
  withApiBase(`/api/chart-file/${encodeURIComponent(chart.ticker)}/${encodeURIComponent(
    chart.date
  )}/${encodeURIComponent(chart.filename)}`);

export const buildNotesPreview = (notes = "") => {
  const trimmedNotes = notes.trim();
  if (!trimmedNotes) {
    return "";
  }
  if (trimmedNotes.length <= 100) {
    return trimmedNotes;
  }
  return `${trimmedNotes.slice(0, 100)}...`;
};

export const getChartKey = (chart) => `${chart.ticker}::${chart.date}::${chart.filename}`;

export const buildEmptyChecklist = () =>
  CHECKLIST_FIELDS.reduce((acc, item) => {
    acc[item.key] = false;
    return acc;
  }, {});

export const buildChecklistSummary = (checklist = {}) => {
  const selected = CHECKLIST_FIELDS.filter((item) => checklist[item.key]).map((item) => item.label);
  return selected.length > 0 ? selected.join(" • ") : "No checklist flags.";
};

export const chartHasFlag = (chart, key) => Boolean(chart?.checklist?.[key]);
