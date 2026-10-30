import { Fragment, useMemo, useState } from "react";
import { CATEGORIES, CRITERIA, categoryClass, categoryRank } from "../categories.js";
import { downloadCsv } from "../export.js";

export default function Results({ results, running, retryCount, onRetry }) {
  const [filter, setFilter] = useState("All");
  const [expanded, setExpanded] = useState(null);

  const sorted = useMemo(
    () =>
      [...results].sort((a, b) => categoryRank(a) - categoryRank(b) || (b.score ?? -1) - (a.score ?? -1)),
    [results]
  );

  const counts = useMemo(() => {
    const c = { All: sorted.length, Error: 0 };
    CATEGORIES.forEach((cat) => (c[cat.name] = 0));
    sorted.forEach((r) => (r.status === "ok" ? c[r.category]++ : c.Error++));
    return c;
  }, [sorted]);

  const visible = sorted.filter((r) =>
    filter === "All" ? true : filter === "Error" ? r.status !== "ok" : r.category === filter
  );

  return (
    <section className="card">
      <div className="card-header">
        <h2>Shortlist</h2>
        <div className="actions">
          {retryCount > 0 && (
            <button type="button" className="btn secondary" onClick={onRetry} disabled={running}>
              Retry {retryCount} failed
            </button>
          )}
          <button type="button" className="btn secondary" onClick={() => downloadCsv(sorted)} disabled={running || !results.length}>
            Export to Excel (CSV)
          </button>
        </div>
      </div>

      <div className="summary">
        <button type="button" className={`summary-tile${filter === "All" ? " selected" : ""}`} onClick={() => setFilter("All")}>
          <span className="summary-count">{counts.All}</span>
          <span>All candidates</span>
        </button>
        {CATEGORIES.map((cat) => (
          <button
            type="button"
            key={cat.name}
            className={`summary-tile ${cat.className}${filter === cat.name ? " selected" : ""}`}
            onClick={() => setFilter(cat.name)}
          >
            <span className="summary-count">{counts[cat.name]}</span>
            <span>{cat.name}</span>
            <span className="muted small">{cat.range}</span>
          </button>
        ))}
        {counts.Error > 0 && (
          <button
            type="button"
            className={`summary-tile cat-error${filter === "Error" ? " selected" : ""}`}
            onClick={() => setFilter("Error")}
          >
            <span className="summary-count">{counts.Error}</span>
            <span>Could not process</span>
          </button>
        )}
      </div>

      <div className="table-wrap">
        <table className="results">
          <thead>
            <tr>
              <th>#</th>
              <th>Candidate</th>
              <th>Score</th>
              <th>Category</th>
              <th className="hide-sm">Experience</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => {
              const rank = sorted.indexOf(r) + 1;
              const isOpen = expanded === r.id;
              const warnings = r.failed_must_haves?.filter((m) => !r.failed_deal_breakers?.includes(m)) || [];
              return (
                <Fragment key={r.id}>
                  <tr className={isOpen ? "open" : ""} onClick={() => setExpanded(isOpen ? null : r.id)}>
                    <td>{rank}</td>
                    <td>
                      <div className="cand-name">{r.status === "ok" ? r.candidate_name : r.file_name}</div>
                      <div className="muted small">{r.status === "ok" ? r.current_title || r.file_name : r.error}</div>
                    </td>
                    <td>
                      {r.status === "ok" ? (
                        <div className="score">
                          <div className="score-bar">
                            <div className={`score-fill ${categoryClass(r.category)}`} style={{ width: `${r.score}%` }} />
                          </div>
                          <span>{r.score}</span>
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <span className={`badge ${r.status === "ok" ? categoryClass(r.category) : "cat-error"}`}>
                        {r.status === "ok" ? r.category : "Error"}
                      </span>
                      {r.failed_deal_breakers?.length > 0 && (
                        <div className="knockout small">✗ Missing deal-breaker: {r.failed_deal_breakers.join(", ")}</div>
                      )}
                      {r.unverified_deal_breakers?.length > 0 && (
                        <div className="check-note small">? Check manually: {r.unverified_deal_breakers.join(", ")}</div>
                      )}
                      {warnings.length > 0 && <div className="missing-note small">⚠ Missing: {warnings.join(", ")}</div>}
                    </td>
                    <td className="hide-sm">
                      {r.relevant_experience_years != null ? (
                        <>
                          <div>{r.relevant_experience_years} yrs relevant</div>
                          <div className="muted small">{r.total_experience_years} yrs total</div>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="chevron">{r.status === "ok" ? (isOpen ? "▲" : "▼") : ""}</td>
                  </tr>
                  {isOpen && r.status === "ok" && (
                    <tr className="details-row">
                      <td colSpan={6}>
                        <Details r={r} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {running && (
              <tr>
                <td colSpan={6} className="muted center">
                  Screening remaining resumes…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Details({ r }) {
  return (
    <div className="details">
      <p className="summary-text">{r.summary}</p>

      <div className="contact muted small">
        {r.email && <span>✉ {r.email}</span>}
        {r.phone && <span>☎ {r.phone}</span>}
        <span>📄 {r.file_name}</span>
        {r.ai_model && <span>Rated by {r.ai_model}</span>}
      </div>

      {r.must_haves?.length > 0 && (
        <div>
          <h4>Must-have check</h4>
          <ul className="checklist">
            {r.must_haves.map((m) => (
              <li
                key={m.requirement}
                className={m.met === false ? (m.deal_breaker ? "fail" : "warn") : m.met ? "pass" : "unknown"}
              >
                <span className="check-icon">{m.met === false ? "✗" : m.met ? "✓" : "?"}</span>
                <div>
                  <div>
                    {m.requirement}
                    {m.deal_breaker && <span className="tag-deal-breaker">Deal-breaker</span>}
                  </div>
                  {m.evidence && <div className="muted small">{m.evidence}</div>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="breakdown">
        {CRITERIA.map(({ key, label }) => {
          const { rating, weight } = r.breakdown[key];
          return (
            <div key={key} className="breakdown-item">
              <div className="breakdown-label">
                <span>
                  {label} <span className="muted">({weight}%)</span>
                </span>
                <span>{rating}/10</span>
              </div>
              <div className="score-bar">
                <div className="score-fill neutral" style={{ width: `${rating * 10}%` }} />
              </div>
            </div>
          );
        })}
      </div>

      {r.positions.length > 0 && (
        <div>
          <h4>Work history (calculated to today)</h4>
          <ul className="history">
            {r.positions.map((p) => (
              <li key={`${p.title}-${p.period}`}>
                <span>
                  {p.title}
                  {p.company && <span className="muted">, {p.company}</span>}
                </span>
                <span className="muted small">
                  {p.period} · {p.years} yrs{p.relevant ? "" : " · not relevant"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="details-grid">
        <List title="Matched skills" items={r.matched_skills} chip="chip-good" />
        <List title="Missing skills" items={r.missing_skills} chip="chip-bad" />
        <List title="Strengths" items={r.strengths} />
        <List title="Concerns" items={r.concerns} />
      </div>
    </div>
  );
}

function List({ title, items, chip }) {
  return (
    <div>
      <h4>{title}</h4>
      {!items?.length ? (
        <p className="muted small">None noted</p>
      ) : chip ? (
        <div className="chips">
          {items.map((item) => (
            <span key={item} className={`chip ${chip}`}>
              {item}
            </span>
          ))}
        </div>
      ) : (
        <ul className="bullets">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
