import { useDeferredValue, useEffect, useMemo, useState } from "react";

type Item = {
  kind: "tender" | "contract";
  relevance_score: number;
  status?: string;
  is_active?: boolean;
  status_label?: string;
  title?: string;
  title_en?: string;
  description?: string;
  description_en?: string;
  contract_subject?: string;
  contract_subject_en?: string;
  organization?: string;
  supplier?: string;
  amount?: number | null;
  contract_value?: number | null;
  budget_amount?: number | null;
  estimated_value?: number | null;
  currency?: number | string | null;
  currency_code?: string | null;
  budget_scope?: string | null;
  cpv?: string | null;
  special_number?: string | null;
  publication_date?: string | null;
  contract_date?: string | null;
  deadline?: string | null;
  offer_phase_end?: string | null;
  url?: string | null;
  query?: string;
  source?: string;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  contact_source?: string | null;
  buyer_address?: string;
  buyer_city?: string;
  buyer_registry_number?: string;
  translation_note?: string;
};

type Dataset = {
  collected_at: string;
  enriched_at?: string;
  counts: {
    total: number;
    tenders: number;
    contracts: number;
    with_contact?: number;
    with_email?: number;
    active?: number;
    with_title_en?: number;
  };
  items: Item[];
};

function formatMoney(value?: number | null, currency?: string | null) {
  if (value == null) return null;
  const amount = new Intl.NumberFormat("en-GB", {
    maximumFractionDigits: 0,
  }).format(value);
  return currency ? `${amount} ${currency}` : amount;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  return d.toLocaleDateString("en-GB");
}

function displayTitle(item: Item) {
  return item.title_en || item.title || "Untitled";
}

function displayDescription(item: Item) {
  return (
    item.description_en ||
    item.contract_subject_en ||
    item.description ||
    item.contract_subject ||
    ""
  );
}

function displayBudget(item: Item) {
  if (item.budget_scope && item.budget_scope !== "Budget unknown") {
    return item.budget_scope;
  }
  const amount =
    item.budget_amount ??
    (item.kind === "contract" ? item.contract_value : item.amount) ??
    item.estimated_value;
  const formatted = formatMoney(amount, item.currency_code || null);
  return formatted || "Budget unknown";
}

function statusClass(item: Item) {
  if (item.is_active || item.status === "active") return "active";
  if (item.status === "awarded") return "awarded";
  if (item.status === "closed") return "closed";
  return "unknown";
}

async function loadDataset(): Promise<Dataset> {
  const preferred = await fetch("/data/tech-development-contacts.json");
  if (preferred.ok) return preferred.json();
  const fallback = await fetch("/data/tech-development.json");
  if (!fallback.ok) throw new Error(`Failed to load dataset (${fallback.status})`);
  return fallback.json();
}

export default function App() {
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | "tender" | "contract">("all");
  const [minScore, setMinScore] = useState(30);
  const [onlyWithEmail, setOnlyWithEmail] = useState(false);
  const [onlyActive, setOnlyActive] = useState(false);
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadDataset()
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
      if (onlyWithEmail && !(item.contact_email || "").trim()) return false;
      if (onlyActive && !(item.is_active || item.status === "active")) return false;
      if (!q) return true;
      const hay = [
        item.title_en,
        item.title,
        item.description_en,
        item.description,
        item.contract_subject_en,
        item.contract_subject,
        item.organization,
        item.supplier,
        item.cpv,
        item.special_number,
        item.contact_name,
        item.contact_email,
        item.contact_phone,
        item.buyer_city,
        item.budget_scope,
        item.status_label,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [data, deferredQuery, kind, minScore, onlyWithEmail, onlyActive]);

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">EOP · tech procurements</p>
        <h1>Tech &amp; development procurements</h1>
        <p className="lede">
          Active status, budget scope, and English titles for software / portal /
          systems work from{" "}
          <a href="https://app.eop.bg/today" target="_blank" rel="noreferrer">
            app.eop.bg
          </a>
          , with buyer contacts.
        </p>
        <div className="meta">
          {data ? (
            <>
              <span>{data.counts.total} rows</span>
              <span>{data.counts.tenders} tenders</span>
              <span>{data.counts.contracts} contracts</span>
              {data.counts.active != null && <span>{data.counts.active} active</span>}
              {data.counts.with_email != null && (
                <span>{data.counts.with_email} with email</span>
              )}
              {data.counts.with_title_en != null && (
                <span>{data.counts.with_title_en} with EN title</span>
              )}
              <span>
                synced {formatDate(data.enriched_at || data.collected_at)}
              </span>
            </>
          ) : (
            <span>Loading dataset…</span>
          )}
        </div>
        <p className="downloads">
          Downloads:{" "}
          <a href="/data/tech-development-contacts.csv">full CSV</a>
          {" · "}
          <a href="/data/contact-list.csv">unique contacts CSV</a>
          {" · "}
          <a href="/data/tech-development-contacts.json">JSON</a>
        </p>
      </header>

      <section className="controls" aria-label="Filters">
        <input
          className="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter: portal, CRM, email, organization…"
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
          <button
            type="button"
            className={onlyActive ? "chip active" : "chip"}
            onClick={() => setOnlyActive((v) => !v)}
          >
            Active only
          </button>
          <button
            type="button"
            className={onlyWithEmail ? "chip active" : "chip"}
            onClick={() => setOnlyWithEmail((v) => !v)}
          >
            has email
          </button>
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
        {loading && <p className="state">Loading contacts…</p>}
        {error && <p className="state error">{error}</p>}
        {!loading && !error && filtered.length === 0 && (
          <p className="state">No matches. Lower the score or clear the filter.</p>
        )}
        <ul className="list">
          {filtered.slice(0, 200).map((item) => {
            const key = `${item.kind}-${item.special_number}-${item.title}-${item.supplier}-${item.contact_email}`;
            const title = displayTitle(item);
            const desc = displayDescription(item);
            const budget = displayBudget(item);
            const label = item.status_label || (item.is_active ? "Active" : "Unknown");
            return (
              <li key={key} className="row">
                <div className="row-top">
                  <span className={`tag ${item.kind}`}>{item.kind}</span>
                  <span className={`badge status-${statusClass(item)}`}>{label}</span>
                  <span className="score-pill">{item.relevance_score}</span>
                  <span className="muted">{item.special_number || "—"}</span>
                  <span className="muted">
                    {formatDate(item.publication_date || item.contract_date)}
                  </span>
                </div>
                <h2>
                  {item.url ? (
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {title}
                    </a>
                  ) : (
                    title
                  )}
                </h2>
                <p className="budget">{budget}</p>
                <p className="desc">
                  {desc.slice(0, 260) || "No description"}
                  {!item.title_en && item.translation_note ? (
                    <span className="muted"> · BG source</span>
                  ) : null}
                </p>
                <div className="contact">
                  <strong>{item.contact_name || "No named contact"}</strong>
                  {item.contact_email ? (
                    <a href={`mailto:${item.contact_email}`}>{item.contact_email}</a>
                  ) : (
                    <span className="muted">no email</span>
                  )}
                  <span>{item.contact_phone || "—"}</span>
                  {item.buyer_address && <span>{item.buyer_address}</span>}
                </div>
                <div className="row-bottom">
                  <span>{item.organization || "—"}</span>
                  {item.supplier && <span>→ {item.supplier}</span>}
                  {item.deadline || item.offer_phase_end ? (
                    <span>
                      deadline {formatDate(item.offer_phase_end || item.deadline)}
                    </span>
                  ) : null}
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
