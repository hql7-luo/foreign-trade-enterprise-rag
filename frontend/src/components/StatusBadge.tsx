import type { KnowledgeStatus } from "../types";

const labels: Record<KnowledgeStatus, string> = {
  current_approved: "Current approved",
  historical_or_dated: "Historical / dated",
  authoritative: "Authoritative guidance",
  missing: "Missing / unverified",
  conflict: "Conflict",
};

export function StatusBadge({ status }: { status: KnowledgeStatus }) {
  return <span className={`status-badge status-${status}`}>{labels[status]}</span>;
}

export function EvidenceRail({ active }: { active: KnowledgeStatus[] }) {
  const statuses: KnowledgeStatus[] = [
    "current_approved",
    "historical_or_dated",
    "missing",
    "conflict",
  ];
  return (
    <div className="evidence-rail" aria-label="Evidence status summary">
      {statuses.map((status) => (
        <span
          className={`rail-segment status-${status} ${active.includes(status) ? "is-active" : ""}`}
          key={status}
          title={labels[status]}
        />
      ))}
    </div>
  );
}
