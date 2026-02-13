import { useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/chartHelpers";
import { filterQueueByPolicy, shouldUploadByPolicy } from "../lib/classifierHelpers";

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

export default function ClassifierTab() {
  const [config, setConfig] = useState(defaultConfig);
  const [calibrationFile, setCalibrationFile] = useState(null);
  const [calibrationPreviewUrl, setCalibrationPreviewUrl] = useState("");
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [metrics, setMetrics] = useState({ red_pixels: 0, yellow_pixels: 0, label: "none" });
  const [calibrationStatus, setCalibrationStatus] = useState("idle");
  const [saveStatus, setSaveStatus] = useState("idle");
  const [error, setError] = useState("");

  const [batchFiles, setBatchFiles] = useState([]);
  const [batchQueue, setBatchQueue] = useState([]);
  const [batchStatus, setBatchStatus] = useState("idle");
  const [policy, setPolicy] = useState({ uploadRed: false, uploadYellow: true, skipNone: true });

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

  const allowedUploads = useMemo(() => filterQueueByPolicy(batchQueue, policy), [batchQueue, policy]);

  const updateHsv = (rangeName, bound, index, value) => {
    setConfig((prev) => {
      const nextRange = { ...prev[rangeName], [bound]: [...prev[rangeName][bound]] };
      nextRange[bound][index] = Number(value);
      return { ...prev, [rangeName]: nextRange };
    });
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
    setBatchStatus("planning");
    setError("");
    try {
      const formData = new FormData();
      files.forEach((file) => formData.append("charts", file));
      const payload = await fetchJson("/api/classifier/batch/plan", { method: "POST", body: formData });
      setBatchQueue((payload.results || []).map((item, index) => ({ ...item, file: files[index] || null })));
    } catch (err) {
      setError(err.message);
      setBatchQueue([]);
    } finally {
      setBatchStatus("idle");
    }
  };

  const handleBatchFiles = (event) => {
    const files = Array.from(event.target.files || []);
    setBatchFiles(files);
    planBatch(files);
  };

  const uploadAllowed = async () => {
    const queue = filterQueueByPolicy(batchQueue, policy).filter((item) => item.file);
    if (!queue.length) {
      return;
    }

    setBatchStatus("uploading");
    setError("");
    const nextQueue = [...batchQueue];

    for (const item of queue) {
      try {
        const formData = new FormData();
        formData.append("ticker", item.ticker || "UNKNOWN");
        formData.append("date", item.date || "");
        formData.append("chart", item.file);
        formData.append("notes", "Uploaded by classifier tab");
        formData.append("classification_label", item.label);
        formData.append("classification_red_pixels", String(item.red_pixels || 0));
        formData.append("classification_yellow_pixels", String(item.yellow_pixels || 0));
        await fetchJson("/api/charts", { method: "POST", body: formData });
        const idx = nextQueue.findIndex((q) => q.filename === item.filename);
        if (idx >= 0) nextQueue[idx] = { ...nextQueue[idx], uploadState: "uploaded" };
      } catch (err) {
        const idx = nextQueue.findIndex((q) => q.filename === item.filename);
        if (idx >= 0) nextQueue[idx] = { ...nextQueue[idx], uploadState: "failed", uploadError: err.message };
      }
    }

    setBatchQueue(nextQueue);
    setBatchStatus("idle");
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
                    setConfig((prev) => ({
                      ...prev,
                      roi: { ...prev.roi, [key]: Math.max(0, Number(event.target.value) || 0) },
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

          <button type="button" onClick={saveConfig}>
            {saveStatus === "saving" ? "Saving config..." : saveStatus === "saved" ? "Saved" : "Save config"}
          </button>
        </article>

        <article className="classifier-card">
          <h2>Batch</h2>
          <label>
            Select images
            <input type="file" accept="image/png,image/*" multiple onChange={handleBatchFiles} />
          </label>
          <div className="batch-policy-controls">
            <label><input type="checkbox" checked={policy.uploadRed} onChange={(event) => setPolicy((prev) => ({ ...prev, uploadRed: event.target.checked }))} /> Upload red</label>
            <label><input type="checkbox" checked={policy.uploadYellow} onChange={(event) => setPolicy((prev) => ({ ...prev, uploadYellow: event.target.checked }))} /> Upload yellow</label>
            <label><input type="checkbox" checked={policy.skipNone} onChange={(event) => setPolicy((prev) => ({ ...prev, skipNone: event.target.checked }))} /> Skip none</label>
          </div>

          <p>{batchFiles.length} file(s) selected • {allowedUploads.length} allowed by current policy</p>
          {batchStatus === "planning" ? <p>Classifying queue…</p> : null}

          <ul className="classifier-queue">
            {batchQueue.map((item) => (
              <li key={item.filename}>
                <div>
                  <strong>{item.filename}</strong>
                  {item.error ? <p>{item.error}</p> : <p>{item.label} • red: {item.red_pixels} • yellow: {item.yellow_pixels}</p>}
                </div>
                <span>{item.error ? "error" : shouldUploadByPolicy(item.label, policy) ? "will upload" : "blocked"}</span>
              </li>
            ))}
          </ul>

          <button type="button" onClick={uploadAllowed} disabled={batchStatus === "uploading" || allowedUploads.length === 0}>
            {batchStatus === "uploading" ? "Uploading..." : "Upload allowed"}
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
