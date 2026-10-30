import { useEffect, useState } from "react";
import { analyzeJd, getHealth, screenResumes } from "./api.js";
import JdInput from "./components/JdInput.jsx";
import JdSummary from "./components/JdSummary.jsx";
import ModelSelect, { initialModel } from "./components/ModelSelect.jsx";
import ResumeUpload from "./components/ResumeUpload.jsx";
import Results from "./components/Results.jsx";

export default function App() {
  const [health, setHealth] = useState(null);
  const [llm, setLlm] = useState(null);
  const [jdMode, setJdMode] = useState("file");
  const [jdFile, setJdFile] = useState(null);
  const [jdText, setJdText] = useState("");
  const [resumes, setResumes] = useState([]);
  const [results, setResults] = useState([]);
  const [jdAnalysis, setJdAnalysis] = useState(null);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [analyzing, setAnalyzing] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getHealth()
      .then((data) => {
        setHealth(data);
        setLlm(initialModel(data));
      })
      .catch(() => setHealth({ status: "down" }));
  }, []);

  useEffect(() => {
    setJdAnalysis(null);
    setResults([]);
  }, [jdMode, jdFile, jdText]);

  const maxResumes = health?.max_resumes || 20;
  const hasJd = jdMode === "file" ? !!jdFile : jdText.trim().length >= 50;
  const busy = analyzing || running;
  const reviewing = !!jdAnalysis && !results.length && !running;
  const canSubmit = !!llm && (jdAnalysis ? resumes.length > 0 && !busy : hasJd && !busy);

  async function handleAnalyze() {
    setError("");
    setResults([]);
    setJdAnalysis(null);
    setAnalyzing(true);
    try {
      setJdAnalysis(await analyzeJd({ jdFile: jdMode === "file" ? jdFile : null, jdText, llm }));
    } catch (err) {
      setError(err.message);
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleScreen() {
    setError("");
    setResults([]);
    setProgress({ done: 0, total: resumes.length });
    setRunning(true);
    try {
      await screenResumes(
        {
          jdFile: jdMode === "file" ? jdFile : null,
          jdText,
          llm,
          resumes,
          jdAnalysis: { ...jdAnalysis, must_haves: jdAnalysis.must_haves.map((m) => m.trim()).filter(Boolean) },
        },
        (event) => {
          if (event.type === "start") setProgress({ done: 0, total: event.total });
          if (event.type === "jd") setJdAnalysis(event.data);
          if (event.type === "error") setError(event.message);
          if (event.type === "result") {
            setResults((prev) => [...prev, event.data]);
            setProgress((p) => ({ ...p, done: p.done + 1 }));
          }
        }
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  const retryable = results.filter(
    (r) => r.status !== "ok" && r.error?.startsWith("AI evaluation failed") && resumes[r.id]?.name === r.file_name
  );

  async function handleRetry() {
    setError("");
    setProgress({ done: 0, total: retryable.length });
    setRunning(true);
    try {
      await screenResumes(
        {
          jdFile: jdMode === "file" ? jdFile : null,
          jdText,
          llm,
          resumes: retryable.map((r) => resumes[r.id]),
          jdAnalysis,
          ids: retryable.map((r) => r.id),
        },
        (event) => {
          if (event.type === "error") setError(event.message);
          if (event.type === "result") {
            setResults((prev) => prev.map((r) => (r.id === event.data.id ? event.data : r)));
            setProgress((p) => ({ ...p, done: p.done + 1 }));
          }
        }
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Resume Shortlister</h1>
          <p className="muted">Upload a job description and up to {maxResumes} resumes. AI ranks every candidate against the JD.</p>
        </div>
        {health?.status === "ok" && health.llm_configured ? (
          <ModelSelect providers={health.providers} value={llm} onChange={setLlm} disabled={busy} />
        ) : (
          <StatusPill health={health} />
        )}
      </header>

      <main>
        <div className="inputs">
          <JdInput
            mode={jdMode}
            onModeChange={setJdMode}
            file={jdFile}
            onFileChange={setJdFile}
            text={jdText}
            onTextChange={setJdText}
            disabled={busy}
          />
          <ResumeUpload files={resumes} onChange={setResumes} maxFiles={maxResumes} disabled={running} />
        </div>

        <div className="actions">
          <button
            type="button"
            className="btn primary"
            onClick={jdAnalysis ? handleScreen : handleAnalyze}
            disabled={!canSubmit}
          >
            {analyzing
              ? "Reading job description…"
              : running
                ? `Screening… ${progress.done}/${progress.total}`
                : jdAnalysis
                  ? `Shortlist ${resumes.length || ""} candidate${resumes.length === 1 ? "" : "s"}`
                  : "Read job description"}
          </button>
          {!hasJd && <span className="muted small">Add a job description to continue</span>}
          {hasJd && !jdAnalysis && !busy && (
            <span className="muted small">The AI drafts the must-haves first, so you can check them before screening</span>
          )}
          {reviewing && !resumes.length && <span className="muted small">Add at least one resume</span>}
          {reviewing && resumes.length > 0 && (
            <span className="muted small">Check the must-haves below, then shortlist</span>
          )}
          {jdAnalysis && results.length > 0 && !running && (
            <button type="button" className="btn secondary" onClick={() => setResults([])}>
              Edit must-haves
            </button>
          )}
        </div>

        {running && (
          <div className="progress" aria-label="Screening progress">
            <div className="progress-fill" style={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }} />
          </div>
        )}

        {error && <div className="alert">{error}</div>}

        {jdAnalysis && <JdSummary analysis={jdAnalysis} editable={reviewing} onChange={setJdAnalysis} />}

        {jdAnalysis && !reviewing && (
          <Results results={results} running={running} retryCount={retryable.length} onRetry={handleRetry} />
        )}
      </main>
    </div>
  );
}

function StatusPill({ health }) {
  if (!health) return <span className="pill">Connecting…</span>;
  if (health.status !== "ok") return <span className="pill pill-bad">Backend offline</span>;
  return <span className="pill pill-warn">AI model not configured</span>;
}
