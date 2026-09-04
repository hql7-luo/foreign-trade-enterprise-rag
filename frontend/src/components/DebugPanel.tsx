import type { QueryResult } from "../types";

export function DebugPanel({ result }: { result: QueryResult }) {
  if (!result.debug) return null;
  return (
    <details className="debug-panel">
      <summary>Admin retrieval trace</summary>
      <div className="debug-stats">
        <span>{result.answer_context_chunks} selected chunks</span>
        <span>{result.answer_context_chars.toLocaleString()} context characters</span>
      </div>
      <div className="debug-table-wrap">
        <table className="debug-table">
          <thead>
            <tr><th>Rank</th><th>Source</th><th>Dense</th><th>BM25</th><th>RRF</th><th>Reranker</th></tr>
          </thead>
          <tbody>
            {result.retrieved_context.map((hit) => (
              <tr key={hit.chunk_id}>
                <td>{hit.final_rank ?? "—"}</td>
                <td>{hit.source_file}<small>{hit.section || `row ${hit.row_number}`}</small></td>
                <td>{hit.dense_score?.toFixed(3) ?? "—"}</td>
                <td>{hit.bm25_score?.toFixed(3) ?? "—"}</td>
                <td>{hit.rrf_score.toFixed(4)}</td>
                <td>{hit.reranker_score.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="debug-json">
        <summary>Claim plan and selection metadata</summary>
        <pre>{JSON.stringify(result.debug, null, 2)}</pre>
      </details>
    </details>
  );
}
