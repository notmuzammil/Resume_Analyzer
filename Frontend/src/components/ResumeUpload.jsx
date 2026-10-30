import { useRef, useState } from "react";
import { fileExt } from "./JdInput.jsx";

const ALLOWED = [".pdf", ".docx"];

export default function ResumeUpload({ files, onChange, maxFiles, disabled }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [warning, setWarning] = useState("");

  function addFiles(list) {
    const incoming = Array.from(list);
    const valid = incoming.filter((f) => ALLOWED.some((ext) => f.name.toLowerCase().endsWith(ext)));
    const notes = [];
    if (valid.length < incoming.length) notes.push(`${incoming.length - valid.length} file(s) skipped (only PDF and DOCX are allowed)`);

    const existing = new Set(files.map((f) => `${f.name}:${f.size}`));
    const fresh = valid.filter((f) => !existing.has(`${f.name}:${f.size}`));

    const room = maxFiles - files.length;
    if (fresh.length > room) notes.push(`Only ${maxFiles} resumes allowed; ${fresh.length - room} not added`);

    setWarning(notes.join(". "));
    onChange([...files, ...fresh.slice(0, Math.max(room, 0))]);
  }

  return (
    <section className="card">
      <div className="card-header">
        <h2>2. Resumes</h2>
        <span className="muted">
          {files.length} / {maxFiles}
        </span>
      </div>

      <button
        type="button"
        className={`dropzone${dragging ? " dragging" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled) addFiles(e.dataTransfer.files);
        }}
        disabled={disabled || files.length >= maxFiles}
      >
        <strong>Drag &amp; drop resumes here, or click to browse</strong>
        <span>PDF or DOCX, up to {maxFiles} files</span>
      </button>

      <input
        ref={inputRef}
        type="file"
        accept={ALLOWED.join(",")}
        multiple
        hidden
        onChange={(e) => {
          addFiles(e.target.files || []);
          e.target.value = "";
        }}
      />

      {warning && <p className="warning">{warning}</p>}

      {files.length > 0 && (
        <>
          <ul className="file-list">
            {files.map((file, index) => (
              <li key={`${file.name}:${file.size}`} className="file-row">
                <span className="file-icon">{fileExt(file.name)}</span>
                <span className="file-name">{file.name}</span>
                <span className="muted small">{(file.size / 1024).toFixed(0)} KB</span>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => onChange(files.filter((_, i) => i !== index))}
                  disabled={disabled}
                  aria-label={`Remove ${file.name}`}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="link-btn" onClick={() => onChange([])} disabled={disabled}>
            Clear all
          </button>
        </>
      )}
    </section>
  );
}
