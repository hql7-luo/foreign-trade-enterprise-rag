import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { IngestionJob, SourceSummary, StagedSource } from "../types";

interface Props { token: string }

export function SourcesPage({ token }: Props) {
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [staged, setStaged] = useState<StagedSource[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [activeJobId, setActiveJobId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const [sourceItems, stagedItems, jobItems] = await Promise.all([api.sources(token), api.stagedSources(token), api.ingestionJobs(token)]);
      setSources(sourceItems); setStaged(stagedItems); setJobs(jobItems);
      const active = jobItems.find((job) => job.status === "pending" || job.status === "running");
      if (active) { setActiveJobId(active.id); setBusy(true); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Sources unavailable"); }
  }
  useEffect(() => { void load(); }, [token]);

  useEffect(() => {
    if (!activeJobId) return;
    let stopped = false;
    const timer = window.setInterval(() => {
      void api.ingestionJob(token, activeJobId).then((job) => {
        if (stopped) return;
        setJobs((items) => [job, ...items.filter((item) => item.id !== job.id)]);
        if (job.status === "completed") {
          setMessage(`Controlled ingestion completed: ${job.result?.chunks ?? 0} chunks indexed.`);
          setActiveJobId(""); setBusy(false); void load();
        } else if (job.status === "failed") {
          setError(job.error_message || "Ingestion failed. Review the backend logs.");
          setActiveJobId(""); setBusy(false);
        } else if (job.status === "cancelled") {
          setMessage("Ingestion cancelled before the index rebuild phase.");
          setActiveJobId(""); setBusy(false);
        }
      }).catch((reason: Error) => {
        if (!stopped) { setError(reason.message); setActiveJobId(""); setBusy(false); }
      });
    }, 1000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [activeJobId, token]);

  async function upload(file: File) {
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await api.stageSource(token, file);
      setMessage(result.status === "blocked" ? "Source blocked. Only finding types were retained." : "Source validated in private staging. It is not authoritative knowledge.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Upload validation failed"); }
    finally { setBusy(false); if (input.current) input.current.value = ""; }
  }

  async function propose(item: StagedSource) {
    setBusy(true); setError("");
    try { const result = await api.proposeStaged(token, item.id); setMessage(`${result.changes.length} review item(s) created. No current facts changed.`); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not create review items"); }
    finally { setBusy(false); }
  }

  async function ingest() {
    setBusy(true); setError(""); setMessage("");
    try {
      const job = await api.ingest(token);
      setJobs((items) => [job, ...items.filter((item) => item.id !== job.id)]);
      setActiveJobId(job.id);
      setMessage("Ingestion queued. You can follow validation, embedding, and index progress below.");
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Ingestion failed"); setBusy(false); }
  }

  async function cancel(job: IngestionJob) {
    setError("");
    try {
      const updated = await api.cancelIngestion(token, job.id);
      setJobs((items) => [updated, ...items.filter((item) => item.id !== updated.id)]);
      if (updated.status === "cancelled") { setActiveJobId(""); setBusy(false); }
      setMessage(updated.status === "cancelled" ? "Pending ingestion cancelled." : "Cancellation requested. The job will stop at the next safe checkpoint.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not cancel ingestion"); }
  }

  return (
    <div className="page-stack">
      <header className="page-header"><div><p className="eyebrow">Administrator workspace</p><h1>Knowledge sources</h1><p>Validate first. Stage privately. Promote facts only through review.</p></div><button className="secondary-button" type="button" onClick={() => void ingest()} disabled={busy}>Re-index configured source</button></header>
      {message && <div className="success-banner" role="status">{message}</div>}{error && <div className="inline-error" role="alert">{error}</div>}
      <section className="source-section" aria-labelledby="ingestion-jobs-heading">
        <div className="section-heading"><div><p className="eyebrow">Reliable operations</p><h2 id="ingestion-jobs-heading">Ingestion jobs</h2></div><span>{jobs.length} recent jobs</span></div>
        <div className="job-list" aria-live="polite">
          {jobs.slice(0, 5).map((job) => <article className="job-card" key={job.id}>
            <div className="job-summary"><span className={`review-state state-${job.status}`}>{job.status}</span><strong>{job.phase.replaceAll("_", " ")}</strong><small>{new Date(job.created_at).toLocaleString()} · {job.created_by}</small></div>
            <div className="job-progress"><div><span style={{ width: `${job.progress}%` }} /></div><strong>{job.progress}%</strong></div>
            {job.error_message && <p className="job-error" role="alert">{job.error_message}</p>}
            {job.result && <p>{job.result.products} products · {job.result.chunks} chunks · source hashes {job.result.source_hashes_unchanged ? "verified" : "changed"}</p>}
            {job.cancellable && <button className="danger-button" type="button" onClick={() => void cancel(job)}>Cancel safely</button>}
          </article>)}
          {jobs.length === 0 && <div className="list-state">No ingestion jobs yet. Re-indexing will create an auditable background job.</div>}
        </div>
      </section>
      <section className="source-section">
        <div className="section-heading"><div><p className="eyebrow">Approved registry</p><h2>Indexed sources</h2></div><span>{sources.length} governed sources</span></div>
        <div className="source-table-wrap"><table className="source-table"><thead><tr><th>Source</th><th>Authority</th><th>Version state</th><th>Records</th><th>Chunks</th><th>Indexed</th></tr></thead><tbody>{sources.map((source) => <tr key={source.id}><td><strong>{source.filename}</strong><small>{source.source_type.toUpperCase()} · v{source.version}</small></td><td><span className={`authority-level level-${source.authority_class}`}>{source.authority_class}</span></td><td>{source.version_status?.replaceAll("_", " ") || "registered"}<small>{source.source_date || "date not recorded"}</small></td><td>{source.record_count}</td><td>{source.chunk_count}</td><td><span className={source.indexed ? "indexed-yes" : "indexed-no"}>{source.indexed ? "Indexed" : "Evidence only"}</span></td></tr>)}</tbody></table></div>
      </section>
      <section className="source-section staging-section">
        <div className="section-heading"><div><p className="eyebrow">Private staging</p><h2>Validate a new source</h2></div><label className="upload-button">{busy ? "Working…" : "Choose source"}<input ref={input} aria-label="Choose a knowledge source" type="file" accept=".csv,.xlsx,.pdf,.md,.txt" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); }} /></label></div>
        <div className="governance-flow" aria-label="Ingestion governance flow"><span>Validate</span><i>→</i><span>Privacy scan</span><i>→</i><span>Private stage</span><i>→</i><span>Review items</span><i>→</i><span>Approval</span></div>
        <div className="staged-grid">
          {staged.map((item) => <article className="staged-card" key={item.id}><div><span className={`review-state state-${item.status}`}>{item.status.replaceAll("_", " ")}</span><strong>{item.original_filename}</strong><small>{(item.size_bytes / 1024).toFixed(1)} KB · {new Date(item.created_at).toLocaleString()}</small></div>{item.findings.length > 0 && <p className="blocked-findings">Blocked findings: {item.findings.join(", ")}. Raw values were not retained.</p>}{item.fact_updates.length > 0 && <p>{item.fact_updates.length} governed product fact update(s) detected.</p>}{item.status === "validated" && <button className="secondary-button" type="button" disabled={busy} onClick={() => void propose(item)}>Create review items</button>}</article>)}
          {staged.length === 0 && <div className="list-state">No staged sources. Uploads never become trusted automatically.</div>}
        </div>
      </section>
    </div>
  );
}
