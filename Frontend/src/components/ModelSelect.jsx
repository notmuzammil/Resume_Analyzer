const STORAGE_KEY = "resume-shortlister.model";

export function initialModel(health) {
  const offered = (health.providers || []).flatMap((p) => p.models.map((model) => ({ provider: p.id, model })));
  const isOffered = (choice) => offered.some((o) => o.provider === choice?.provider && o.model === choice?.model);
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
  } catch {
  }
  if (isOffered(saved)) return saved;
  const fallback = health.default || {};
  if (isOffered(fallback)) return fallback;
  return offered.find((o) => o.provider === fallback.provider) || offered[0] || null;
}

export default function ModelSelect({ providers, value, onChange, disabled }) {
  function select(event) {
    const [provider, model] = JSON.parse(event.target.value);
    const choice = { provider, model };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(choice));
    } catch {
    }
    onChange(choice);
  }

  return (
    <label className="model-select">
      <span className="muted small">AI model</span>
      <select
        className="jd-text"
        value={value ? JSON.stringify([value.provider, value.model]) : ""}
        onChange={select}
        disabled={disabled}
      >
        {!value && <option value="">No model available</option>}
        {providers.map((p) => (
          <optgroup key={p.id} label={p.label}>
            {p.models.map((model) => (
              <option key={model} value={JSON.stringify([p.id, model])}>
                {model}
              </option>
            ))}
            {!p.models.length && (
              <option disabled value={JSON.stringify([p.id, ""])}>
                {p.error ? `${p.error}: is the server running?` : "No models found"}
              </option>
            )}
          </optgroup>
        ))}
      </select>
    </label>
  );
}
