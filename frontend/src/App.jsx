import { useEffect, useMemo, useRef, useState } from "react";

import {
  CHECKLIST_FIELDS,
  buildChartPath,
  buildChecklistSummary,
  buildEmptyChecklist,
  analyzeChart,
  buildNotesPreview,
  chartHasFlag,
  fetchJson,
  getChartKey,
  normalizeAnalysis,
} from "./lib/chartHelpers";
import ClassifierTab from "./components/ClassifierTab";

const emptyState = {
  tickers: [],
  charts: [],
};

export default function App() {
  const [activeTab, setActiveTab] = useState("library");
  const [tickers, setTickers] = useState(emptyState.tickers);
  const [selectedTicker, setSelectedTicker] = useState("");
  const [tickerSearch, setTickerSearch] = useState("");
  const [tickerSortBy, setTickerSortBy] = useState("name");
  const [tickerSortDirection, setTickerSortDirection] = useState("asc");
  const [charts, setCharts] = useState(emptyState.charts);
  const [libraryChecklistFilters, setLibraryChecklistFilters] = useState(buildEmptyChecklist());
  const [activeChecklistFilters, setActiveChecklistFilters] = useState(buildEmptyChecklist());
  const [libraryFilteredChartCounts, setLibraryFilteredChartCounts] = useState({});
  const [isLoadingLibraryFilters, setIsLoadingLibraryFilters] = useState(false);
  const [chartsTicker, setChartsTicker] = useState("");
  const [totalCharts, setTotalCharts] = useState(0);
  const [chartCountsByTicker, setChartCountsByTicker] = useState({});
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [previewChart, setPreviewChart] = useState(null);
  const [previewZoom, setPreviewZoom] = useState(1);
  const [previewPan, setPreviewPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [isSlideshowOpen, setIsSlideshowOpen] = useState(false);
  const [slideshowSortOrder, setSlideshowSortOrder] = useState("newest");
  const [slideshowStartDate, setSlideshowStartDate] = useState("");
  const [slideshowEndDate, setSlideshowEndDate] = useState("");
  const [slideshowIndex, setSlideshowIndex] = useState(0);
  const [isSlideshowEnhanced, setIsSlideshowEnhanced] = useState(true);
  const [editingNotesKey, setEditingNotesKey] = useState("");
  const [notesDraft, setNotesDraft] = useState("");
  const [isSavingNotes, setIsSavingNotes] = useState(false);
  const [isSavingChecklist, setIsSavingChecklist] = useState(false);
  const [isAnalyzingChart, setIsAnalyzingChart] = useState(false);
  const [analysisCopyStatus, setAnalysisCopyStatus] = useState("");
  const [hoveredChart, setHoveredChart] = useState(null);
  const [batchFiles, setBatchFiles] = useState([]);
  const [batchIndex, setBatchIndex] = useState(0);
  const [isBatchModalOpen, setIsBatchModalOpen] = useState(false);
  const [isBatchUploading, setIsBatchUploading] = useState(false);
  const [batchFormState, setBatchFormState] = useState({
    ticker: "",
    date: "",
    notes: "",
    checklist: buildEmptyChecklist(),
  });
  const [formState, setFormState] = useState({
    ticker: "",
    date: "",
    notes: "",
    file: null,
    checklist: buildEmptyChecklist(),
  });
  const dateInputRef = useRef(null);
  const batchDateInputRef = useRef(null);
  const fileInputRef = useRef(null);
  const batchFileInputRef = useRef(null);
  const slideshowRef = useRef(null);
  const panStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });
  const panRef = useRef({ x: 0, y: 0 });

  const currentBatchFile = batchFiles[batchIndex] || null;
  const currentBatchPreviewUrl = useMemo(() => {
    if (!currentBatchFile) {
      return "";
    }
    return URL.createObjectURL(currentBatchFile);
  }, [currentBatchFile]);

  useEffect(() => {
    return () => {
      if (currentBatchPreviewUrl) {
        URL.revokeObjectURL(currentBatchPreviewUrl);
      }
    };
  }, [currentBatchPreviewUrl]);

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

  const handleBatchDateInputDoubleClick = () => {
    setBatchFormState((prev) => ({
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
    setPreviewChart({ ...chart, analysis: normalizeAnalysis(chart.analysis) });
    setEditingNotesKey("");
    setNotesDraft("");
    resetPreviewTransform();
  };

  const openChartNotesEditor = (chart) => {
    openChartPreview(chart);
    startEditingNotes(chart);
  };

  const closeChartPreview = () => {
    setPreviewChart(null);
    setIsPanning(false);
    setEditingNotesKey("");
    setNotesDraft("");
    setAnalysisCopyStatus("");
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

  const updateChartAnalysisInState = (targetChart, nextAnalysis) => {
    const normalizedAnalysis = normalizeAnalysis(nextAnalysis);
    setCharts((prevCharts) =>
      prevCharts.map((chart) => {
        if (getChartKey(chart) !== getChartKey(targetChart)) {
          return chart;
        }
        return { ...chart, analysis: normalizedAnalysis };
      })
    );

    setPreviewChart((prevPreviewChart) => {
      if (
        prevPreviewChart &&
        prevPreviewChart.ticker === targetChart.ticker &&
        prevPreviewChart.date === targetChart.date &&
        prevPreviewChart.filename === targetChart.filename
      ) {
        return { ...prevPreviewChart, analysis: normalizedAnalysis };
      }
      return prevPreviewChart;
    });
  };

  const runChartAnalysis = async (chart) => {
    setError("");
    setAnalysisCopyStatus("");
    try {
      setIsAnalyzingChart(true);
      const updatedChart = await analyzeChart(chart);
      if (updatedChart) {
        updateChartAnalysisInState(chart, updatedChart.analysis);
        if (updatedChart.checklist) {
          updateChartChecklistInState(chart, updatedChart.checklist);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsAnalyzingChart(false);
    }
  };

  const handleAnalyzeChartClick = (chart) => {
    const hasExistingAnalysis = Boolean(chart?.analysis?.text?.trim());
    if (hasExistingAnalysis) {
      const confirmed = window.confirm(
        "AI Analysis has already been run for this chart. Do you want to run the analysis again?"
      );
      if (!confirmed) {
        return;
      }
    }
    runChartAnalysis(chart);
  };

  const copyAnalysisText = async () => {
    const analysisText = previewChart?.analysis?.text || "";
    if (!analysisText) {
      return;
    }
    try {
      await navigator.clipboard.writeText(analysisText);
      setAnalysisCopyStatus("Copied");
    } catch {
      setAnalysisCopyStatus("Copy failed");
    }
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



  const checklistRows = useMemo(() => {
    const rowOne = CHECKLIST_FIELDS.filter((field) => field.row === 1);
    const rowTwo = CHECKLIST_FIELDS.filter((field) => field.row === 2);
    return [rowOne, rowTwo];
  }, []);

  const selectedChecklistFilterKeys = useMemo(
    () => CHECKLIST_FIELDS.filter((field) => activeChecklistFilters[field.key]).map((field) => field.key),
    [activeChecklistFilters]
  );

  const selectedLibraryChecklistFilterKeys = useMemo(
    () => CHECKLIST_FIELDS.filter((field) => libraryChecklistFilters[field.key]).map((field) => field.key),
    [libraryChecklistFilters]
  );

  const appliedChecklistFilterKeys = useMemo(
    () => Array.from(new Set([...selectedChecklistFilterKeys, ...selectedLibraryChecklistFilterKeys])),
    [selectedChecklistFilterKeys, selectedLibraryChecklistFilterKeys]
  );

  const filteredCharts = useMemo(() => {
    if (appliedChecklistFilterKeys.length === 0) {
      return charts;
    }

    return charts.filter((chart) =>
      appliedChecklistFilterKeys.every((key) => chartHasFlag(chart, key))
    );
  }, [appliedChecklistFilterKeys, charts]);

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

  const buildSlideshowChartList = (sourceCharts, sortOrder, startDate, endDate) => {
    const inDateRange = sourceCharts.filter((chart) => {
      if (startDate && chart.date < startDate) {
        return false;
      }
      if (endDate && chart.date > endDate) {
        return false;
      }
      return true;
    });

    const sortDirection = sortOrder === "oldest" ? 1 : -1;
    return [...inDateRange].sort((chartA, chartB) => {
      if (chartA.date !== chartB.date) {
        return chartA.date < chartB.date ? -1 * sortDirection : 1 * sortDirection;
      }
      return chartA.filename.localeCompare(chartB.filename) * sortDirection;
    });
  };

  const slideshowCharts = useMemo(
    () => buildSlideshowChartList(filteredCharts, slideshowSortOrder, slideshowStartDate, slideshowEndDate),
    [filteredCharts, slideshowEndDate, slideshowSortOrder, slideshowStartDate]
  );

  const activeSlideshowChart = slideshowCharts[slideshowIndex] || null;

  const getChartIndexInList = (targetChart, list) =>
    list.findIndex(
      (chart) =>
        chart.ticker === targetChart.ticker &&
        chart.date === targetChart.date &&
        chart.filename === targetChart.filename
    );

  const openSlideshowFromChart = (chart) => {
    if (!chart) {
      return;
    }

    const defaultOrder = "newest";
    const defaultStartDate = "";
    const defaultEndDate = "";
    const sortedCharts = buildSlideshowChartList(
      filteredCharts,
      defaultOrder,
      defaultStartDate,
      defaultEndDate
    );

    const chartIndex = getChartIndexInList(chart, sortedCharts);

    closeChartPreview();
    setSlideshowSortOrder(defaultOrder);
    setSlideshowStartDate(defaultStartDate);
    setSlideshowEndDate(defaultEndDate);
    setSlideshowIndex(chartIndex >= 0 ? chartIndex : 0);
    setIsSlideshowOpen(true);
  };

  const visibleTickers = useMemo(() => {
    const tickersMatchingLibraryFilters = selectedLibraryChecklistFilterKeys.length
      ? tickers.filter((ticker) => Number(libraryFilteredChartCounts[ticker] ?? 0) > 0)
      : tickers;

    const query = tickerSearch.trim().toUpperCase();
    const filtered = query
      ? tickersMatchingLibraryFilters.filter((ticker) => ticker.includes(query))
      : [...tickersMatchingLibraryFilters];

    return filtered.sort((tickerA, tickerB) => {
      if (tickerSortBy === "charts") {
        const chartCountA = selectedLibraryChecklistFilterKeys.length
          ? Number(libraryFilteredChartCounts[tickerA] ?? 0)
          : Number(chartCountsByTicker[tickerA] ?? 0);
        const chartCountB = selectedLibraryChecklistFilterKeys.length
          ? Number(libraryFilteredChartCounts[tickerB] ?? 0)
          : Number(chartCountsByTicker[tickerB] ?? 0);
        if (chartCountA !== chartCountB) {
          return tickerSortDirection === "asc"
            ? chartCountA - chartCountB
            : chartCountB - chartCountA;
        }
      }

      const nameComparison = tickerA.localeCompare(tickerB);
      return tickerSortDirection === "asc" ? nameComparison : -nameComparison;
    });
  }, [
    chartCountsByTicker,
    libraryFilteredChartCounts,
    selectedLibraryChecklistFilterKeys.length,
    tickerSearch,
    tickerSortBy,
    tickerSortDirection,
    tickers,
  ]);

  const isLoadingCharts = status === "loading";
  const displayedTicker = isLoadingCharts && chartsTicker ? chartsTicker : selectedTicker;
  const displayedTickerChartCount = displayedTicker
    ? selectedLibraryChecklistFilterKeys.length
      ? Number(libraryFilteredChartCounts[displayedTicker] ?? 0)
      : chartCountsByTicker[displayedTicker] ?? charts.length
    : charts.length;
  const displayedTickerMatchingChartCount = filteredCharts.length;
  const displayedTickerChartLabel = displayedTickerChartCount === 1 ? "chart" : "charts";
  const displayedTickerMatchingChartLabel = displayedTickerMatchingChartCount === 1 ? "chart" : "charts";
  const getFinvizUrl = (ticker) => `https://finviz.com/quote.ashx?t=${encodeURIComponent(ticker)}&p=d`;

  const normalizeTickerForTradingView = (ticker) => {
    const rawTicker = String(ticker || "").trim();
    const noExchangePrefix = rawTicker.includes(":") ? rawTicker.split(":").pop() : rawTicker;
    const firstToken = noExchangePrefix.split(/[\s,/|]+/)[0] || "";
    return firstToken.toUpperCase().replace(/[^A-Z0-9._-]/g, "");
  };

  const getTradingViewEmbedUrl = (ticker) => {
    const normalizedTicker = normalizeTickerForTradingView(ticker);
    const symbolQuery = normalizedTicker || "SPY";
    return `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(
      symbolQuery
    )}&interval=D&hidesidetoolbar=1&symboledit=1&saveimage=0&theme=dark&style=1&timezone=Etc%2FUTC&studies=[]&withdateranges=1&hideideas=1`;
  };

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
      setCharts((data.charts || []).map((chart) => ({ ...chart, analysis: normalizeAnalysis(chart.analysis) })));
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

  const handleClassifierBatchUploadComplete = async (uploadedTickers = []) => {
    await loadTickers();
    const preferredTicker = uploadedTickers.find((ticker) => ticker)?.trim().toUpperCase();
    const targetTicker = preferredTicker || selectedTicker;
    if (targetTicker) {
      setSelectedTicker(targetTicker);
      await loadCharts(targetTicker);
    }
  };

  useEffect(() => {
    if (selectedLibraryChecklistFilterKeys.length === 0 || tickers.length === 0) {
      setLibraryFilteredChartCounts({});
      setIsLoadingLibraryFilters(false);
      return;
    }

    let isCancelled = false;

    const loadLibraryFilteredCounts = async () => {
      setIsLoadingLibraryFilters(true);
      try {
        const chartCollections = await Promise.all(
          tickers.map(async (ticker) => {
            const data = await fetchJson(`/api/charts/${encodeURIComponent(ticker)}`);
            return [ticker, data.charts || []];
          })
        );

        if (isCancelled) {
          return;
        }

        const nextCounts = chartCollections.reduce((counts, [ticker, tickerCharts]) => {
          counts[ticker] = tickerCharts.filter((chart) =>
            selectedLibraryChecklistFilterKeys.every((key) => chartHasFlag(chart, key))
          ).length;
          return counts;
        }, {});

        setLibraryFilteredChartCounts(nextCounts);
      } catch (err) {
        if (!isCancelled) {
          setError(err.message);
          setLibraryFilteredChartCounts({});
        }
      } finally {
        if (!isCancelled) {
          setIsLoadingLibraryFilters(false);
        }
      }
    };

    loadLibraryFilteredCounts();

    return () => {
      isCancelled = true;
    };
  }, [selectedLibraryChecklistFilterKeys, tickers]);

  useEffect(() => {
    if (!selectedTicker && visibleTickers.length > 0) {
      setSelectedTicker(visibleTickers[0]);
      return;
    }

    if (selectedTicker && visibleTickers.length > 0 && !visibleTickers.includes(selectedTicker)) {
      setSelectedTicker(visibleTickers[0]);
    }
  }, [selectedTicker, visibleTickers]);

  const uploadChart = async ({ ticker, date, notes, file, checklist }) => {
    const normalizedTicker = ticker.trim().toUpperCase();
    const formData = new FormData();
    formData.append("ticker", normalizedTicker);
    formData.append("date", date);
    formData.append("chart", file);
    formData.append("notes", notes.trim());
    CHECKLIST_FIELDS.forEach((field) => {
      formData.append(field.key, checklist[field.key] ? "true" : "false");
    });

    await fetchJson("/api/charts", {
      method: "POST",
      body: formData,
    });

    return normalizedTicker;
  };

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

    try {
      setStatus("uploading");
      const uploadedTicker = await uploadChart({
        ticker: normalizedTicker,
        date: formState.date,
        notes: formState.notes,
        file: selectedFile,
        checklist: formState.checklist,
      });
      await loadTickers();
      setSelectedTicker(uploadedTicker);
      await loadCharts(uploadedTicker);
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

  const closeBatchModal = () => {
    setIsBatchModalOpen(false);
    setBatchFiles([]);
    setBatchIndex(0);
    setBatchFormState({
      ticker: "",
      date: "",
      notes: "",
      checklist: buildEmptyChecklist(),
    });
    if (batchFileInputRef.current) {
      batchFileInputRef.current.value = "";
    }
  };

  const handleBatchFileSelection = (event) => {
    const selectedFiles = Array.from(event.target.files || []).filter((file) =>
      file.type.startsWith("image/")
    );

    if (selectedFiles.length === 0) {
      return;
    }

    setBatchFiles(selectedFiles);
    setBatchIndex(0);
    setBatchFormState({
      ticker: formState.ticker || selectedTicker || "",
      date: formState.date || "",
      notes: "",
      checklist: buildEmptyChecklist(),
    });
    setIsBatchModalOpen(true);
  };

  const handleBatchModalSubmit = async (event) => {
    event.preventDefault();
    setError("");

    const currentFile = currentBatchFile;
    const normalizedTicker = batchFormState.ticker.trim().toUpperCase();

    if (!currentFile || !normalizedTicker || !batchFormState.date) {
      setError("Please add a ticker and date before uploading this chart.");
      return;
    }

    try {
      setIsBatchUploading(true);
      const uploadedTicker = await uploadChart({
        ticker: normalizedTicker,
        date: batchFormState.date,
        notes: batchFormState.notes,
        file: currentFile,
        checklist: batchFormState.checklist,
      });

      const nextIndex = batchIndex + 1;
      if (nextIndex >= batchFiles.length) {
        await loadTickers();
        setSelectedTicker(uploadedTicker);
        await loadCharts(uploadedTicker);
        closeBatchModal();
        return;
      }

      setBatchIndex(nextIndex);
      setBatchFormState((prev) => ({
        ...prev,
        date: "",
        notes: "",
        checklist: buildEmptyChecklist(),
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setIsBatchUploading(false);
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

  const handleDeleteAllCharts = async () => {
    if (tickers.length === 0) {
      return;
    }

    const shouldDeleteAll = window.confirm(
      "Delete ALL charts across the ticker library? This is intended for testing and cannot be undone."
    );

    if (!shouldDeleteAll) {
      return;
    }

    setError("");
    try {
      setStatus("deleting");

      const chartCollections = await Promise.all(
        tickers.map(async (ticker) => {
          const data = await fetchJson(`/api/charts/${encodeURIComponent(ticker)}`);
          return data.charts || [];
        })
      );

      const allCharts = chartCollections.flat();
      await Promise.all(
        allCharts.map((chart) =>
          fetchJson(
            `/api/charts/${encodeURIComponent(chart.ticker)}/${encodeURIComponent(
              chart.date
            )}/${encodeURIComponent(chart.filename)}`,
            { method: "DELETE" }
          )
        )
      );

      setCharts([]);
      setTickers([]);
      setChartCountsByTicker({});
      setTotalCharts(0);
      setSelectedTicker("");
      setPreviewChart(null);
      setLibraryFilteredChartCounts({});
      setTickerSearch("");
      await loadTickers();
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus("idle");
    }
  };


  useEffect(() => {
    if (!previewChart || isSlideshowOpen) {
      return undefined;
    }

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        closeChartPreview();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isSlideshowOpen, previewChart]);

  useEffect(() => {
    const onKeyDown = (event) => {
      const isPresentationShortcut = event.key === "f" || event.key === "F";
      if (!isPresentationShortcut || !hoveredChart || isSlideshowOpen) {
        return;
      }

      const targetTagName = event.target?.tagName;
      const isTypingTarget =
        event.target?.isContentEditable ||
        targetTagName === "INPUT" ||
        targetTagName === "TEXTAREA" ||
        targetTagName === "SELECT";

      if (isTypingTarget) {
        return;
      }

      event.preventDefault();
      openSlideshowFromChart(hoveredChart);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hoveredChart, isSlideshowOpen, filteredCharts]);

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

      if (event.key === "f" || event.key === "F") {
        event.preventDefault();
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

  const previewAnalysisStatus = previewChart?.analysis?.status || "idle";
  const isAnalysisRunning = isAnalyzingChart || previewAnalysisStatus === "running";
  const previewAnalysisStatusTone = isAnalysisRunning ? "analyzing" : previewAnalysisStatus;
  const previewAnalysisStatusLabel = isAnalysisRunning
    ? "Analyzing"
    : previewAnalysisStatus.charAt(0).toUpperCase() + previewAnalysisStatus.slice(1);

  return (
    <div className="app">
      <header className="header">
        <div className="hero">
          <p className="eyebrow">Trading chart library</p>
          <h1>Chart Vault</h1>
          <p className="hero-slogan">Your visual market memory, organized at a glance.</p>
        </div>
      </header>

      <nav className="top-tabs" aria-label="Primary tabs">
        <button
          type="button"
          className={`top-tab ${activeTab === "library" ? "is-active" : ""}`.trim()}
          onClick={() => setActiveTab("library")}
        >
          Library
        </button>
        <button
          type="button"
          className={`top-tab ${activeTab === "classifier" ? "is-active" : ""}`.trim()}
          onClick={() => setActiveTab("classifier")}
        >
          Classifier
        </button>
      </nav>

      {activeTab === "library" ? (
        <>
      <section className="controls">
        <div className="selector">
          <div className="ticker-library-header">
            <label htmlFor="ticker-search">Ticker library</label>
            <button
              type="button"
              className="clear-library-button"
              onClick={handleDeleteAllCharts}
              disabled={status === "deleting" || tickers.length === 0}
            >
              {status === "deleting" ? "Clearing..." : "Delete all charts"}
            </button>
          </div>
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

          <fieldset className="library-checklist-filters">
            <legend>Library checklist filters</legend>
            {checklistRows.map((row, rowIndex) => (
              <div key={`library-checklist-row-${rowIndex + 1}`} className="checklist-row">
                {row.map((field) => (
                  <label key={field.key} className="checklist-option">
                    <input
                      type="checkbox"
                      checked={Boolean(libraryChecklistFilters[field.key])}
                      onChange={(event) =>
                        setLibraryChecklistFilters((prev) => ({
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
          </fieldset>

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
                    const tickerChartCount = selectedLibraryChecklistFilterKeys.length
                      ? Number(libraryFilteredChartCounts[ticker] ?? 0)
                      : Number(chartCountsByTicker[ticker] ?? 0);
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
          {isLoadingLibraryFilters ? (
            <p className="ticker-library-filter-status">Updating ticker matches for checklist filters…</p>
          ) : null}
        </div>

        <form className="upload" onSubmit={handleUpload}>
          <div className="upload-header">
            <h2>Upload chart</h2>
            <button
              type="button"
              className="batch-upload-button"
              onClick={() => batchFileInputRef.current?.click()}
            >
              Batch upload
            </button>
          </div>
          <input
            ref={batchFileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="batch-file-input"
            onChange={handleBatchFileSelection}
          />
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

      {isBatchModalOpen && batchFiles.length > 0 ? (
        <div className="chart-modal-overlay batch-upload-overlay" onClick={closeBatchModal}>
          <div
            className="chart-modal batch-upload-modal is-fullscreen"
            role="dialog"
            aria-modal="true"
            aria-label="Batch upload details"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="chart-modal-toolbar">
              <h3>
                Batch upload ({batchIndex + 1}/{batchFiles.length})
              </h3>
              <button type="button" className="close-modal" onClick={closeBatchModal}>
                Cancel
              </button>
            </div>
            <div className="batch-upload-content">
              <div className="batch-upload-preview">
                {currentBatchPreviewUrl ? (
                  <img src={currentBatchPreviewUrl} alt={currentBatchFile?.name || "Batch chart preview"} />
                ) : null}
              </div>
              <form className="batch-upload-form" onSubmit={handleBatchModalSubmit}>
                <p className="batch-upload-file">File: {currentBatchFile?.name || ""}</p>
                <div className="upload-field">
                  <label htmlFor="batch-ticker-input">Ticker</label>
                  <input
                    id="batch-ticker-input"
                    placeholder="NVDA"
                    value={batchFormState.ticker}
                    onChange={(event) =>
                      setBatchFormState((prev) => ({
                        ...prev,
                        ticker: event.target.value.toUpperCase(),
                      }))
                    }
                    maxLength={6}
                  />
                </div>
                <div className="upload-field">
                  <label htmlFor="batch-date-input">Date</label>
                  <div className="date-input-wrap">
                    <input
                      id="batch-date-input"
                      ref={batchDateInputRef}
                      type="date"
                      value={batchFormState.date}
                      onDoubleClick={handleBatchDateInputDoubleClick}
                      onChange={(event) =>
                        setBatchFormState((prev) => ({ ...prev, date: event.target.value }))
                      }
                    />
                    <button
                      type="button"
                      className="date-picker-trigger"
                      aria-label="Open date picker"
                      onClick={() => {
                        if (batchDateInputRef.current?.showPicker) {
                          batchDateInputRef.current.showPicker();
                        } else {
                          batchDateInputRef.current?.focus();
                        }
                      }}
                    >
                      📅
                    </button>
                  </div>
                </div>
                <div className="upload-field">
                  <label htmlFor="batch-notes-input">Notes</label>
                  <textarea
                    id="batch-notes-input"
                    placeholder="Optional notes about this chart setup"
                    value={batchFormState.notes}
                    onChange={(event) =>
                      setBatchFormState((prev) => ({
                        ...prev,
                        notes: event.target.value,
                      }))
                    }
                    rows={3}
                  />
                </div>
                <fieldset className="upload-checklist">
                  <legend>Checklist</legend>
                  {checklistRows.map((row, rowIndex) => (
                    <div key={`batch-checklist-row-${rowIndex + 1}`} className="checklist-row">
                      {row.map((field) => (
                        <label key={field.key} className="checklist-option">
                          <input
                            type="checkbox"
                            checked={Boolean(batchFormState.checklist[field.key])}
                            onChange={(event) =>
                              setBatchFormState((prev) => ({
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
                <button type="submit" disabled={isBatchUploading}>
                  {isBatchUploading
                    ? "Uploading..."
                    : batchIndex + 1 === batchFiles.length
                      ? "Upload final chart"
                      : "Upload & continue"}
                </button>
              </form>
            </div>
          </div>
        </div>
      ) : null}

      <section className="gallery">
        <div className="gallery-header">
          <div className="gallery-header-main">
            <div className="gallery-controls-panel">
              <div className="gallery-controls-header">
                <div>
                  <h2>
                    {displayedTicker ? (
                      <>
                        <a href={getFinvizUrl(displayedTicker)} target="_blank" rel="noopener noreferrer">
                          {displayedTicker}
                        </a>{" "}
                        {displayedTickerChartLabel}
                      </>
                    ) : (
                      "Charts"
                    )}
                  </h2>
                  <p>
                    {displayedTicker
                      ? `${displayedTickerChartCount} ${displayedTickerChartLabel} saved for ${displayedTicker}.`
                      : "Browse your saved snapshots organized by date."}
                  </p>
                </div>
                {displayedTicker ? (
                  <button
                    type="button"
                    className="gallery-slideshow-button"
                    onClick={openSlideshow}
                    disabled={slideshowCharts.length === 0}
                    aria-label="Open presentation mode"
                    title="Presentation mode"
                  >
                    ⛶
                  </button>
                ) : null}
              </div>
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
                              checked={Boolean(activeChecklistFilters[field.key] || libraryChecklistFilters[field.key])}
                              disabled={Boolean(libraryChecklistFilters[field.key])}
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
                  {selectedLibraryChecklistFilterKeys.length > 0 ? (
                    <p>Library filters are also applied to this chart grid.</p>
                  ) : null}
                </fieldset>
              ) : null}
              {error && <span className="error">{error}</span>}
            </div>
          </div>
          {displayedTicker ? (
            <div className="gallery-chart-panel" aria-label={`${displayedTicker} Live Chart panel`}>
              <div className="gallery-chart-panel-header">
                <h3>{displayedTicker} Live Chart</h3>
                <a href={getFinvizUrl(displayedTicker)} target="_blank" rel="noopener noreferrer">
                  Open in Finviz
                </a>
              </div>
              <div className="gallery-chart-panel-body">
                <iframe
                  title={`${displayedTicker} chart graph`}
                  src={getTradingViewEmbedUrl(displayedTicker)}
                  loading="lazy"
                  allowTransparency="true"
                  referrerPolicy="no-referrer-when-downgrade"
                />
              </div>
            </div>
          ) : null}
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
                      <div className="chart-card-header">
                        <div className="chart-checklist-preview" title={buildChecklistSummary(chart.checklist)}>
                          {buildChecklistSummary(chart.checklist)}
                        </div>
                        <button
                          type="button"
                          className="delete-button"
                          onClick={() => handleDeleteChart(chart)}
                          disabled={status === "deleting"}
                          aria-label={`Delete ${chart.filename}`}
                          title="Delete chart"
                        >
                          🗑️
                        </button>
                      </div>
                      <button
                        type="button"
                        className="chart-preview-trigger"
                        onClick={() => openChartPreview(chart)}
                        onMouseEnter={() => setHoveredChart(chart)}
                        onMouseLeave={() =>
                          setHoveredChart((prev) =>
                            prev && getChartKey(prev) === getChartKey(chart) ? null : prev
                          )
                        }
                        onFocus={() => setHoveredChart(chart)}
                        onBlur={() =>
                          setHoveredChart((prev) =>
                            prev && getChartKey(prev) === getChartKey(chart) ? null : prev
                          )
                        }
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
            className="chart-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Chart image preview"
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
              <h2 className="chart-modal-title">{previewChart.ticker}</h2>
              <div className="modal-actions">
                <button
                  type="button"
                  className="fullscreen-toggle"
                  onClick={() => openSlideshowFromChart(previewChart)}
                  aria-label="Open fullscreen slideshow"
                >
                  Full Screen
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
            <div className="chart-modal-analysis">
              <div className="chart-modal-analysis-header">
                <h4>AI Analysis</h4>
                <span className={`analysis-status analysis-${previewAnalysisStatusTone}`}>
                  {previewAnalysisStatusLabel}
                </span>
              </div>
              <div className="chart-modal-analysis-actions">
                <button
                  type="button"
                  className={previewChart.analysis?.text ? "analysis-rerun-button" : ""}
                  onClick={() => handleAnalyzeChartClick(previewChart)}
                  disabled={isAnalyzingChart}
                >
                  {isAnalyzingChart ? "Analyzing..." : "AI Analysis"}
                </button>
                <button
                  type="button"
                  className="notes-cancel"
                  onClick={copyAnalysisText}
                  disabled={!previewChart.analysis?.text}
                >
                  Copy analysis
                </button>
                {analysisCopyStatus ? <span className="analysis-copy-status">{analysisCopyStatus}</span> : null}
              </div>
              {previewChart.analysis?.error ? <p className="analysis-error">{previewChart.analysis.error}</p> : null}
              {previewChart.analysis?.text ? (
                <pre className="analysis-text">{previewChart.analysis.text}</pre>
              ) : (
                <p className="chart-notes-empty">No analysis yet.</p>
              )}
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
            <p className="slideshow-current-date" aria-live="polite">
              {activeSlideshowChart.date}
            </p>
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
              <button
                type="button"
                className={`slideshow-enhance-toggle ${isSlideshowEnhanced ? "is-active" : ""}`.trim()}
                onClick={() => setIsSlideshowEnhanced((prev) => !prev)}
                aria-pressed={isSlideshowEnhanced}
              >
                {isSlideshowEnhanced ? "Enhanced" : "Enhance"}
              </button>
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
                className={isSlideshowEnhanced ? "is-enhanced" : ""}
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
        </>
      ) : (
        <ClassifierTab onBatchUploadComplete={handleClassifierBatchUploadComplete} />
      )}
    </div>
  );
}
