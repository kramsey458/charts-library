import { getStore } from "@netlify/blobs";

const ALLOWED_EXTENSIONS = new Set(["png"]);
const STORE_NAME = process.env.NETLIFY_BLOBS_STORE || "chart-vault";
const INDEX_KEY = "charts/index.json";

const json = (payload, status = 200) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });

const normalize = (value) => value.trim().toUpperCase();

const cleanSegment = (value) =>
  value
    .trim()
    .replace(/[^A-Za-z0-9._-]/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-|-$/g, "");

const isAllowedFile = (filename) => {
  const parts = filename.split(".");
  if (parts.length < 2) {
    return false;
  }
  const extension = parts.at(-1)?.toLowerCase() || "";
  return ALLOWED_EXTENSIONS.has(extension);
};

const getStoreClient = (context) => {
  const store = getStore({ name: STORE_NAME, consistency: "strong" }, { context });
  return store;
};

const loadIndex = async (store) => {
  const result = await store.get(INDEX_KEY, { type: "json" });
  if (!Array.isArray(result)) {
    return [];
  }
  return result;
};

const saveIndex = async (store, charts) => {
  await store.set(INDEX_KEY, JSON.stringify(charts), {
    contentType: "application/json",
  });
};

const buildChartKey = (ticker, date, filename) => `charts/images/${ticker}/${date}/${filename}`;

const toChartPayload = (chart) => ({
  ticker: chart.ticker,
  date: chart.date,
  filename: chart.filename,
  notes: chart.notes || "",
  url: `/api/chart-file/${chart.ticker}/${chart.date}/${chart.filename}`,
});

const getPathParts = (pathname) => pathname.replace(/^\/api\/?/, "").split("/").filter(Boolean);

export default async (request, context) => {
  const store = getStoreClient(context);
  const url = new URL(request.url);
  const parts = getPathParts(url.pathname);

  if (url.pathname === "/api/health" && request.method === "GET") {
    return json({ status: "ok", storage_mode: "external", provider: "netlify-blobs" });
  }

  if (url.pathname === "/api/tickers" && request.method === "GET") {
    const charts = await loadIndex(store);
    const chartCounts = {};
    for (const chart of charts) {
      chartCounts[chart.ticker] = (chartCounts[chart.ticker] || 0) + 1;
    }
    const tickers = Object.keys(chartCounts).sort();
    return json({
      tickers,
      chart_counts: chartCounts,
      total_charts: charts.length,
    });
  }

  if (parts[0] === "charts" && parts.length === 2 && request.method === "GET") {
    const ticker = decodeURIComponent(parts[1]).toUpperCase();
    const charts = await loadIndex(store);
    const tickerCharts = charts
      .filter((chart) => chart.ticker === ticker)
      .sort((a, b) => (a.date < b.date ? 1 : -1))
      .map(toChartPayload);
    return json({ charts: tickerCharts });
  }

  if (url.pathname === "/api/charts" && request.method === "POST") {
    const formData = await request.formData();
    const tickerRaw = String(formData.get("ticker") || "");
    const dateRaw = String(formData.get("date") || "").trim();
    const notes = String(formData.get("notes") || "").trim();
    const chartFile = formData.get("chart");

    if (!tickerRaw.trim()) {
      return json({ error: "Ticker is required." }, 400);
    }
    if (!(chartFile instanceof File) || !chartFile.name) {
      return json({ error: "Chart image is required." }, 400);
    }
    if (!isAllowedFile(chartFile.name)) {
      return json({ error: "Only PNG files are supported." }, 400);
    }

    const ticker = cleanSegment(normalize(tickerRaw));
    const date = cleanSegment(dateRaw || new Date().toISOString().slice(0, 10));
    const filename = cleanSegment(chartFile.name);
    const key = buildChartKey(ticker, date, filename);
    const buffer = await chartFile.arrayBuffer();

    await store.set(key, buffer, {
      contentType: chartFile.type || "image/png",
    });

    const charts = await loadIndex(store);
    const dedupedCharts = charts.filter(
      (chart) => !(chart.ticker === ticker && chart.date === date && chart.filename === filename)
    );
    dedupedCharts.push({ ticker, date, filename, notes, key, createdAt: Date.now() });
    await saveIndex(store, dedupedCharts);

    return json(
      {
        message: "Chart uploaded.",
        chart: {
          ticker,
          date,
          filename,
          notes,
          url: `/api/chart-file/${ticker}/${date}/${filename}`,
        },
      },
      201
    );
  }

  if (parts[0] === "charts" && parts.length === 4 && request.method === "DELETE") {
    const ticker = decodeURIComponent(parts[1]).toUpperCase();
    const date = decodeURIComponent(parts[2]);
    const filename = decodeURIComponent(parts[3]);

    const charts = await loadIndex(store);
    const chart = charts.find(
      (item) => item.ticker === ticker && item.date === date && item.filename === filename
    );
    if (!chart) {
      return json({ error: "Chart not found." }, 404);
    }

    await store.delete(chart.key || buildChartKey(ticker, date, filename));
    const nextCharts = charts.filter(
      (item) => !(item.ticker === ticker && item.date === date && item.filename === filename)
    );
    await saveIndex(store, nextCharts);

    return json({ message: "Chart deleted." });
  }

  if (parts[0] === "chart-file" && parts.length === 4 && request.method === "GET") {
    const ticker = decodeURIComponent(parts[1]).toUpperCase();
    const date = decodeURIComponent(parts[2]);
    const filename = decodeURIComponent(parts[3]);

    const charts = await loadIndex(store);
    const chart = charts.find(
      (item) => item.ticker === ticker && item.date === date && item.filename === filename
    );

    if (!chart) {
      return json({ error: "Chart not found." }, 404);
    }

    const blob = await store.get(chart.key || buildChartKey(ticker, date, filename), {
      type: "arrayBuffer",
    });

    if (!blob) {
      return json({ error: "Chart not found." }, 404);
    }

    return new Response(blob, {
      status: 200,
      headers: {
        "content-type": "image/png",
        "cache-control": "public, max-age=3600",
      },
    });
  }

  return json({ error: "Not found." }, 404);
};
