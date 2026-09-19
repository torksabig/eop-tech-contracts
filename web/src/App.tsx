import { useDeferredValue, useEffect, useMemo, useState } from "react";

type Item = {
  kind: "tender" | "contract";
  relevance_score: number;
  title?: string;
  description?: string;
  contract_subject?: string;
  organization?: string;
  supplier?: string;
  amount?: number | null;
  contract_value?: number | null;
  currency?: number | string | null;
  cpv?: string | null;
  special_number?: string | null;
  publication_date?: string | null;
  contract_date?: string | null;
  deadline?: string | null;
  url?: string | null;
  query?: string;
  source?: string;
};

type Dataset = {
  collected_at: string;
  counts: { total: number; tenders: number; contracts: number };
  items: Item[];
};

function formatMoney(value?: number | null) {
  if (value == null) return "—";
  return new Intl.NumberFormat("bg-BG", {
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  return d.toLocaleDateString("bg-BG");
}

export default function App() {
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | "tender" | "contract">("all");
  const [minScore, setMinScore] = useState(30);
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch("/data/tech-development.json")
      .then(async (res) => {
        if (!res.ok) throw new Error(`Failed to load dataset (${res.status})`);
        return res.json() as Promise<Dataset>;
      })
      .then((json) => {
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = deferredQuery.trim().toLowerCase();
    return data.items.filter((item) => {
      if (kind !== "all" && item.kind !== kind) return false;
      if ((item.relevance_score ?? 0) < minScore) return false;
      if (!q) return true;
      const hay = [
        item.title,
        item.description,
        item.contract_subject,
        item.organization,
        item.supplier,
        item.cpv,
        item.special_number,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [data, deferredQuery, kind, minScore]);

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">ЦАИС ЕОП · curated feed</p>
        <h1>Tech &amp; development procurements</h1>
        <p className="lede">
          Software, portals, platforms, integrations, and IT systems pulled from{" "}
          <a href="https://app.eop.bg/today" target="_blank" rel="noreferrer">
            app.eop.bg
          </a>
          .
        </p>
        <div className="meta">
          {data ? (
            <>
              <span>{data.counts.total} curated</span>
              <span>{data.counts.tenders} tenders</span>
              <span>{data.counts.contracts} contracts</span>
              <span>synced {formatDate(data.collected_at)}</span>
            </>
          ) : (
            <span>Loading dataset…</span>
          )}
        </div>
      </header>

      <section className="controls" aria-label="Filters">
        <input
          className="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter: dashboard, портал, CRM, CPV…"
        />
        <div className="chips">
          {(["all", "tender", "contract"] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={kind === value ? "chip active" : "chip"}
              onClick={() => setKind(value)}
            >
              {value}
            </button>
          ))}
        </div>
        <label className="score">
          Min score
          <input
            type="range"
            min={0}
            max={120}
            step={5}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
          />
          <strong>{minScore}</strong>
        </label>
      </section>

      <section className="results" aria-live="polite">
        {loading && <p className="state">Loading contracts…</p>}
        {error && <p className="state error">{error}</p>}
        {!loading && !error && filtered.length === 0 && (
          <p className="state">No matches. Lower the score or clear the filter.</p>
        )}
        <ul className="list">
          {filtered.slice(0, 200).map((item) => {
            const key = `${item.kind}-${item.special_number}-${item.title}-${item.supplier}`;
            const money =
              item.kind === "contract"
                ? formatMoney(item.contract_value)
                : formatMoney(item.amount);
            return (
              <li key={key} className="row">
                <div className="row-top">
                  <span className={`tag ${item.kind}`}>{item.kind}</span>
                  <span className="score-pill">{item.relevance_score}</span>
                  <span className="muted">{item.special_number || "—"}</span>
                  <span className="muted">
                    {formatDate(item.publication_date || item.contract_date)}
                  </span>
                </div>
                <h2>
                  {item.url ? (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {item.title || "Untitled"}
                    </a>
                  ) : (
                    item.title || "Untitled"
                  )}
                </h2>
                <p className="desc">
                  {(item.description || item.contract_subject || "").slice(0, 220) ||
                    "No description"}
                </p>
                <div className="row-bottom">
                  <span>{item.organization || "—"}</span>
                  {item.supplier && <span>→ {item.supplier}</span>}
                  <span>{money} BGN-eq</span>
                  {item.cpv && <span>CPV {item.cpv}</span>}
                </div>
              </li>
            );
          })}
        </ul>
        {filtered.length > 200 && (
          <p className="state">Showing 200 of {filtered.length}. Narrow the filter.</p>
        )}
      </section>
    </div>
  );
}
