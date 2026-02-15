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
  const [policy, setPolicy] = useState({ upload_red: true, upload_yellow: true, skip_none: true });
  const [overrides, setOverrides] = useState({});
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

  const submitDecision = async () => {
    const payload = await fetchJson(`/api/pipeline/jobs/${job.id}/upload-decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ policy, overrides }),
    });
    setJob(payload);
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
              <p>Classified: {job.progress.classified}</p>
              <p>Uploaded: {job.progress.uploaded}</p>
            </div>
          ) : null}
          {job.state === "awaiting_upload_decision" ? (
            <div>
              <label><input type="checkbox" checked={policy.upload_red} onChange={(e)=>setPolicy((p)=>({...p, upload_red:e.target.checked}))}/>Upload red</label>
              <label><input type="checkbox" checked={policy.upload_yellow} onChange={(e)=>setPolicy((p)=>({...p, upload_yellow:e.target.checked}))}/>Upload yellow</label>
              <button onClick={submitDecision}>Upload approved charts</button>
              <table>
                <thead><tr><th>Ticker</th><th>Label</th><th>Override</th></tr></thead>
                <tbody>
                  {job.items.map((item) => (
                    <tr key={item.ticker}>
                      <td>{item.ticker}</td><td>{item.label || "-"}</td>
                      <td>
                        <select value={overrides[item.ticker] || ""} onChange={(e)=>setOverrides((prev)=>({...prev,[item.ticker]:e.target.value}))}>
                          <option value="">Recommended</option>
                          <option value="upload">Upload</option>
                          <option value="skip">Skip</option>
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {TERMINAL.has(job.state) ? <a href={report} download={`pipeline-${job.id}.json`}>Download report JSON</a> : null}
        </div>
      ) : null}
    </section>
  );
}
