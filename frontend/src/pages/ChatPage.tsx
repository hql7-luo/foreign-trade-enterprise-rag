import { useMemo, useState } from "react";

import { api } from "../api";
import { DebugPanel } from "../components/DebugPanel";
import { EvidenceRail, StatusBadge } from "../components/StatusBadge";
import type { Citation, KnowledgeStatus, QueryResult, Role } from "../types";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  result?: QueryResult;
}

interface Props {
  token: string;
  role: Role;
  onEvidence: (citation: Citation) => void;
}

const prompts = [
  "Show NSTR-VESSEL-731 specifications.",
  "What is the current lead time for NSTR-LANTERN-864?",
  "Which payment terms and Incoterm were in the historical NSTR-VESSEL-731 quotation?",
  "SOP: explain the release gate and quality inspection.",
];

function statusSet(result: QueryResult): KnowledgeStatus[] {
  const values = new Set<KnowledgeStatus>(
    result.sources.map((source) => source.knowledge_status),
  );
  if (result.claims.some((claim) => !claim.supported)) values.add("missing");
  if (result.conflicts.length) values.add("conflict");
  return [...values];
}

function ClaimCard({ claim, onEvidence }: { claim: QueryResult["claims"][number]; onEvidence: Props["onEvidence"] }) {
  const status: KnowledgeStatus = claim.supported
    ? claim.sources[0]?.knowledge_status || "authoritative"
    : "missing";
  return (
    <li className="claim-card">
      <span className={`claim-pin status-${status}`} aria-hidden="true" />
      <div>
        <StatusBadge status={status} />
        <p>{claim.text}</p>
        {claim.sources.length > 0 && (
          <div className="citation-row">
            {claim.sources.map((source) => (
              <button type="button" className="citation-chip" key={source.chunk_id} onClick={() => onEvidence(source)}>
                [{source.citation_id}] {source.source_file}{source.row_number ? ` · row ${source.row_number}` : ""}
              </button>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}

export function ChatPage({ token, role, onEvidence }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [debug, setDebug] = useState(false);

  const latestResult = useMemo(
    () => [...messages].reverse().find((message) => message.result)?.result,
    [messages],
  );

  async function ask(value = question) {
    const clean = value.trim();
    if (!clean || loading) return;
    setQuestion("");
    setError("");
    setLoading(true);
    setMessages((items) => [...items, { id: crypto.randomUUID(), role: "user", text: clean }]);
    try {
      const result = await api.query(token, clean, role === "admin" && debug);
      setMessages((items) => [
        ...items,
        { id: crypto.randomUUID(), role: "assistant", text: result.answer, result },
      ]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The knowledge query failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="chat-layout">
      <section className="chat-main">
        <header className="page-header chat-header">
          <div>
            <p className="eyebrow">Employee workspace</p>
            <h1>Ask company knowledge</h1>
            <p>Answers are assembled only from approved evidence. Unknown fields remain unknown.</p>
          </div>
          {role === "admin" && (
            <label className="debug-toggle">
              <input type="checkbox" checked={debug} onChange={(event) => setDebug(event.target.checked)} />
              Developer trace
            </label>
          )}
        </header>

        <div className="conversation" aria-live="polite">
          {messages.length === 0 && (
            <div className="chat-empty">
              <div className="empty-compass" aria-hidden="true">✦</div>
              <h2>Start with a product, process, or evidence question.</h2>
              <p>The assistant separates approved current facts from dated quotation evidence and explicit gaps.</p>
              <div className="prompt-grid">
                {prompts.map((prompt) => <button type="button" key={prompt} onClick={() => void ask(prompt)}>{prompt}</button>)}
              </div>
            </div>
          )}
          {messages.map((message) => (
            <article className={`message message-${message.role}`} key={message.id}>
              <div className="message-label">{message.role === "user" ? "You" : "Knowledge Desk"}</div>
              {message.role === "user" ? <p>{message.text}</p> : message.result && (
                <div className="answer-card">
                  <EvidenceRail active={statusSet(message.result)} />
                  <div className="answer-summary">
                    <StatusBadge status={message.result.sufficient_information ? "authoritative" : "missing"} />
                    <p>{message.text}</p>
                  </div>
                  {message.result.conflicts.length > 0 && (
                    <div className="conflict-banner"><strong>Conflicting evidence detected.</strong> Review every cited value before using it.</div>
                  )}
                  {message.result.claims.length > 0 && (
                    <ol className="claim-list">
                      {message.result.claims.map((claim, index) => <ClaimCard key={`${claim.text}-${index}`} claim={claim} onEvidence={onEvidence} />)}
                    </ol>
                  )}
                  <DebugPanel result={message.result} />
                </div>
              )}
            </article>
          ))}
          {loading && <div className="thinking" role="status"><span /><span /><span />Checking approved evidence</div>}
        </div>
        {error && <div className="inline-error" role="alert">{error}</div>}
        <form className="composer" onSubmit={(event) => { event.preventDefault(); void ask(); }}>
          <label htmlFor="question">Ask a grounded question</label>
          <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Compare travel drinkware, or ask what is still unverified…" rows={3} />
          <div className="composer-foot"><span>No general-world-knowledge completion</span><button className="primary-button" type="submit" disabled={!question.trim() || loading}>Ask knowledge</button></div>
        </form>
      </section>
      <aside className="trust-sidebar">
        <p className="eyebrow">Trust model</p>
        <h2>Evidence before confidence</h2>
        <div className="trust-list">
          <div><i className="status-current_approved" /><span><strong>Current approved</strong>Governed product master</span></div>
          <div><i className="status-historical_or_dated" /><span><strong>Historical / dated</strong>Never promoted silently</span></div>
          <div><i className="status-missing" /><span><strong>Missing</strong>Explicitly unverified</span></div>
          <div><i className="status-conflict" /><span><strong>Conflict</strong>Requires comparison</span></div>
        </div>
        {latestResult && <div className="context-receipt"><span>Last answer receipt</span><strong>{latestResult.sources.length} sources</strong><strong>{latestResult.claims.filter((claim) => claim.supported).length}/{latestResult.claims.length} claims supported</strong></div>}
      </aside>
    </div>
  );
}
