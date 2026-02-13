import { useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/chartHelpers";
import { parseBatchFilename } from "../lib/batchFilenameParser";
import {
  buildChecklistFieldsForLabel,
  filterQueueByPolicy,
  shouldUploadByPolicy,
  policyToApiPayload,
  rowSkipReason,
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
  const [policy, setPolicy] = useState({ uploadRed: false, uploadYellow: true, uploadNone: false });

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
        (item) =>
          item.file &&
          item.ticker &&
          item.date &&
          (!item.requiresConfirmation || item.isConfirmed)
      ),
    [batchQueue, policy]
  );

  useEffect(() => {
    const state = {
      policy,
      batchQueue: batchQueue.map(({ file, ...rest }) => rest),
    };
    window.localStorage.setItem("classifier_batch_session", JSON.stringify(state));
  }, [batchQueue, policy]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("classifier_batch_session");
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed?.policy) setPolicy(parsed.policy);
      if (Array.isArray(parsed?.batchQueue)) {
        setBatchQueue(parsed.batchQueue.map((item) => ({ ...item, file: null })));
      }
    } catch (_err) {
      // ignore restore issues
    }
  }, []);

  const updateHsv = (rangeName, bound, index, value) => {
    setConfig((prev) => {
      const nextRange = { ...prev[rangeName], [bound]: [...prev[rangeName][bound]] };
      nextRange[bound][index] = Number(value);
      return { ...prev, [rangeName]: nextRange };
    });
  };

  const updateQueueItem = (filename, updates) => {
    setBatchQueue((prev) =>
      prev.map((item) => (item.filename === filename ? { ...item, ...updates } : item))
    );
  };

  const removeQueueItem = (filename) => {
    setBatchQueue((prev) => prev.filter((item) => item.filename !== filename));
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

    const parsedMetadata = files.map((file) => ({
      filename: file.name,
      ...parseBatchFilename(file.name),
    }));

    setBatchStatus("planning");
    setError("");

    try {
      const formData = new FormData();
      files.forEach((file) => formData.append("charts", file));
      Object.entries(policyToApiPayload(policy)).forEach(([k, v]) => formData.append(k, v));
      formData.append("metadata", JSON.stringify(parsedMetadata));
      const payload = await fetchJson("/api/classifier/batch/plan", {
        method: "POST",
        body: formData,
      });

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
            status: item.status || "planned",
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

  const buildIdempotencyKey = async (item) => {
    if (!item.file) {
      return `${item.filename}:${item.label}:${item.ticker}:${item.date}`;
    }
    const data = await item.file.arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", data);
    const hex = Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    return `${item.filename}:${item.file.size}:${item.file.lastModified}:${hex}`;
  };

  const uploadAllowed = async (failedOnly = false) => {
    const candidates = (failedOnly ? allowedUploads.filter((item) => item.uploadState === "failed") : allowedUploads);
    if (!candidates.length) {
      return;
    }

    setBatchStatus("uploading");
    setError("");
    const nextQueue = [...batchQueue];
    const uploadedTickers = new Set();

    for (const item of nextQueue) {
      if (item.error) {
        item.uploadState = "failed";
      } else if (!shouldUploadByPolicy(item.label, policy)) {
        item.uploadState = "skipped_by_policy";
        item.uploadError = rowSkipReason(item, policy);
      }
    }

    for (const item of candidates) {
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
        formData.append("red_candle", checklist.red_candle ? "true" : "false");
        formData.append("yellow_candle", checklist.yellow_candle ? "true" : "false");
        formData.append("idempotency_key", await buildIdempotencyKey(item));

        await fetchJson("/api/charts", { method: "POST", body: formData });
        uploadedTickers.add(item.ticker.trim().toUpperCase());

        const idx = nextQueue.findIndex((q) => q.filename === item.filename);
        if (idx >= 0) {
          nextQueue[idx] = { ...nextQueue[idx], uploadState: "uploaded", uploadError: "" };
        }
      } catch (err) {
        const idx = nextQueue.findIndex((q) => q.filename === item.filename);
        if (idx >= 0) {
          nextQueue[idx] = { ...nextQueue[idx], uploadState: "failed", uploadError: err.message };
        }
      }
    }

    setBatchQueue(nextQueue);
    setBatchStatus("idle");

    if (uploadedTickers.size > 0 && onBatchUploadComplete) {
      await onBatchUploadComplete(Array.from(uploadedTickers));
    }
  };

  const exportDryRunCsv = () => {
    const headers = [
      "filename",
      "parsed_ticker",
      "parsed_date",
      "label",
      "red_pixels",
      "yellow_pixels",
      "will_upload",
      "reason",
    ];
    const rows = batchQueue.map((item) => [
      item.filename,
      item.ticker || "",
      item.date || "",
      item.label || "",
      item.red_pixels ?? "",
      item.yellow_pixels ?? "",
      shouldUploadByPolicy(item.label, policy) ? "true" : "false",
      rowSkipReason(item, policy),
    ]);
    const csv = [headers, ...rows]
      .map((line) => line.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `batch-dry-run-${new Date().toISOString().slice(0, 19).replaceAll(":", "-")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="classifier-tab">
      <div className="classifier-grid">
        <article className="classifier-card">
          <h2>Calibration</h2>
          <label>
            Calibration image
            <input
              type="file"
              accept="image/png,image/*"
              onChange={(event) => setCalibrationFile(event.target.files?.[0] || null)}
            />
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
                    setConfig((prev) => ({
                      ...prev,
                      roi: {
                        ...prev.roi,
                        [key]: Math.max(0, Number(event.target.value) || 0),
                      },
                    }))
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
                          onChange={(event) =>
                            updateHsv(rangeName, bound, index, event.target.value)
                          }
                        />
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className="classifier-metrics">
            <p>
              Red pixels: <strong>{metrics.red_pixels}</strong>
            </p>
            <p>
              Yellow pixels: <strong>{metrics.yellow_pixels}</strong>
            </p>
            <p>
              Predicted: <strong>{metrics.label}</strong>
            </p>
            {calibrationStatus === "loading" ? <p>Refreshing preview…</p> : null}
          </div>

          <button type="button" className="classifier-primary-button" onClick={saveConfig}>
            {saveStatus === "saving"
              ? "Saving config..."
              : saveStatus === "saved"
                ? "Saved"
                : "Save config"}
          </button>
        </article>

        <article className="classifier-card batch-card">
          <div className="batch-header">
            <h2>Batch</h2>
            <p>Phase A classifies and builds a review table. Phase B uploads rows matching policy.</p>
          </div>

          <label className="batch-file-picker">
            <span>Select images</span>
            <input type="file" accept="image/png,image/*" multiple onChange={handleBatchFiles} />
          </label>

          <div className="batch-policy-controls" role="group" aria-label="Batch upload policy">
            <label className="policy-check">
              <input
                type="checkbox"
                checked={policy.uploadRed}
                onChange={(event) =>
                  setPolicy((prev) => ({ ...prev, uploadRed: event.target.checked }))
                }
              />
              <span className="policy-check-indicator" aria-hidden="true" />
              <span>Upload red only</span>
            </label>
            <label className="policy-check">
              <input
                type="checkbox"
                checked={policy.uploadYellow}
                onChange={(event) =>
                  setPolicy((prev) => ({ ...prev, uploadYellow: event.target.checked }))
                }
              />
              <span className="policy-check-indicator" aria-hidden="true" />
              <span>Upload yellow only</span>
            </label>
            <label className="policy-check">
              <input
                type="checkbox"
                checked={policy.uploadNone}
                onChange={(event) =>
                  setPolicy((prev) => ({ ...prev, uploadNone: event.target.checked }))
                }
              />
              <span className="policy-check-indicator" aria-hidden="true" />
              <span>Upload none</span>
            </label>
          </div>

          <p className="batch-summary">
            {batchQueue.length} reviewed • {allowedUploads.length} ready • {batchStatus === "planning" ? "Phase A classifying…" : "Ready"}
          </p>
          <ul className="classifier-queue">
            {batchQueue.map((item) => {
              const canUploadByLabel = shouldUploadByPolicy(item.label, policy);
              const hasMetadata = Boolean(item.ticker && item.date);
              const needsConfirm = item.requiresConfirmation && !item.isConfirmed;

              return (
                <li key={item.filename}>
                  <div className="classifier-queue-main">
                    <div className="queue-row-top">
                      <strong>{item.filename}</strong>
                      <div className="queue-row-actions">
                        <span className={`parse-badge ${item.parseConfidence || "none"}`}>
                          {confidenceBadge[item.parseConfidence || "none"]}
                        </span>
                      </div>
                    </div>

                    {item.error ? (
                      <p>{item.error}</p>
                    ) : (
                      <p className="queue-metrics">
                        Classification: {classificationStatusLabel[item.label] || "None"} ({item.label}) • red: {item.red_pixels} • yellow: {item.yellow_pixels}
                      </p>
                    )}

                    <p className="parse-reason">{item.parseReason}</p>

                    <div className="queue-meta-fields">
                      <label>
                        Ticker
                        <input
                          value={item.ticker || ""}
                          onChange={(event) =>
                            updateQueueItem(item.filename, {
                              ticker: event.target.value.toUpperCase(),
                              isConfirmed: false,
                            })
                          }
                          placeholder="VG"
                        />
                      </label>
                      <label>
                        Date
                        <input
                          type="date"
                          value={item.date || ""}
                          onChange={(event) =>
                            updateQueueItem(item.filename, {
                              date: event.target.value,
                              isConfirmed: false,
                            })
                          }
                        />
                      </label>
                    </div>

                    {item.requiresConfirmation ? (
                      <label className="confirm-parse-checkbox">
                        <input
                          type="checkbox"
                          checked={Boolean(item.isConfirmed)}
                          onChange={(event) =>
                            updateQueueItem(item.filename, { isConfirmed: event.target.checked })
                          }
                        />
                        Confirm parsed/edited metadata
                      </label>
                    ) : null}

                    {item.uploadState === "failed" ? (
                      <p className="status-message">Status: failed — {item.uploadError}</p>
                    ) : null}
                    {item.uploadState === "uploaded" ? <p>Status: uploaded ✅</p> : null}
                    {item.uploadState === "skipped_by_policy" ? <p>Status: skipped_by_policy</p> : null}
                  </div>

                  <div className="queue-side-actions">
                    <span className="queue-status-pill">
                      {item.error
                        ? "error"
                        : !canUploadByLabel
                          ? "blocked"
                          : !hasMetadata
                            ? "missing metadata"
                            : needsConfirm
                              ? "confirm"
                              : "ready"}
                    </span>
                    <button
                      type="button"
                      className="queue-delete-button"
                      onClick={() => removeQueueItem(item.filename)}
                    >
                      Remove
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>

          <button
            type="button"
            className="classifier-primary-button"
            onClick={uploadAllowed}
            disabled={batchStatus === "uploading" || allowedUploads.length === 0}
          >
            {batchStatus === "uploading" ? "Uploading..." : "Phase B: Upload ready items"}
          </button>
          <button
            type="button"
            className="classifier-primary-button"
            onClick={() => uploadAllowed(true)}
            disabled={batchStatus === "uploading" || !allowedUploads.some((item) => item.uploadState === "failed")}
          >
            Retry failed only
          </button>
          <button type="button" className="classifier-primary-button" onClick={exportDryRunCsv}>
            Export dry-run CSV
          </button>
        </article>
      </div>

      <div className="classifier-preview-panel">
        {calibrationPreviewUrl ? (
          <div className="classifier-image-wrap">
            <img
              src={calibrationPreviewUrl}
              alt="Calibration preview"
              onLoad={(event) =>
                setImageSize({
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                })
              }
            />
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
