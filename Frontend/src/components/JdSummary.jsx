import { CRITERIA } from "../categories.js";

const MAX_MUST_HAVES = 10;

export default function JdSummary({ analysis, editable = false, onChange }) {
  const meta = [analysis.department, analysis.seniority].filter(Boolean).join(" · ");
  const mustHaves = [analysis.experience_requirement, ...analysis.must_haves].filter(Boolean);
  const dealBreakers = analysis.deal_breakers;

  return (
    <section className={`card${editable ? " card-review" : ""}`}>
      <div className="card-header">
        <div>
          <h2>{analysis.job_title}</h2>
          {meta && <span className="muted small">{meta}</span>}
        </div>
        <span className="muted small">{editable ? "Check before screening" : "How the AI read the JD"}</span>
      </div>

      <div className="jd-grid">
        <div>
          <h4>Scoring weights</h4>
          <div className="weights">
            {CRITERIA.map(({ key, label }) => (
              <div key={key} className="breakdown-item">
                <div className="breakdown-label">
                  <span>{label}</span>
                  <span>{analysis.weights[key]}%</span>
                </div>
                <div className="score-bar">
                  <div className="score-fill neutral" style={{ width: `${analysis.weights[key]}%` }} />
                </div>
              </div>
            ))}
          </div>
          {analysis.weight_reason && <p className="muted small">{analysis.weight_reason}</p>}
        </div>

        <div>
          <h4>Must-haves</h4>
          {editable ? (
            <MustHaveEditor analysis={analysis} onChange={onChange} />
          ) : mustHaves.length ? (
            <>
              <p className="muted small">
                {dealBreakers.length
                  ? "Missing a deal-breaker makes a candidate Not Suitable. Other missing must-haves are shown as warnings."
                  : "Missing must-haves are shown as warnings. The category follows the score."}
              </p>
              <ul className="bullets">
                {mustHaves.map((m) => (
                  <li key={m}>
                    {m}
                    {dealBreakers.includes(m) && <span className="tag-deal-breaker">Deal-breaker</span>}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="muted small">The JD has no strictly mandatory requirements. Candidates are ranked by score only.</p>
          )}
          {analysis.nice_to_haves.length > 0 && (
            <>
              <h4 className="spaced">Nice to have</h4>
              <div className="chips">
                {analysis.nice_to_haves.map((n) => (
                  <span key={n} className="chip chip-neutral">
                    {n}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function MustHaveEditor({ analysis, onChange }) {
  const items = analysis.must_haves;
  const dealBreakers = analysis.deal_breakers;

  function update(mustHaves, nextDealBreakers = dealBreakers) {
    onChange({ ...analysis, must_haves: mustHaves, deal_breakers: nextDealBreakers });
  }

  function editItem(i, text) {
    update(
      items.map((m, j) => (j === i ? text : m)),
      dealBreakers.map((d) => (d === items[i] ? text : d))
    );
  }

  function removeItem(i) {
    update(
      items.filter((_, j) => j !== i),
      dealBreakers.filter((d) => d !== items[i])
    );
  }

  function setDealBreaker(item, on) {
    update(items, on ? [...dealBreakers, item] : dealBreakers.filter((d) => d !== item));
  }

  function setYears(value) {
    const years = value === "" ? null : Number(value);
    const valid = years > 0 ? years : null;
    onChange({
      ...analysis,
      min_experience_years: valid,
      experience_requirement: valid ? `Minimum ${valid} years of relevant experience` : null,
    });
  }

  return (
    <>
      <p className="muted small">
        The AI drafted this list from the JD. Fix the wording, remove what does not matter or add what is missing.
        A missing must-have is shown as a warning and the category follows the score. Candidates missing a{" "}
        <strong>Deal-breaker</strong> are Not Suitable whatever their score. The AI ticks a required degree or license;
        untick it if the role can do without, and tick only other true requirements.
      </p>

      <label className="years-row">
        <span>Minimum years of experience</span>
        <input
          type="number"
          min="0"
          step="0.5"
          className="jd-text years-input"
          placeholder="None"
          value={analysis.min_experience_years ?? ""}
          onChange={(e) => setYears(e.target.value)}
        />
      </label>

      <ul className="edit-list">
        {items.map((item, i) => (
          <li key={i} className="edit-row">
            <textarea
              className="jd-text edit-input"
              rows={1}
              value={item}
              aria-label={`Must-have ${i + 1}`}
              onChange={(e) => editItem(i, e.target.value)}
            />
            <label className="deal-breaker-toggle">
              <input
                type="checkbox"
                checked={dealBreakers.includes(item)}
                onChange={(e) => setDealBreaker(item, e.target.checked)}
                disabled={!item.trim()}
              />
              Deal-breaker
            </label>
            <button
              type="button"
              className="link-btn"
              aria-label={`Remove ${item || `must-have ${i + 1}`}`}
              onClick={() => removeItem(i)}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
      {!items.length && <p className="muted small">No must-haves: candidates are ranked by score only.</p>}

      <button
        type="button"
        className="link-btn"
        onClick={() => update([...items, ""])}
        disabled={items.length >= MAX_MUST_HAVES}
      >
        + Add must-have
      </button>
    </>
  );
}
