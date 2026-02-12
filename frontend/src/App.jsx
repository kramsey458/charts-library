import { useEffect, useMemo, useRef, useState } from "react";

import {
  CHECKLIST_FIELDS,
  buildChartPath,
  buildChecklistSummary,
  buildEmptyChecklist,
  buildNotesPreview,
  chartHasFlag,
  fetchJson,
  getChartKey,
} from "./lib/chartHelpers";

const emptyState = {
  tickers: [],
  charts: [],
};

export default function App() {
  const [tickers, setTickers] = useState(emptyState.tickers);
  const [selectedTicker, setSelectedTicker] = useState("");
  const [tickerSearch, setTickerSearch] = useState("");
  const [tickerSortBy, setTickerSortBy] = useState("name");
  const [tickerSortDirection, setTickerSortDirection] = useState("asc");
  const [charts, setCharts] = useState(emptyState.charts);
  const [activeChecklistFilters, setActiveChecklistFilters] = useState(buildEmptyChecklist());
  const [chartsTicker, setChartsTicker] = useState("");
  const [totalCharts, setTotalCharts] = useState(0);
  const [chartCountsByTicker, setChartCountsByTicker] = useState({});
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [previewChart, setPreviewChart] = useState(null);
  const [previewZoom, setPreviewZoom] = useState(1);
  const [previewPan, setPreviewPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [isModalFullscreen, setIsModalFullscreen] = useState(false);
  const [isSlideshowOpen, setIsSlideshowOpen] = useState(false);
  const [slideshowSortOrder, setSlideshowSortOrder] = useState("newest");
  const [slideshowStartDate, setSlideshowStartDate] = useState("");
  const [slideshowEndDate, setSlideshowEndDate] = useState("");
  const [slideshowIndex, setSlideshowIndex] = useState(0);
  const [editingNotesKey, setEditingNotesKey] = useState("");
  const [notesDraft, setNotesDraft] = useState("");
  const [isSavingNotes, setIsSavingNotes] = useState(false);
  const [isSavingChecklist, setIsSavingChecklist] = useState(false);
  const [formState, setFormState] = useState({
    ticker: "",
    date: "",
    notes: "",
    file: null,
    checklist: buildEmptyChecklist(),
  });
  const dateInputRef = useRef(null);
  const fileInputRef = useRef(null);
  const modalRef = useRef(null);
  const slideshowRef = useRef(null);
  const panStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });
  const panRef = useRef({ x: 0, y: 0 });

  const getTodayDateValue = () => {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, "0");
    const day = String(today.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };

  const handleDateInputDoubleClick = () => {
    setFormState((prev) => ({
      ...prev,
      date: getTodayDateValue(),
    }));
  };

  const clampZoom = (zoom) => Math.min(4, Math.max(1, zoom));

  const resetPreviewTransform = () => {
    setPreviewZoom(1);
    const nextPan = { x: 0, y: 0 };
    panRef.current = nextPan;
    setPreviewPan(nextPan);
  };

  const openChartPreview = (chart) => {
    setPreviewChart(chart);
    setEditingNotesKey("");
    setNotesDraft("");
    resetPreviewTransform();
  };

  const openChartNotesEditor = (chart) => {
    openChartPreview(chart);
    startEditingNotes(chart);
  };

  const closeChartPreview = () => {
    if (document.fullscreenElement === modalRef.current) {
      document.exitFullscreen().catch(() => {});
    }
    setPreviewChart(null);
    setIsPanning(false);
    setIsModalFullscreen(false);
    setEditingNotesKey("");
    setNotesDraft("");
  };

  const openSlideshow = () => {
    if (slideshowCharts.length === 0) {
      return;
    }

    setSlideshowIndex(0);
    setIsSlideshowOpen(true);
  };

  const closeSlideshow = () => {
    if (document.fullscreenElement === slideshowRef.current) {
      document.exitFullscreen().catch(() => {});
    }
    setIsSlideshowOpen(false);
  };

  const goToNextSlideshowChart = () => {
    if (slideshowCharts.length === 0) {
      return;
    }
    setSlideshowIndex((prevIndex) => (prevIndex + 1) % slideshowCharts.length);
  };

  const goToPreviousSlideshowChart = () => {
    if (slideshowCharts.length === 0) {
      return;
    }
    setSlideshowIndex((prevIndex) => (prevIndex - 1 + slideshowCharts.length) % slideshowCharts.length);
  };

  const startEditingNotes = (chart) => {
    setEditingNotesKey(getChartKey(chart));
    setNotesDraft(chart.notes || "");
  };

  const cancelEditingNotes = () => {
    setEditingNotesKey("");
    setNotesDraft("");
  };

  const updateChartNotesInState = (targetChart, nextNotes) => {
    setCharts((prevCharts) =>
      prevCharts.map((chart) => {
        if (
          chart.ticker === targetChart.ticker &&
          chart.date === targetChart.date &&
          chart.filename === targetChart.filename
        ) {
          return { ...chart, notes: nextNotes };
        }
        return chart;
      })
    );

    setPreviewChart((prevPreviewChart) => {
      if (
        prevPreviewChart &&
        prevPreviewChart.ticker === targetChart.ticker &&
        prevPreviewChart.date === targetChart.date &&
        prevPreviewChart.filename === targetChart.filename
      ) {
        return { ...prevPreviewChart, notes: nextNotes };
      }
      return prevPreviewChart;
    });
  };

  const updateChartChecklistInState = (targetChart, nextChecklist) => {
    setCharts((prevCharts) =>
      prevCharts.map((chart) => {
        if (
          chart.ticker === targetChart.ticker &&
          chart.date === targetChart.date &&
          chart.filename === targetChart.filename
        ) {
          return { ...chart, checklist: nextChecklist };
        }
        return chart;
      })
    );

    setPreviewChart((prevPreviewChart) => {
      if (
        prevPreviewChart &&
        prevPreviewChart.ticker === targetChart.ticker &&
        prevPreviewChart.date === targetChart.date &&
        prevPreviewChart.filename === targetChart.filename
      ) {
        return { ...prevPreviewChart, checklist: nextChecklist };
      }
      return prevPreviewChart;
    });
  };

  const saveChartNotes = async (chart) => {
    setError("");
    try {
      setIsSavingNotes(true);
      const response = await fetchJson(
        `/api/charts/${encodeURIComponent(chart.ticker)}/${encodeURIComponent(
          chart.date
        )}/${encodeURIComponent(chart.filename)}/notes`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ notes: notesDraft }),
        }
      );
      updateChartNotesInState(chart, response.chart?.notes || "");
      cancelEditingNotes();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSavingNotes(false);
    }
  };

  const toggleChartChecklistFlag = async (chart, key) => {
    setError("");
    const nextChecklist = {
      ...buildEmptyChecklist(),
      ...(chart.checklist || {}),
      [key]: !chartHasFlag(chart, key),
    };

    try {
      setIsSavingChecklist(true);
      const response = await fetchJson(
        `/api/charts/${encodeURIComponent(chart.ticker)}/${encodeURIComponent(
          chart.date
        )}/${encodeURIComponent(chart.filename)}/notes`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            notes: chart.notes || "",
            checklist: nextChecklist,
          }),
        }
      );
      updateChartChecklistInState(chart, response.chart?.checklist || nextChecklist);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSavingChecklist(false);
    }
  };

  const updateZoom = (nextZoom) => {
    const clampedZoom = clampZoom(nextZoom);
    setPreviewZoom(clampedZoom);
    if (clampedZoom === 1) {
      const nextPan = { x: 0, y: 0 };
      panRef.current = nextPan;
      setPreviewPan(nextPan);
    }
  };

  const handleZoomIn = () => updateZoom(previewZoom + 0.25);

  const handleZoomOut = () => updateZoom(previewZoom - 0.25);

  const handleWheelZoom = (event) => {
    event.preventDefault();
    const step = event.deltaY < 0 ? 0.2 : -0.2;
    updateZoom(previewZoom + step);
  };

  const beginPan = (event) => {
    if (previewZoom <= 1 || event.button !== 0) {
      return;
    }
    event.preventDefault();
    setIsPanning(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    panStartRef.current = {
      x: event.clientX,
      y: event.clientY,
      panX: panRef.current.x,
      panY: panRef.current.y,
    };
  };

  const continuePan = (event) => {
    if (!isPanning) {
      return;
    }
    const nextPan = {
      x: panStartRef.current.panX + (event.clientX - panStartRef.current.x),
      y: panStartRef.current.panY + (event.clientY - panStartRef.current.y),
    };
    panRef.current = nextPan;
    setPreviewPan(nextPan);
  };

  const stopPan = (event) => {
    if (
      event &&
      event.currentTarget.hasPointerCapture &&
      event.currentTarget.hasPointerCapture(event.pointerId)
    ) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setIsPanning(false);
  };

  const toggleModalFullscreen = async () => {
    if (!modalRef.current) {
      return;
    }

    try {
      if (document.fullscreenElement === modalRef.current) {
        await document.exitFullscreen();
      } else if (!document.fullscreenElement) {
        await modalRef.current.requestFullscreen();
      }
    } catch {
      // no-op when fullscreen is unavailable
    }
  };


  const checklistRows = useMemo(() => {
    const rowOne = CHECKLIST_FIELDS.filter((field) => field.row === 1);
    const rowTwo = CHECKLIST_FIELDS.filter((field) => field.row === 2);
    return [rowOne, rowTwo];
  }, []);

  const selectedChecklistFilterKeys = useMemo(
    () => CHECKLIST_FIELDS.filter((field) => activeChecklistFilters[field.key]).map((field) => field.key),
    [activeChecklistFilters]
  );

  const filteredCharts = useMemo(() => {
    if (selectedChecklistFilterKeys.length === 0) {
      return charts;
    }

    return charts.filter((chart) =>
      selectedChecklistFilterKeys.every((key) => chartHasFlag(chart, key))
    );
  }, [charts, selectedChecklistFilterKeys]);

  const groupedCharts = useMemo(() => {
    return filteredCharts.reduce((groups, chart) => {
      if (!groups[chart.date]) {
        groups[chart.date] = [];
      }
      groups[chart.date].push(chart);
      return groups;
    }, {});
  }, [filteredCharts]);

  const sortedDates = useMemo(() => {
    return Object.keys(groupedCharts).sort((a, b) => (a < b ? 1 : -1));
  }, [groupedCharts]);

  const slideshowCharts = useMemo(() => {
    const inDateRange = filteredCharts.filter((chart) => {
      if (slideshowStartDate && chart.date < slideshowStartDate) {
        return false;
      }
      if (slideshowEndDate && chart.date > slideshowEndDate) {
        return false;
      }
      return true;
    });

    const sortDirection = slideshowSortOrder === "oldest" ? 1 : -1;
    return [...inDateRange].sort((chartA, chartB) => {
      if (chartA.date !== chartB.date) {
        return chartA.date < chartB.date ? -1 * sortDirection : 1 * sortDirection;
      }
      return chartA.filename.localeCompare(chartB.filename) * sortDirection;
    });
  }, [filteredCharts, slideshowEndDate, slideshowSortOrder, slideshowStartDate]);

  const activeSlideshowChart = slideshowCharts[slideshowIndex] || null;

  const visibleTickers = useMemo(() => {
    const query = tickerSearch.trim().toUpperCase();
    const filtered = query
      ? tickers.filter((ticker) => ticker.includes(query))
      : [...tickers];

    return filtered.sort((tickerA, tickerB) => {
      if (tickerSortBy === "charts") {
        const chartCountA = Number(chartCountsByTicker[tickerA] ?? 0);
        const chartCountB = Number(chartCountsByTicker[tickerB] ?? 0);
        if (chartCountA !== chartCountB) {
          return tickerSortDirection === "asc"
            ? chartCountA - chartCountB
            : chartCountB - chartCountA;
        }
      }

      const nameComparison = tickerA.localeCompare(tickerB);
      return tickerSortDirection === "asc" ? nameComparison : -nameComparison;
    });
  }, [chartCountsByTicker, tickerSearch, tickerSortBy, tickerSortDirection, tickers]);

  const isLoadingCharts = status === "loading";
  const displayedTicker = isLoadingCharts && chartsTicker ? chartsTicker : selectedTicker;
  const displayedTickerChartCount = displayedTicker
    ? chartCountsByTicker[displayedTicker] ?? charts.length
    : charts.length;
  const displayedTickerMatchingChartCount = filteredCharts.length;
  const displayedTickerChartLabel = displayedTickerChartCount === 1 ? "chart" : "charts";
  const displayedTickerMatchingChartLabel = displayedTickerMatchingChartCount === 1 ? "chart" : "charts";
  const getFinvizUrl = (ticker) => `https://finviz.com/quote.ashx?t=${encodeURIComponent(ticker)}&p=d`;

  const loadTickers = async () => {
    const data = await fetchJson("/api/tickers");
    const nextTickers = data.tickers || [];
    const nextChartCounts = data.chart_counts || {};
    const fallbackTotalCharts = Object.values(nextChartCounts).reduce(
      (sum, count) => sum + Number(count || 0),
      0
    );

    setTickers(nextTickers);
    setChartCountsByTicker(nextChartCounts);
    setTotalCharts(data.total_charts ?? fallbackTotalCharts);

    if (!selectedTicker && nextTickers.length > 0) {
      setSelectedTicker(nextTickers[0]);
    }
  };

  const loadCharts = async (ticker) => {
    if (!ticker) {
      setCharts([]);
      setChartsTicker("");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const data = await fetchJson(`/api/charts/${encodeURIComponent(ticker)}`);
      setCharts(data.charts);
      setChartsTicker(ticker);
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

    const normalizedTicker = formState.ticker.trim().toUpperCase();
    const selectedFile =
      formState.file || event.currentTarget?.querySelector("#file-input")?.files?.[0] || null;

    if (!normalizedTicker || !selectedFile) {
      setError("Please provide a ticker and PNG chart file.");
      return;
    }

    const formData = new FormData();
    formData.append("ticker", normalizedTicker);
    formData.append("date", formState.date);
    formData.append("chart", selectedFile);
    formData.append("notes", formState.notes.trim());
    CHECKLIST_FIELDS.forEach((field) => {
      formData.append(field.key, formState.checklist[field.key] ? "true" : "false");
    });

    try {
      setStatus("uploading");
      await fetchJson("/api/charts", {
        method: "POST",
        body: formData,
      });
      await loadTickers();
      setSelectedTicker(normalizedTicker);
      await loadCharts(normalizedTicker);
      setFormState({
        ticker: "",
        date: "",
        notes: "",
        file: null,
        checklist: buildEmptyChecklist(),
      });
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
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


  useEffect(() => {
    if (!previewChart) {
      return undefined;
    }

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        closeChartPreview();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [previewChart]);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsModalFullscreen(document.fullscreenElement === modalRef.current);
    };

    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  useEffect(() => {
    if (!isSlideshowOpen || !slideshowRef.current) {
      return undefined;
    }

    slideshowRef.current.requestFullscreen().catch(() => {});
    return undefined;
  }, [isSlideshowOpen]);

  useEffect(() => {
    if (!isSlideshowOpen) {
      return undefined;
    }

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        closeSlideshow();
        return;
      }

      if (event.key === "ArrowRight") {
        event.preventDefault();
        goToNextSlideshowChart();
      }

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        goToPreviousSlideshowChart();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isSlideshowOpen, slideshowCharts.length]);

  useEffect(() => {
    if (!isSlideshowOpen) {
      return;
    }

    if (slideshowCharts.length === 0) {
      closeSlideshow();
      return;
    }

    setSlideshowIndex((prevIndex) => Math.min(prevIndex, slideshowCharts.length - 1));
  }, [isSlideshowOpen, slideshowCharts.length]);

  useEffect(() => {
    if (!isSlideshowOpen) {
      return undefined;
    }

    const onFullscreenChange = () => {
      if (document.fullscreenElement !== slideshowRef.current) {
        setIsSlideshowOpen(false);
      }
    };

    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, [isSlideshowOpen]);

  return (
    <div className="app">
      <header className="header">
        <div className="hero">
          <p className="eyebrow">Trading chart library</p>
          <h1>Chart Vault</h1>
          <p className="hero-slogan">Your visual market memory, organized at a glance.</p>
        </div>
      </header>

      <section className="controls">
        <div className="selector">
          <label htmlFor="ticker-search">Ticker library</label>
          <p className="ticker-library-summary">
            {tickers.length} ticker{tickers.length === 1 ? "" : "s"} tracked • {totalCharts} chart
            {totalCharts === 1 ? "" : "s"} stored
          </p>
          <input
            id="ticker-search"
            placeholder="Search ticker (e.g. NVDA)"
            value={tickerSearch}
            onChange={(event) => setTickerSearch(event.target.value.toUpperCase())}
          />

          <div className="ticker-sort-controls">
            <div className="ticker-sort-field">
              <label htmlFor="ticker-sort-by">Sort by</label>
              <select
                id="ticker-sort-by"
                value={tickerSortBy}
                onChange={(event) => setTickerSortBy(event.target.value)}
              >
                <option value="name">Name</option>
                <option value="charts">Charts uploaded</option>
              </select>
            </div>
            <div className="ticker-sort-field">
              <label htmlFor="ticker-sort-direction">Direction</label>
              <select
                id="ticker-sort-direction"
                value={tickerSortDirection}
                onChange={(event) => setTickerSortDirection(event.target.value)}
              >
                <option value="asc">Ascending</option>
                <option value="desc">Descending</option>
              </select>
            </div>
          </div>

          <div className="ticker-table-wrap">
            <table className="ticker-table" aria-label="Stored tickers">
              <thead>
                <tr>
                  <th scope="col">Ticker</th>
                  <th scope="col">Charts</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {visibleTickers.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="ticker-empty">
                      No tickers match your search.
                    </td>
                  </tr>
                ) : (
                  visibleTickers.map((ticker) => {
                    const isActive = ticker === selectedTicker;
                    const tickerChartCount = Number(chartCountsByTicker[ticker] ?? 0);
                    return (
                      <tr key={ticker} className={isActive ? "active-row" : ""}>
                        <td>
                          <a
                            href={getFinvizUrl(ticker)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="ticker-link"
                          >
                            {ticker}
                          </a>
                        </td>
                        <td>{tickerChartCount}</td>
                        <td>
                          <button
                            type="button"
                            className="ticker-row-button"
                            onClick={() => setSelectedTicker(ticker)}
                          >
                            {isActive ? "Selected" : "View"}
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
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
            <div className="date-input-wrap">
              <input
                id="date-input"
                ref={dateInputRef}
                type="date"
                value={formState.date}
                onDoubleClick={handleDateInputDoubleClick}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, date: event.target.value }))
                }
              />
              <button
                type="button"
                className="date-picker-trigger"
                aria-label="Open date picker"
                onClick={() => {
                  if (dateInputRef.current?.showPicker) {
                    dateInputRef.current.showPicker();
                  } else {
                    dateInputRef.current?.focus();
                  }
                }}
              >
                📅
              </button>
            </div>
          </div>
          <div className="upload-field">
            <label htmlFor="notes-input">Notes</label>
            <textarea
              id="notes-input"
              placeholder="Optional notes about this chart setup"
              value={formState.notes}
              onChange={(event) =>
                setFormState((prev) => ({
                  ...prev,
                  notes: event.target.value,
                }))
              }
              rows={3}
            />
          </div>
          <div className="upload-field">
            <label htmlFor="file-input">Chart PNG</label>
            <input
              id="file-input"
              ref={fileInputRef}
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
          <fieldset className="upload-checklist">
            <legend>Checklist</legend>
            {checklistRows.map((row, rowIndex) => (
              <div key={`upload-checklist-row-${rowIndex + 1}`} className="checklist-row">
                {row.map((field) => (
                  <label key={field.key} className="checklist-option">
                    <input
                      type="checkbox"
                      checked={Boolean(formState.checklist[field.key])}
                      onChange={(event) =>
                        setFormState((prev) => ({
                          ...prev,
                          checklist: {
                            ...prev.checklist,
                            [field.key]: event.target.checked,
                          },
                        }))
                      }
                    />
                    <span>{field.label}</span>
                  </label>
                ))}
              </div>
            ))}
          </fieldset>
          <button type="submit" disabled={status === "uploading"}>
            {status === "uploading" ? "Uploading..." : "Save chart"}
          </button>
        </form>
      </section>

      <section className="gallery">
        <div className="gallery-header">
          <div className="gallery-header-main">
            <h2>{displayedTicker ? `${displayedTicker} ${displayedTickerChartLabel}` : "Charts"}</h2>
            <p>
              {displayedTicker
                ? `${displayedTickerChartCount} ${displayedTickerChartLabel} saved for ${displayedTicker}.`
                : "Browse your saved snapshots organized by date."}
            </p>
            {displayedTicker ? (
              <fieldset className="gallery-checklist-filters">
                <legend>Checklist filters</legend>
                <div className="gallery-checklist-filter-options">
                  {checklistRows.map((row, rowIndex) => (
                    <div key={`gallery-checklist-row-${rowIndex + 1}`} className="checklist-row">
                      {row.map((field) => (
                        <label key={field.key} className="checklist-option">
                          <input
                            type="checkbox"
                            checked={Boolean(activeChecklistFilters[field.key])}
                            onChange={(event) =>
                              setActiveChecklistFilters((prev) => ({
                                ...prev,
                                [field.key]: event.target.checked,
                              }))
                            }
                          />
                          <span>{field.label}</span>
                        </label>
                      ))}
                    </div>
                  ))}
                </div>
                {selectedChecklistFilterKeys.length > 0 ? (
                  <p>
                    Showing {displayedTickerMatchingChartCount} matching {displayedTickerMatchingChartLabel}.
                  </p>
                ) : null}
              </fieldset>
            ) : null}
          </div>
          <div className="gallery-header-actions">
            {displayedTicker ? (
              <button
                type="button"
                className="gallery-slideshow-button"
                onClick={openSlideshow}
                disabled={slideshowCharts.length === 0}
              >
                Presentation mode
              </button>
            ) : null}
            {error && <span className="error">{error}</span>}
          </div>
        </div>

        {filteredCharts.length === 0 ? (
          <div className="empty-state">
            {isLoadingCharts
              ? "Loading charts..."
              : charts.length === 0
                ? "Upload your first chart to start building this ticker timeline."
                : "No charts match the selected checklist filters."}
          </div>
        ) : (
          <div className="date-groups-wrap">
            {isLoadingCharts ? (
              <div className="gallery-refreshing">Refreshing {selectedTicker || "charts"}…</div>
            ) : null}
            <div className={`date-groups ${isLoadingCharts ? "is-refreshing" : ""}`.trim()}>
            {sortedDates.map((date) => (
              <div className="date-group" key={date}>
                <div className="date-label">{date}</div>
                <div className="chart-grid">
                  {groupedCharts[date].map((chart) => (
                    <div className="chart-card" key={`${chart.date}-${chart.filename}`}>
                      <div className="chart-checklist-preview" title={buildChecklistSummary(chart.checklist)}>
                        {buildChecklistSummary(chart.checklist)}
                      </div>
                      <button
                        type="button"
                        className="chart-preview-trigger"
                        onClick={() => openChartPreview(chart)}
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
                      <div className="chart-notes-row">
                        <button
                          type="button"
                          className={`chart-notes-preview ${chart.notes ? "" : "chart-notes-preview-empty"}`.trim()}
                          onDoubleClick={() => openChartNotesEditor(chart)}
                          aria-label={
                            chart.notes
                              ? `Double-click to edit notes for ${chart.filename}`
                              : `Double-click to add notes for ${chart.filename}`
                          }
                          title={chart.notes ? "Double-click to edit notes" : "Double-click to add notes"}
                        >
                          {chart.notes ? buildNotesPreview(chart.notes) : "No notes yet."}
                        </button>
                        <button
                          type="button"
                          className="notes-edit-icon"
                          aria-label={`Edit notes for ${chart.filename}`}
                          onClick={() => openChartNotesEditor(chart)}
                        >
                          ✎
                        </button>
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
          </div>
        )}
      </section>

      {previewChart && (
        <div className="chart-modal-overlay" onClick={closeChartPreview}>
          <div
            ref={modalRef}
            className={`chart-modal ${isModalFullscreen ? "is-fullscreen" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-label="Chart image preview. You can resize this modal from its bottom-right corner."
            onClick={(event) => event.stopPropagation()}
          >
            <div className="chart-modal-toolbar">
              <div className="zoom-controls">
                <button type="button" onClick={handleZoomOut} disabled={previewZoom <= 1}>
                  −
                </button>
                <button type="button" onClick={handleZoomIn} disabled={previewZoom >= 4}>
                  +
                </button>
                <button type="button" onClick={resetPreviewTransform}>
                  Reset
                </button>
                <span>{Math.round(previewZoom * 100)}%</span>
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  className="fullscreen-toggle"
                  onClick={toggleModalFullscreen}
                  aria-label={isModalFullscreen ? "Exit fullscreen chart preview" : "Enter fullscreen chart preview"}
                >
                  {isModalFullscreen ? "Exit full screen" : "Full screen"}
                </button>
                <button type="button" className="close-modal" onClick={closeChartPreview}>
                  Close
                </button>
              </div>
            </div>
            <div
              className={`chart-modal-image-viewport ${previewZoom > 1 ? "is-zoomed" : ""}`}
              onWheel={handleWheelZoom}
              onPointerDown={beginPan}
              onPointerMove={continuePan}
              onPointerUp={stopPan}
              onPointerCancel={stopPan}
            >
              <img
                className={`chart-modal-image ${isPanning ? "is-panning" : ""}`}
                src={buildChartPath(previewChart)}
                alt={`${previewChart.ticker} ${previewChart.filename}`}
                style={{
                  transform: `translate(${previewPan.x}px, ${previewPan.y}px) scale(${previewZoom})`,
                }}
              />
            </div>
            <div className="chart-modal-meta">
              <a href={buildChartPath(previewChart)} download={previewChart.filename}>
                {previewChart.filename}
              </a>
              <span className="chart-modal-context">
                {previewChart.ticker} • {previewChart.date}
              </span>
              {!isModalFullscreen && <span className="resize-hint">↘ Drag corner to resize</span>}
            </div>
            <div className="chart-modal-checklist">
              <h3>Checklist</h3>
              <div className="chart-modal-checklist-rows">
                {checklistRows.map((row, rowIndex) => (
                  <ul key={`modal-checklist-row-${rowIndex + 1}`}>
                    {row.map((field) => (
                      <li key={field.key}>
                        <button
                          type="button"
                          className="checklist-chip"
                          onClick={() => toggleChartChecklistFlag(previewChart, field.key)}
                          disabled={isSavingChecklist}
                          aria-pressed={chartHasFlag(previewChart, field.key)}
                          aria-label={`Toggle ${field.label}`}
                        >
                          <span className="checklist-icon">{chartHasFlag(previewChart, field.key) ? "☑" : "☐"}</span>
                          <span className="checklist-label">{field.label}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ))}
              </div>
            </div>
            <div
              className="chart-modal-notes"
              onDoubleClick={() => {
                if (editingNotesKey !== getChartKey(previewChart)) {
                  startEditingNotes(previewChart);
                }
              }}
            >
              <div className="chart-modal-notes-header">
                <h3>Notes</h3>
                {editingNotesKey !== getChartKey(previewChart) ? (
                  <button
                    type="button"
                    className="notes-edit-icon"
                    onClick={() => startEditingNotes(previewChart)}
                    aria-label={`Edit notes for ${previewChart.filename}`}
                  >
                    ✎
                  </button>
                ) : null}
              </div>
              {editingNotesKey === getChartKey(previewChart) ? (
                <div className="chart-notes-editor">
                  <textarea
                    aria-label="Edit chart notes"
                    value={notesDraft}
                    onChange={(event) => setNotesDraft(event.target.value)}
                    rows={4}
                  />
                  <div className="chart-notes-actions">
                    <button
                      type="button"
                      onClick={() => saveChartNotes(previewChart)}
                      disabled={isSavingNotes}
                    >
                      {isSavingNotes ? "Saving..." : "Save notes"}
                    </button>
                    <button
                      type="button"
                      className="notes-cancel"
                      onClick={cancelEditingNotes}
                      disabled={isSavingNotes}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : previewChart.notes ? (
                <p>{previewChart.notes}</p>
              ) : (
                <p className="chart-notes-empty">Double-click to add notes.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {isSlideshowOpen && activeSlideshowChart ? (
        <div className="slideshow-shell" ref={slideshowRef}>
          <div className="slideshow-topbar">
            <div className="slideshow-title-wrap">
              <h3>{displayedTicker} chart gallery</h3>
              <p>
                {slideshowIndex + 1} of {slideshowCharts.length} • Use ← and → arrows to navigate
              </p>
            </div>
            <div className="slideshow-filters">
              <label>
                Order
                <select
                  value={slideshowSortOrder}
                  onChange={(event) => {
                    setSlideshowSortOrder(event.target.value);
                    setSlideshowIndex(0);
                  }}
                >
                  <option value="newest">Newest first</option>
                  <option value="oldest">Oldest first</option>
                </select>
              </label>
              <label>
                From
                <input
                  type="date"
                  value={slideshowStartDate}
                  max={slideshowEndDate || undefined}
                  onChange={(event) => {
                    setSlideshowStartDate(event.target.value);
                    setSlideshowIndex(0);
                  }}
                />
              </label>
              <label>
                To
                <input
                  type="date"
                  value={slideshowEndDate}
                  min={slideshowStartDate || undefined}
                  onChange={(event) => {
                    setSlideshowEndDate(event.target.value);
                    setSlideshowIndex(0);
                  }}
                />
              </label>
              <button type="button" className="slideshow-close" onClick={closeSlideshow}>
                Exit full screen
              </button>
            </div>
          </div>

          <div className="slideshow-stage">
            <button
              type="button"
              className="slideshow-nav previous"
              aria-label="Previous chart"
              onClick={goToPreviousSlideshowChart}
            >
              ‹
            </button>
            <figure className="slideshow-figure">
              <img
                src={buildChartPath(activeSlideshowChart)}
                alt={`${activeSlideshowChart.ticker} on ${activeSlideshowChart.date}`}
              />
              <figcaption>
                <span>{activeSlideshowChart.filename}</span>
                <span>
                  {activeSlideshowChart.ticker} • {activeSlideshowChart.date}
                </span>
              </figcaption>
            </figure>
            <button
              type="button"
              className="slideshow-nav next"
              aria-label="Next chart"
              onClick={goToNextSlideshowChart}
            >
              ›
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
