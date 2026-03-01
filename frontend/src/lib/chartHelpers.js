export const CHECKLIST_FIELDS = [
  { key: "red_candle", label: "Red Candle", row: 1 },
  { key: "trend_bullish", label: "Trend Bullish", row: 1 },
  { key: "whale_accumulation_plus", label: "Whale +", row: 1 },
  { key: "macd_positive", label: "MACD +", row: 1 },
  { key: "macd_plus_cross", label: "MACD + Cross", row: 1 },
  { key: "yellow_candle", label: "Yellow Candle", row: 2 },
  { key: "trend_bearish", label: "Trend Bearish", row: 2 },
  { key: "whale_accumulation_minus", label: "Whale -", row: 2 },
  { key: "macd_negative", label: "MACD -", row: 2 },
  { key: "macd_minus_cross", label: "MACD - Cross", row: 2 },
];

export const TIMEFRAME_OPTIONS = ["D", "W", "M"];

export const normalizeTimeframe = (timeframe) => {
  const normalized = String(timeframe || "").trim().toUpperCase();
  return TIMEFRAME_OPTIONS.includes(normalized) ? normalized : "D";
};

export const getNextTimeframe = (timeframe) => {
  const normalized = normalizeTimeframe(timeframe);
  const currentIndex = TIMEFRAME_OPTIONS.indexOf(normalized);
  return TIMEFRAME_OPTIONS[(currentIndex + 1) % TIMEFRAME_OPTIONS.length];
};

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
    const error = new Error(payload.error || "Request failed");
    error.status = response.status;
    throw error;
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


export const normalizeAnalysis = (analysis = {}) => ({
  status: typeof analysis?.status === "string" && analysis.status ? analysis.status : "idle",
  model: typeof analysis?.model === "string" ? analysis.model : "",
  prompt_version: typeof analysis?.prompt_version === "string" ? analysis.prompt_version : "",
  text: typeof analysis?.text === "string" ? analysis.text : "",
  error: typeof analysis?.error === "string" ? analysis.error : "",
  started_at: typeof analysis?.started_at === "string" ? analysis.started_at : "",
  completed_at: typeof analysis?.completed_at === "string" ? analysis.completed_at : "",
});

export const analyzeChart = async (chart) => {
  const payload = await fetchJson(
    `/api/charts/${encodeURIComponent(chart.ticker)}/${encodeURIComponent(chart.date)}/${encodeURIComponent(
      chart.filename
    )}/analyze`,
    { method: "POST" }
  );
  return payload.chart;
};


export const cycleChartTimeframe = async (chart) => {
  const chartRoute = `/api/charts/${encodeURIComponent(chart.ticker)}/${encodeURIComponent(
    chart.date
  )}/${encodeURIComponent(chart.filename)}`;

  try {
    const payload = await fetchJson(`${chartRoute}/timeframe`, { method: "POST" });
    return payload.chart;
  } catch (error) {
    if (!error || error.status !== 404) {
      throw error;
    }

    const payload = await fetchJson(`${chartRoute}/notes`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        notes: chart.notes || "",
        timeframe: getNextTimeframe(chart.timeframe),
      }),
    });
    return payload.chart;
  }
};
