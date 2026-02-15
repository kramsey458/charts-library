import { useEffect, useMemo, useRef, useState } from "react";
import { fetchJson } from "../lib/chartHelpers";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

export default function PipelineTab() {
  const [file, setFile] = useState(null);
  const [tickersText, setTickersText] = useState("");
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [launchUrl, setLaunchUrl] = useState("");
  const [resumeLoading, setResumeLoading] = useState(false);
  const pollDelayRef = useRef(2000);

  useEffect(() => {
    if (!job?.id || TERMINAL.has(job.state)) return;
    const timer = setTimeout(async () => {
      try {
        const next = await fetchJson(`/api/pipeline/jobs/${job.id}`);
        setJob(next);
        pollDelayRef.current = Math.min(10000, pollDelayRef.current + 100);
      } catch {
        pollDelayRef.current = 5000;
      }
    }, pollDelayRef.current);
    return () => clearTimeout(timer);
  }, [job]);

  const createJob = async () => {
    setError("");
    try {
      let payload;
      if (file) {
        const form = new FormData();
        form.append("ticker_file", file);
        payload = await fetchJson("/api/pipeline/jobs", { method: "POST", body: form });
      } else {
        payload = await fetchJson("/api/pipeline/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tickers_text: tickersText }),
        });
      }
      setJob(payload);
    } catch (err) {
      setError(err.message);
    }
  };

  const start = async () => {
    const payload = await fetchJson(`/api/pipeline/jobs/${job.id}/start`, { method: "POST" });
    setJob(payload);
    setLaunchUrl(payload.launch_url || "");
  };

  const resume = async () => {
    setResumeLoading(true);
    setError("");
    try {
      const payload = await fetchJson(`/api/pipeline/jobs/${job.id}/resume-after-login`, { method: "POST" });
      setJob(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setResumeLoading(false);
    }
  };

  const report = useMemo(() => (job ? `data:text/json,${encodeURIComponent(JSON.stringify(job, null, 2))}` : ""), [job]);

  return (
    <section>
      <h2>Pipeline</h2>
      {error ? <p role="alert">{error}</p> : null}
      <label>
        Ticker file (.txt/.csv)
        <input type="file" accept=".txt,.csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />
      </label>
      <label>
        Or tickers text
        <textarea value={tickersText} onChange={(e) => setTickersText(e.target.value)} rows={5} />
      </label>
      <button type="button" onClick={createJob}>Create Job</button>

      {job ? (
        <div>
          <p>State: {job.state}</p>
          <p>Valid tickers: {job.tickers.length}</p>
          <p>Invalid rows: {job.invalid_rows.length}</p>
          {job.state === "draft" ? <button onClick={start}>Start Pipeline</button> : null}
          {job.state === "awaiting_login" ? (
            <div>
              {launchUrl ? <a href={launchUrl} target="_blank" rel="noreferrer">Open Login Session</a> : null}
              <button onClick={resume} disabled={resumeLoading}>{resumeLoading ? "Resuming..." : "I Have Logged In (Resume)"}</button>
              <button onClick={() => fetchJson(`/api/pipeline/jobs/${job.id}/cancel`, { method: "POST" }).then(setJob)}>Cancel Job</button>
            </div>
          ) : null}
          {job.state.startsWith("running") ? (
            <div>
              <p>Captured: {job.progress.captured}/{job.progress.total}</p>
              <p>Failed: {job.progress.failed}</p>
            </div>
          ) : null}
          {job?.zip_download_url ? (
            <p>
              <a href={job.zip_download_url} target="_blank" rel="noreferrer">Download chart images (.zip)</a>
            </p>
          ) : null}
          {TERMINAL.has(job.state) ? <a href={report} download={`pipeline-${job.id}.json`}>Download report JSON</a> : null}
        </div>
      ) : null}
    </section>
  );
}
