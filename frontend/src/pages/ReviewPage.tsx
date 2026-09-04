import { useEffect, useState } from "react";

import { api } from "../api";
import type { FactChange } from "../types";

interface Props { token: string }

function value(value: unknown) {
  return value === null || value === undefined ? "Unknown" : typeof value === "object" ? JSON.stringify(value) : String(value);
}

export function ReviewPage({ token }: Props) {
  const statuses = ["pending", "approved", "rejected", "superseded"];
  const [status, setStatus] = useState("pending");
  const [items, setItems] = useState<FactChange[]>([]);
  const [selected, setSelected] = useState<FactChange | null>(null);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load(nextStatus = status) {
    setLoading(true); setError("");
    try {
      const changes = await api.changes(token, nextStatus);
      setItems(changes);
      const summary = changes.find((item) => item.id === selected?.id) || changes[0] || null;
      setSelected(summary ? await api.change(token, summary.id) : null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Review queue unavailable"); }
    finally { setLoading(false); }
  }

  useEffect(() => { void load(status); }, [status]);

  async function inspect(item: FactChange) {
    setSelected(item); setNote(""); setError("");
    try { setSelected(await api.change(token, item.id)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Change detail unavailable"); }
  }

  async function decide(action: "approve" | "reject" | "supersede") {
    if (!selected || note.trim().length < 4) return;
    setWorking(true); setError(""); setMessage("");
    try {
      await api.decide(token, selected.id, action, note.trim());
      setMessage(`${action[0].toUpperCase()}${action.slice(1)}d with an auditable reviewer note.`);
      setNote("");
      await load(status);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Review action failed"); }
    finally { setWorking(false); }
  }

  return (
    <div className="page-stack">
      <header className="page-header"><div><p className="eyebrow">Knowledge governance</p><h1>Reviewer queue</h1><p>Compare evidence before a proposed fact can become current company truth.</p></div><div className="header-stat pending"><span>In this view</span><strong>{items.length}</strong></div></header>
      <div className="review-tabs" role="tablist" aria-label="Fact change status">{statuses.map((item, index) => <button id={`review-tab-${item}`} aria-controls="review-panel" tabIndex={status === item ? 0 : -1} type="button" role="tab" aria-selected={status === item} className={status === item ? "active" : ""} key={item} onClick={() => setStatus(item)} onKeyDown={(event) => { if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return; event.preventDefault(); const direction = event.key === "ArrowRight" ? 1 : -1; const next = statuses[(index + direction + statuses.length) % statuses.length]; setStatus(next); document.getElementById(`review-tab-${next}`)?.focus(); }}>{item}</button>)}</div>
      {message && <div className="success-banner" role="status">{message}</div>}
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="review-layout" id="review-panel" role="tabpanel" aria-labelledby={`review-tab-${status}`}>
        <section className="review-queue">
          <div className="queue-heading"><span>Change request</span><span>Field</span><span>Status</span></div>
          {loading && <div className="list-state">Loading review items…</div>}
          {!loading && items.length === 0 && <div className="list-state">No {status} changes. New conflicts will appear here.</div>}
          {items.map((item) => <button type="button" className={selected?.id === item.id ? "review-row active" : "review-row"} key={item.id} onClick={() => void inspect(item)}><span><strong>{item.product_sku}</strong><small className="mono">{item.canonical_product_id}</small></span><span>{item.field_name.replaceAll("_", " ")}</span><span className={`review-state state-${item.status}`}>{item.status}</span></button>)}
        </section>
        <section className="review-detail">
          {!selected ? <div className="list-state">Select a change to inspect its evidence.</div> : <>
            <div className="detail-title"><div><p className="eyebrow">{selected.product_sku} · proposed fact</p><h2>{selected.field_name.replaceAll("_", " ")}</h2></div><span className={`review-state state-${selected.status}`}>{selected.status}</span></div>
            <div className="value-compare"><div><span>{selected.status === "pending" ? "Current approved value" : "Previous approved value"}</span><strong>{value(selected.existing_value)}</strong>{selected.existing_value === null && <small>Field was previously unverified</small>}</div><div className="proposed-value"><span>{selected.status === "approved" ? "Approved value" : "Proposed value"}</span><strong>{value(selected.proposed_value)}</strong><small>{selected.status === "approved" ? "Promoted through reviewer approval" : "Not authoritative until approved"}</small></div></div>
            <div className="review-evidence"><p className="eyebrow">Source evidence</p><dl><div><dt>Source</dt><dd>{String(selected.evidence.original_filename || selected.source_file)}</dd></div><div><dt>Row</dt><dd>{selected.source_row}</dd></div><div><dt>Version</dt><dd className="mono">{selected.source_version.slice(0, 12)}</dd></div><div><dt>Submitted</dt><dd>{new Date(selected.created_at).toLocaleString()}</dd></div></dl><blockquote>{String(selected.evidence.statement || "Source-backed proposal awaiting reviewer interpretation")}</blockquote></div>
            {selected.status === "pending" && <div className="decision-box"><label>Reviewer note<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Explain why the evidence supports or does not support this fact." rows={3} /></label><div className="decision-actions"><button className="danger-button" type="button" disabled={working || note.trim().length < 4} onClick={() => void decide("reject")}>Reject</button><button className="primary-button" type="button" disabled={working || note.trim().length < 4} onClick={() => void decide("approve")}>{working ? "Recording…" : "Approve fact"}</button></div></div>}
            {selected.status === "approved" && <div className="decision-box"><label>Supersede note<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Explain why this approved non-core fact should return to unknown." rows={3} /></label><button className="secondary-button" type="button" disabled={working || note.trim().length < 4} onClick={() => void decide("supersede")}>Supersede fact</button></div>}
            <div className="audit-events"><p className="eyebrow">Audit trail</p>{selected.events.map((event, index) => <div key={index}><i /><span><strong>{String(event.to_status)}</strong>{String(event.actor)} · {new Date(String(event.occurred_at)).toLocaleString()}</span></div>)}</div>
          </>}
        </section>
      </div>
    </div>
  );
}
