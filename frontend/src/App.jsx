import { useEffect, useMemo, useState } from "react";

const emptyState = {
  tickers: [],
  charts: [],
};

const fetchJson = async (url, options) => {
  const response = await fetch(url, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "Request failed");
  }
  return response.json();
};

const buildChartPath = (chart) => {
  return `/api/chart-file/${encodeURIComponent(chart.ticker)}/${encodeURIComponent(
    chart.date
  )}/${encodeURIComponent(chart.filename)}`;
};

export default function App() {
  const [tickers, setTickers] = useState(emptyState.tickers);
  const [selectedTicker, setSelectedTicker] = useState("");
  const [charts, setCharts] = useState(emptyState.charts);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [previewChart, setPreviewChart] = useState(null);
  const [formState, setFormState] = useState({
    ticker: "",
    date: "",
    file: null,
  });

  const groupedCharts = useMemo(() => {
    return charts.reduce((groups, chart) => {
      if (!groups[chart.date]) {
        groups[chart.date] = [];
      }
      groups[chart.date].push(chart);
      return groups;
    }, {});
  }, [charts]);

  const sortedDates = useMemo(() => {
    return Object.keys(groupedCharts).sort((a, b) => (a < b ? 1 : -1));
  }, [groupedCharts]);

  const loadTickers = async () => {
    const data = await fetchJson("/api/tickers");
    setTickers(data.tickers);
    if (!selectedTicker && data.tickers.length > 0) {
      setSelectedTicker(data.tickers[0]);
    }
  };

  const loadCharts = async (ticker) => {
    if (!ticker) {
      setCharts([]);
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const data = await fetchJson(`/api/charts/${encodeURIComponent(ticker)}`);
      setCharts(data.charts);
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus("idle");
    }
  };

  useEffect(() => {
    loadTickers();
  }, []);

  useEffect(() => {
    if (selectedTicker) {
      loadCharts(selectedTicker);
    }
  }, [selectedTicker]);

  const handleUpload = async (event) => {
    event.preventDefault();
    setError("");

    if (!formState.ticker || !formState.file) {
      setError("Please provide a ticker and PNG chart file.");
      return;
    }

    const normalizedTicker = formState.ticker.trim().toUpperCase();
    const formData = new FormData();
    formData.append("ticker", normalizedTicker);
    formData.append("date", formState.date);
    formData.append("chart", formState.file);

    try {
      setStatus("uploading");
      await fetchJson("/api/charts", {
        method: "POST",
        body: formData,
      });
      await loadTickers();
      setSelectedTicker(normalizedTicker);
      await loadCharts(normalizedTicker);
      setFormState({ ticker: "", date: "", file: null });
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus("idle");
    }
  };

  const handleDeleteChart = async (chart) => {
    const shouldDelete = window.confirm(
      `Delete ${chart.filename} from ${chart.ticker} on ${chart.date}?`
    );
    if (!shouldDelete) {
      return;
    }

    setError("");
    try {
      setStatus("deleting");
      await fetchJson(
        `/api/charts/${encodeURIComponent(chart.ticker)}/${encodeURIComponent(
          chart.date
        )}/${encodeURIComponent(chart.filename)}`,
        { method: "DELETE" }
      );
      await loadCharts(selectedTicker);
      await loadTickers();
      if (
        previewChart &&
        previewChart.ticker === chart.ticker &&
        previewChart.date === chart.date &&
        previewChart.filename === chart.filename
      ) {
        setPreviewChart(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus("idle");
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div>
          <p className="eyebrow">Chart Vault</p>
          <h1>Store and review your trading chart snapshots.</h1>
          <p className="subtitle">
            Upload PNG charts by ticker and date. Instantly browse your visual
            history with a responsive, card-based gallery.
          </p>
        </div>
        <div className="header-card">
          <div className="stat">
            <span className="stat-label">Tickers tracked</span>
            <span className="stat-value">{tickers.length}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Charts stored</span>
            <span className="stat-value">{charts.length}</span>
          </div>
        </div>
      </header>

      <section className="controls">
        <div className="selector">
          <label htmlFor="ticker-select">Ticker library</label>
          <select
            id="ticker-select"
            value={selectedTicker}
            onChange={(event) => setSelectedTicker(event.target.value)}
          >
            <option value="">Select a ticker</option>
            {tickers.map((ticker) => (
              <option key={ticker} value={ticker}>
                {ticker}
              </option>
            ))}
          </select>
        </div>

        <form className="upload" onSubmit={handleUpload}>
          <div className="upload-field">
            <label htmlFor="ticker-input">Ticker</label>
            <input
              id="ticker-input"
              placeholder="NVDA"
              value={formState.ticker}
              onChange={(event) =>
                setFormState((prev) => ({
                  ...prev,
                  ticker: event.target.value.toUpperCase(),
                }))
              }
              maxLength={6}
            />
          </div>
          <div className="upload-field">
            <label htmlFor="date-input">Date</label>
            <input
              id="date-input"
              type="date"
              value={formState.date}
              onChange={(event) =>
                setFormState((prev) => ({ ...prev, date: event.target.value }))
              }
            />
          </div>
          <div className="upload-field">
            <label htmlFor="file-input">Chart PNG</label>
            <input
              id="file-input"
              type="file"
              accept="image/png"
              onChange={(event) =>
                setFormState((prev) => ({
                  ...prev,
                  file: event.target.files?.[0] || null,
                }))
              }
            />
          </div>
          <button type="submit" disabled={status === "uploading"}>
            {status === "uploading" ? "Uploading..." : "Save chart"}
          </button>
        </form>
      </section>

      <section className="gallery">
        <div className="gallery-header">
          <div>
            <h2>{selectedTicker ? `${selectedTicker} charts` : "Charts"}</h2>
            <p>Browse your saved snapshots organized by date.</p>
          </div>
          {error && <span className="error">{error}</span>}
        </div>

        {status === "loading" ? (
          <div className="empty-state">Loading charts...</div>
        ) : charts.length === 0 ? (
          <div className="empty-state">
            Upload your first chart to start building this ticker timeline.
          </div>
        ) : (
          <div className="date-groups">
            {sortedDates.map((date) => (
              <div className="date-group" key={date}>
                <div className="date-label">{date}</div>
                <div className="chart-grid">
                  {groupedCharts[date].map((chart) => (
                    <div className="chart-card" key={`${chart.date}-${chart.filename}`}>
                      <button
                        type="button"
                        className="chart-preview-trigger"
                        onClick={() => setPreviewChart(chart)}
                        aria-label={`Open full image for ${chart.filename}`}
                      >
                        <img src={buildChartPath(chart)} alt={`${chart.ticker} chart`} />
                      </button>
                      <div className="chart-meta">
                        <a href={buildChartPath(chart)} download={chart.filename}>
                          {chart.filename}
                        </a>
                        <span>{chart.ticker}</span>
                      </div>
                      <button
                        type="button"
                        className="delete-button"
                        onClick={() => handleDeleteChart(chart)}
                        disabled={status === "deleting"}
                      >
                        Delete
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {previewChart && (
        <div
          className="chart-modal-overlay"
          role="button"
          tabIndex={0}
          onClick={() => setPreviewChart(null)}
          onKeyDown={(event) => {
            if (event.key === "Escape" || event.key === "Enter") {
              setPreviewChart(null);
            }
          }}
        >
          <div className="chart-modal" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              className="close-modal"
              onClick={() => setPreviewChart(null)}
            >
              Close
            </button>
            <img
              className="chart-modal-image"
              src={buildChartPath(previewChart)}
              alt={`${previewChart.ticker} ${previewChart.filename}`}
            />
            <div className="chart-modal-meta">
              <a href={buildChartPath(previewChart)} download={previewChart.filename}>
                {previewChart.filename}
              </a>
              <span>
                {previewChart.ticker} • {previewChart.date}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
