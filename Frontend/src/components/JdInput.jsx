import { useRef } from "react";

const JD_ACCEPT = ".pdf,.docx,.txt";

export default function JdInput({ mode, onModeChange, file, onFileChange, text, onTextChange, disabled }) {
  const inputRef = useRef(null);

  return (
    <section className="card">
      <div className="card-header">
        <h2>1. Job Description</h2>
        <div className="tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "file"}
            className={mode === "file" ? "tab active" : "tab"}
            onClick={() => onModeChange("file")}
            disabled={disabled}
          >
            Upload file
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "text"}
            className={mode === "text" ? "tab active" : "tab"}
            onClick={() => onModeChange("text")}
            disabled={disabled}
          >
            Paste text
          </button>
        </div>
      </div>

      {mode === "file" ? (
        file ? (
          <div className="file-row">
            <span className="file-icon">{fileExt(file.name)}</span>
            <span className="file-name">{file.name}</span>
            <button type="button" className="link-btn" onClick={() => onFileChange(null)} disabled={disabled}>
              Remove
            </button>
          </div>
        ) : (
          <button type="button" className="dropzone small" onClick={() => inputRef.current?.click()} disabled={disabled}>
            <strong>Choose JD file</strong>
            <span>PDF or DOCX</span>
          </button>
        )
      ) : (
        <textarea
          className="jd-text"
          placeholder="Paste the job description here: role, responsibilities, required skills, experience…"
          value={text}
          onChange={(e) => onTextChange(e.target.value)}
          disabled={disabled}
          rows={10}
        />
      )}

      <input
        ref={inputRef}
        type="file"
        accept={JD_ACCEPT}
        hidden
        onChange={(e) => {
          onFileChange(e.target.files?.[0] || null);
          e.target.value = "";
        }}
      />
    </section>
  );
}

export function fileExt(name) {
  return (name.split(".").pop() || "").toUpperCase().slice(0, 4);
}
