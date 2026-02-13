import { useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/chartHelpers";
import { parseBatchFilename } from "../lib/batchFilenameParser";
import {
  buildChecklistFieldsForLabel,
  filterQueueByPolicy,
  shouldUploadByPolicy,
} from "../lib/classifierHelpers";

const defaultConfig = {
  roi: { x: 0, y: 0, width: 200, height: 120 },
  red_range_1: { lower: [0, 80, 80], upper: [10, 255, 255] },
  red_range_2: { lower: [170, 80, 80], upper: [180, 255, 255] },
  yellow_range: { lower: [18, 80, 80], upper: [40, 255, 255] },
  min_pixels: 50,
  dominance_ratio: 1.2,
};

const rangeFields = ["red_range_1", "red_range_2", "yellow_range"];
const hsvKeys = ["H", "S", "V"];

const confidenceBadge = {
  high: "High confidence",
  medium: "Needs confirmation",
  none: "Parse failed",
};

const classificationStatusLabel = {
  red: "Red Candle",
  yellow: "Yellow Candle",
  none: "None",
};

const SORTABLE_COLUMNS = new Set(["filename", "ticker", "date", "label", "red_pixels", "yellow_pixels", "decision_reason"]);

export default function ClassifierTab({ onBatchUploadComplete }) {
  const [config, setConfig] = useState(defaultConfig);
  const [calibrationFile, setCalibrationFile] = useState(null);
  const [calibrationPreviewUrl, setCalibrationPreviewUrl] = useState("");
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [metrics, setMetrics] = useState({ red_pixels: 0, yellow_pixels: 0, label: "none" });
  const [calibrationStatus, setCalibrationStatus] = useState("idle");
  const [saveStatus, setSaveStatus] = useState("idle");
  const [error, setError] = useState("");

  const [batchQueue, setBatchQueue] = useState([]);
  const [batchStatus, setBatchStatus] = useState("idle");
  const [policy, setPolicy] = useState({ uploadRed: false, uploadYellow: true, skipNone: true });
  const [filterText, setFilterText] = useState("");
  const [reasonFilter, setReasonFilter] = useState("all");
  const [sortBy, setSortBy] = useState("date");
  const [sortDirection, setSortDirection] = useState("desc");

  useEffect(() => {
    fetchJson("/api/classifier/config")
      .then((payload) => {
        if (payload?.config) {
          setConfig(payload.config);
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!calibrationFile) {
      setCalibrationPreviewUrl("");
      return;
    }
    const url = URL.createObjectURL(calibrationFile);
    setCalibrationPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [calibrationFile]);

  useEffect(() => {
    if (!calibrationFile) {
      return;
    }
    const timer = setTimeout(async () => {
      setCalibrationStatus("loading");
      setError("");
      try {
        const formData = new FormData();
        formData.append("image", calibrationFile);
        formData.append("config", JSON.stringify(config));
        const result = await fetchJson("/api/classifier/preview", { method: "POST", body: formData });
        setMetrics({
          red_pixels: result.red_pixels ?? 0,
          yellow_pixels: result.yellow_pixels ?? 0,
          label: result.label ?? "none",
        });
      } catch (err) {
        setError(err.message);
      } finally {
        setCalibrationStatus("idle");
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [calibrationFile, config]);

  const roiStyle = useMemo(() => {
    if (!imageSize.width || !imageSize.height) {
      return null;
    }
    return {
      left: `${(config.roi.x / imageSize.width) * 100}%`,
      top: `${(config.roi.y / imageSize.height) * 100}%`,
      width: `${(config.roi.width / imageSize.width) * 100}%`,
      height: `${(config.roi.height / imageSize.height) * 100}%`,
    };
  }, [config.roi, imageSize]);

  const allowedUploads = useMemo(
    () =>
      filterQueueByPolicy(batchQueue, policy).filter(
        (item) => item.file && item.ticker && item.date && (!item.requiresConfirmation || item.isConfirmed)
      ),
    [batchQueue, policy]
  );

  const reasonOptions = useMemo(
    () => Array.from(new Set(batchQueue.map((item) => item.decision_reason).filter(Boolean))),
    [batchQueue]
  );

  const visibleQueue = useMemo(() => {
    const query = filterText.trim().toLowerCase();
    const filtered = batchQueue.filter((item) => {
      if (query) {
        const haystack = `${item.filename} ${item.ticker || ""} ${item.date || ""} ${item.label || ""} ${item.decision_reason || ""}`.toLowerCase();
        if (!haystack.includes(query)) {
          return false;
        }
      }
      if (reasonFilter !== "all" && item.decision_reason !== reasonFilter) {
        return false;
      }
      return true;
    });

    return [...filtered].sort((a, b) => {
      const left = a[sortBy] ?? "";
      const right = b[sortBy] ?? "";
      const direction = sortDirection === "asc" ? 1 : -1;
      if (typeof left === "number" || typeof right === "number") {
        return ((Number(left) || 0) - (Number(right) || 0)) * direction;
      }
      return String(left).localeCompare(String(right)) * direction;
    });
  }, [batchQueue, filterText, reasonFilter, sortBy, sortDirection]);

  const updateHsv = (rangeName, bound, index, value) => {
    setConfig((prev) => {
      const nextRange = { ...prev[rangeName], [bound]: [...prev[rangeName][bound]] };
      nextRange[bound][index] = Number(value);
      return { ...prev, [rangeName]: nextRange };
    });
  };

  const updateQueueItem = (filename, updates) => {
    setBatchQueue((prev) => prev.map((item) => (item.filename === filename ? { ...item, ...updates } : item)));
  };

  const removeQueueItem = (filename) => setBatchQueue((prev) => prev.filter((item) => item.filename !== filename));

  const toggleSort = (column) => {
    if (!SORTABLE_COLUMNS.has(column)) return;
    if (sortBy === column) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortBy(column);
    setSortDirection(column === "date" ? "desc" : "asc");
  };

  const saveConfig = async () => {
    setSaveStatus("saving");
    setError("");
    try {
      await fetchJson("/api/classifier/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 1200);
    } catch (err) {
      setError(err.message);
      setSaveStatus("idle");
    }
  };

  const planBatch = async (files) => {
    if (!files.length) {
      setBatchQueue([]);
      return;
    }

    const parsedMetadata = files.map((file) => ({ filename: file.name, ...parseBatchFilename(file.name) }));
    setBatchStatus("planning");
    setError("");

    try {
      const formData = new FormData();
      files.forEach((file) => formData.append("charts", file));
      const payload = await fetchJson("/api/classifier/batch/plan", { method: "POST", body: formData });

      setBatchQueue(
        (payload.results || []).map((item, index) => {
          const parsed = parsedMetadata[index] || parseBatchFilename(item.filename);
          return {
            ...item,
            file: files[index] || null,
            ticker: parsed.ticker || item.ticker || "",
            date: parsed.date || item.date || "",
            parseConfidence: parsed.confidence,
            parseReason: parsed.reason,
            requiresConfirmation: parsed.requiresConfirmation,
            isConfirmed: !parsed.requiresConfirmation,
            markedMisclassified: false,
            feedbackNote: "",
          };
        })
      );
    } catch (err) {
      setError(err.message);
      setBatchQueue([]);
    } finally {
      setBatchStatus("idle");
    }
  };

  const handleBatchFiles = (event) => {
    const files = Array.from(event.target.files || []);
    planBatch(files);
  };

  const uploadAllowed = async () => {
    if (!allowedUploads.length) return;
    setBatchStatus("uploading");
    setError("");
    const nextQueue = [...batchQueue];
    const uploadedTickers = new Set();

    for (const item of allowedUploads) {
      try {
        const checklist = buildChecklistFieldsForLabel(item.label);
        const formData = new FormData();
        formData.append("ticker", item.ticker.trim().toUpperCase());
        formData.append("date", item.date);
        formData.append("chart", item.file);
        formData.append("notes", "Uploaded by classifier tab");
        formData.append("classification_label", item.label);
        formData.append("classification_red_pixels", String(item.red_pixels || 0));
        formData.append("classification_yellow_pixels", String(item.yellow_pixels || 0));
        formData.append("classification_decision_reason", item.decision_reason || "");
        formData.append("classification_marked_misclassified", item.markedMisclassified ? "true" : "false");
        formData.append("classification_feedback_note", item.feedbackNote || "");
        formData.append("red_candle", checklist.red_candle ? "true" : "false");
        formData.append("yellow_candle", checklist.yellow_candle ? "true" : "false");

        await fetchJson("/api/charts", { method: "POST", body: formData });
        uploadedTickers.add(item.ticker.trim().toUpperCase());

        const idx = nextQueue.findIndex((q) => q.filename === item.filename);
        if (idx >= 0) nextQueue[idx] = { ...nextQueue[idx], uploadState: "uploaded", uploadError: "" };
      } catch (err) {
        const idx = nextQueue.findIndex((q) => q.filename === item.filename);
        if (idx >= 0) nextQueue[idx] = { ...nextQueue[idx], uploadState: "failed", uploadError: err.message };
      }
    }

    setBatchQueue(nextQueue);
    setBatchStatus("idle");
    if (uploadedTickers.size > 0 && onBatchUploadComplete) {
      await onBatchUploadComplete(Array.from(uploadedTickers));
    }
  };

  return (
    <section className="classifier-tab">
      <div className="classifier-grid">
        <article className="classifier-card">
          <h2>Calibration</h2>
          <label>
            Calibration image
            <input type="file" accept="image/png,image/*" onChange={(event) => setCalibrationFile(event.target.files?.[0] || null)} />
          </label>

          <div className="classifier-roi-controls">
            {["x", "y", "width", "height"].map((key) => (
              <label key={key}>
                ROI {key}
                <input
                  type="number"
                  min={0}
                  value={config.roi[key]}
                  onChange={(event) =>
                    setConfig((prev) => ({ ...prev, roi: { ...prev.roi, [key]: Math.max(0, Number(event.target.value) || 0) } }))
                  }
                />
              </label>
            ))}
          </div>

          <div className="classifier-hsv-controls">
            {rangeFields.map((rangeName) => (
              <div key={rangeName} className="hsv-range-block">
                <h4>{rangeName}</h4>
                {["lower", "upper"].map((bound) => (
                  <div key={`${rangeName}-${bound}`} className="hsv-bound-row">
                    <span>{bound}</span>
                    {hsvKeys.map((label, index) => (
                      <label key={`${rangeName}-${bound}-${label}`}>
                        {label}
                        <input
                          type="number"
                          min={0}
                          max={index === 0 ? 180 : 255}
                          value={config[rangeName][bound][index]}
                          onChange={(event) => updateHsv(rangeName, bound, index, event.target.value)}
                        />
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="classifier-metrics">
            <p>Red pixels: <strong>{metrics.red_pixels}</strong></p>
            <p>Yellow pixels: <strong>{metrics.yellow_pixels}</strong></p>
            <p>Predicted: <strong>{metrics.label}</strong></p>
            {calibrationStatus === "loading" ? <p>Refreshing preview…</p> : null}
          </div>

          <button type="button" className="classifier-primary-button" onClick={saveConfig}>
            {saveStatus === "saving" ? "Saving config..." : saveStatus === "saved" ? "Saved" : "Save config"}
          </button>
        </article>

        <article className="classifier-card batch-card">
          <div className="batch-header">
            <h2>Batch review</h2>
            <p>Review classifier outputs, pixel counts, and reason codes before upload.</p>
          </div>

          <label className="batch-file-picker">
            <span>Select images</span>
            <input type="file" accept="image/png,image/*" multiple onChange={handleBatchFiles} />
          </label>

          <div className="batch-policy-controls" role="group" aria-label="Batch upload policy">
            <label className="policy-check"><input type="checkbox" checked={policy.uploadRed} onChange={(event) => setPolicy((prev) => ({ ...prev, uploadRed: event.target.checked }))} /><span className="policy-check-indicator" aria-hidden="true" /><span>Upload red only</span></label>
            <label className="policy-check"><input type="checkbox" checked={policy.uploadYellow} onChange={(event) => setPolicy((prev) => ({ ...prev, uploadYellow: event.target.checked }))} /><span className="policy-check-indicator" aria-hidden="true" /><span>Upload yellow only</span></label>
            <label className="policy-check"><input type="checkbox" checked={policy.skipNone} onChange={(event) => setPolicy((prev) => ({ ...prev, skipNone: event.target.checked }))} /><span className="policy-check-indicator" aria-hidden="true" /><span>Skip none</span></label>
          </div>

          <div className="classifier-review-controls">
            <input value={filterText} onChange={(event) => setFilterText(event.target.value)} placeholder="Filter filename/ticker/date/reason" />
            <select value={reasonFilter} onChange={(event) => setReasonFilter(event.target.value)}>
              <option value="all">All reasons</option>
              {reasonOptions.map((reason) => <option key={reason} value={reason}>{reason}</option>)}
            </select>
          </div>

          <p className="batch-summary">{batchQueue.length} queued • {allowedUploads.length} ready • {batchStatus === "planning" ? "Classifying…" : "Ready"}</p>

          <div className="classifier-review-table-wrap">
            <table className="classifier-review-table" aria-label="Batch review table">
              <thead>
                <tr>
                  {["filename", "ticker", "date", "label", "red_pixels", "yellow_pixels", "decision_reason"].map((column) => (
                    <th key={column}><button type="button" className="table-sort-button" onClick={() => toggleSort(column)}>{column}{sortBy === column ? (sortDirection === "asc" ? " ↑" : " ↓") : ""}</button></th>
                  ))}
                  <th>metadata</th>
                  <th>feedback</th>
                  <th>actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleQueue.map((item) => {
                  const canUploadByLabel = shouldUploadByPolicy(item.label, policy);
                  const hasMetadata = Boolean(item.ticker && item.date);
                  const needsConfirm = item.requiresConfirmation && !item.isConfirmed;
                  return (
                    <tr key={item.filename}>
                      <td>{item.filename}</td>
                      <td><input value={item.ticker || ""} onChange={(event) => updateQueueItem(item.filename, { ticker: event.target.value.toUpperCase(), isConfirmed: false })} /></td>
                      <td><input type="date" value={item.date || ""} onChange={(event) => updateQueueItem(item.filename, { date: event.target.value, isConfirmed: false })} /></td>
                      <td>{classificationStatusLabel[item.label] || "None"}</td>
                      <td>{item.red_pixels}</td>
                      <td>{item.yellow_pixels}</td>
                      <td>{item.decision_reason || "-"}</td>
                      <td>
                        <span className={`parse-badge ${item.parseConfidence || "none"}`}>{confidenceBadge[item.parseConfidence || "none"]}</span>
                        <div className="parse-reason">{item.parseReason}</div>
                        {item.requiresConfirmation ? (
                          <label className="confirm-parse-checkbox">
                            <input type="checkbox" checked={Boolean(item.isConfirmed)} onChange={(event) => updateQueueItem(item.filename, { isConfirmed: event.target.checked })} />
                            confirm
                          </label>
                        ) : null}
                      </td>
                      <td>
                        <label className="confirm-parse-checkbox">
                          <input type="checkbox" checked={Boolean(item.markedMisclassified)} onChange={(event) => updateQueueItem(item.filename, { markedMisclassified: event.target.checked })} />
                          mark misclassified
                        </label>
                        {item.markedMisclassified ? (
                          <input placeholder="Optional feedback note" value={item.feedbackNote || ""} onChange={(event) => updateQueueItem(item.filename, { feedbackNote: event.target.value })} />
                        ) : null}
                      </td>
                      <td>
                        <span className="queue-status-pill">{item.error ? "error" : !canUploadByLabel ? "blocked" : !hasMetadata ? "missing metadata" : needsConfirm ? "confirm" : "ready"}</span>
                        <button type="button" className="queue-delete-button" onClick={() => removeQueueItem(item.filename)}>Remove</button>
                        {item.uploadState === "failed" ? <p className="status-message">Upload failed: {item.uploadError}</p> : null}
                        {item.uploadState === "uploaded" ? <p>Uploaded ✅</p> : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <button type="button" className="classifier-primary-button" onClick={uploadAllowed} disabled={batchStatus === "uploading" || allowedUploads.length === 0}>
            {batchStatus === "uploading" ? "Uploading..." : "Upload ready items"}
          </button>
        </article>
      </div>

      <div className="classifier-preview-panel">
        {calibrationPreviewUrl ? (
          <div className="classifier-image-wrap">
            <img src={calibrationPreviewUrl} alt="Calibration preview" onLoad={(event) => setImageSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} />
            {roiStyle ? <div className="classifier-roi-rect" style={roiStyle} /> : null}
          </div>
        ) : (
          <p>Select a calibration image to preview ROI.</p>
        )}
      </div>
      {error ? <p className="status-message">{error}</p> : null}
    </section>
  );
}
