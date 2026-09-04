import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { Citation, Evidence } from "../types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  citation: Citation | null;
  token: string;
  onClose: () => void;
}

export function EvidenceDrawer({ citation, token, onClose }: Props) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const drawer = useRef<HTMLElement>(null);

  useEffect(() => {
    setEvidence(null);
    setError("");
    if (!citation) return;
    let active = true;
    api
      .evidence(token, citation.chunk_id)
      .then((item) => active && setEvidence(item))
      .catch((reason: Error) => active && setError(reason.message));
    return () => {
      active = false;
    };
  }, [citation, token]);

  useEffect(() => {
    if (!citation) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const node = drawer.current;
    node?.querySelector<HTMLButtonElement>("button")?.focus();
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !node) return;
      const controls = [...node.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
        .filter((control) => !control.hasAttribute("disabled"));
      if (controls.length === 0) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      previousFocus?.focus();
    };
  }, [citation, onClose]);

  if (!citation) return null;
  return (
    <><div className="drawer-scrim" aria-hidden="true" onClick={onClose} />
    <aside ref={drawer} className="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-title">
      <div className="drawer-header">
        <div>
          <p className="eyebrow">Evidence ledger</p>
          <h2 id="evidence-title">{citation.source_file}</h2>
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="Close evidence">
          ×
        </button>
      </div>
      {!evidence && !error && <div className="drawer-loading" role="status">Loading verified excerpt…</div>}
      {error && <div className="inline-error" role="alert">{error}</div>}
      {evidence && (
        <div className="drawer-body">
          <StatusBadge status={evidence.knowledge_status} />
          <dl className="metadata-grid">
            <div><dt>Authority</dt><dd>Level {evidence.authority_class}</dd></div>
            <div><dt>Format</dt><dd>{evidence.source_type.toUpperCase()}</dd></div>
            <div><dt>Section</dt><dd>{evidence.section || "Row-level record"}</dd></div>
            <div><dt>Location</dt><dd>{evidence.sheet ? `${evidence.sheet} · ` : ""}{evidence.row_start ? `row ${evidence.row_start}` : "section"}</dd></div>
            <div><dt>SKU</dt><dd>{evidence.product_sku || "Not linked"}</dd></div>
            <div><dt>Product ID</dt><dd>{evidence.product_id || "Not linked"}</dd></div>
            <div><dt>Source date</dt><dd>{evidence.source_date || "Not recorded"}</dd></div>
            <div><dt>Version</dt><dd className="mono">{evidence.source_version?.slice(0, 12) || "source snapshot"}</dd></div>
          </dl>
          <div className="excerpt-block">
            <p className="eyebrow">Relevant excerpt</p>
            <pre>{evidence.excerpt}</pre>
          </div>
          <p className="privacy-note">Only the indexed evidence fragment is shown. The original private file is never served.</p>
        </div>
      )}
    </aside></>
  );
}
