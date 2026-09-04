import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import type { FactChange, Product } from "../types";

interface Props { token: string }

function displayValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (value === null || value === undefined || value === "") return "Not verified";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ProductsPage({ token }: Props) {
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [history, setHistory] = useState<{ facts: Product["facts"]; changes: FactChange[]; conflicts: Array<Record<string, unknown>> } | null>(null);
  const [historyField, setHistoryField] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.products(token).then((items) => {
      if (!active) return;
      setProducts(items);
      setSelectedId((current) => current || items[0]?.canonical_product_id || "");
    }).catch((reason: Error) => active && setError(reason.message)).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [token]);

  const categories = useMemo(() => [...new Set(products.map((product) => product.category))].sort(), [products]);
  const filtered = products.filter((product) => {
    const value = `${product.model} ${product.canonical_product_id} ${product.name}`.toLowerCase();
    return (!search || value.includes(search.toLowerCase())) && (!category || product.category === category);
  });
  const selected = filtered.find((product) => product.canonical_product_id === selectedId) || filtered[0];

  async function inspectHistory(field: string) {
    if (!selected) return;
    setHistoryField(field);
    setHistory(null);
    try { setHistory(await api.productHistory(token, selected.canonical_product_id, field)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "History unavailable"); }
  }

  return (
    <div className="page-stack">
      <header className="page-header">
        <div><p className="eyebrow">Governed catalog</p><h1>Current Product Master</h1><p>Only populated, source-backed fields are current. Every gap stays visible.</p></div>
        <div className="header-stat"><span>Approved records</span><strong>{products.length}</strong></div>
      </header>
      <div className="master-layout">
        <section className="master-list-panel">
          <div className="filter-row">
            <label className="search-control"><span>Search</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="SKU or Product ID" /></label>
            <label><span>Category</span><select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{categories.map((item) => <option key={item}>{item}</option>)}</select></label>
          </div>
          {loading && <div className="list-state" role="status">Loading governed products…</div>}
          {error && <div className="inline-error" role="alert">{error}</div>}
          <div className="product-list">
            {filtered.map((product) => (
              <button type="button" className={selected?.canonical_product_id === product.canonical_product_id ? "product-row active" : "product-row"} key={product.canonical_product_id} onClick={() => { setSelectedId(product.canonical_product_id); setHistory(null); }}>
                <span className="product-index mono">{product.model}</span>
                <span><strong>{product.name}</strong><small>{product.category}</small></span>
                <span className="row-arrow">→</span>
              </button>
            ))}
            {!loading && filtered.length === 0 && <div className="list-state">No governed product matches these filters.</div>}
          </div>
        </section>
        <section className="product-detail-panel">
          {!selected ? <div className="list-state">Select a product to inspect its approved facts.</div> : <>
            <div className="detail-title"><div><p className="mono sku-line">{selected.model}</p><h2>{selected.name}</h2><p>{selected.category} · Product ID <span className="mono">{selected.canonical_product_id}</span></p></div><StatusBadge status="current_approved" /></div>
            <div className="detail-meta"><span>Source date {selected.source_date}</span><span>Authority {selected.authority_class}</span><span>{selected.confidence.replaceAll("_", " ")}</span></div>
            <div className="section-heading"><div><p className="eyebrow">Approved facts</p><h3>Supported fields</h3></div><span>Click any field for provenance</span></div>
            <div className="fact-grid">
              {Object.entries(selected.supported_attributes).map(([field, value]) => (
                <button type="button" className="fact-cell" key={field} onClick={() => void inspectHistory(field)}><span>{field.replaceAll("_", " ")}</span><strong>{displayValue(value)}</strong><small>View evidence history →</small></button>
              ))}
            </div>
            <div className="unknown-block"><div><p className="eyebrow">Known gaps</p><h3>Not verified</h3></div><div className="unknown-tags">{selected.unsupported_fields.map((field) => <button type="button" key={field} onClick={() => void inspectHistory(field)}>{field.replaceAll("_", " ")}</button>)}</div></div>
            {historyField && <div className="history-panel">
              <div className="section-heading"><div><p className="eyebrow">Evidence timeline</p><h3>{historyField.replaceAll("_", " ")}</h3></div><button className="text-button" type="button" onClick={() => { setHistory(null); setHistoryField(""); }}>Close</button></div>
              {!history && <div className="list-state">Loading history…</div>}
              {history && history.facts.length === 0 && history.changes.length === 0 && <div className="missing-card"><StatusBadge status="missing" /><p>No approved or proposed value exists for this field.</p></div>}
              {history?.facts.map((fact) => <div className="timeline-item" key={fact.id}><i /><div><StatusBadge status={fact.status === "approved" ? "current_approved" : "historical_or_dated"} /><strong>{displayValue(fact.value)}</strong><p>{fact.source_file} · row {fact.source_row} · {fact.source_date}</p><small>{fact.reason}</small></div></div>)}
              {history?.changes.map((change) => <div className="timeline-item proposed" key={change.id}><i /><div><span className={`review-state state-${change.status}`}>{change.status}</span><strong>{displayValue(change.proposed_value)}</strong><p>{change.source_file} · proposed {new Date(change.created_at).toLocaleDateString()}</p></div></div>)}
              {Boolean(history?.conflicts.length) && <div className="conflict-banner">This product has unresolved source or identifier conflicts. Inspect citations before use.</div>}
            </div>}
          </>}
        </section>
      </div>
    </div>
  );
}
