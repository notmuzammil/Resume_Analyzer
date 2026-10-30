const API_URL = import.meta.env.VITE_API_URL || "";

export async function getHealth() {
  const res = await fetch(`${API_URL}/api/health`);
  if (!res.ok) throw new Error("Backend is not reachable");
  return res.json();
}

export async function analyzeJd({ jdFile, jdText, llm }) {
  const res = await post("/api/analyze-jd", jdForm({ jdFile, jdText, llm }));
  return res.json();
}

export async function screenResumes({ jdFile, jdText, llm, resumes, jdAnalysis, ids }, onEvent) {
  const form = jdForm({ jdFile, jdText, llm });
  resumes.forEach((file) => form.append("resumes", file));
  if (jdAnalysis) form.append("jd_analysis", JSON.stringify(jdAnalysis));
  if (ids) form.append("ids", JSON.stringify(ids));

  const res = await post("/api/screen", form);
  const requestId = res.headers.get("X-Request-ID");
  const emit = (event) => onEvent(event.type === "error" ? { ...event, message: withRef(event.message, requestId) } : event);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) emit(JSON.parse(line));
    }
  }
  if (buffer.trim()) emit(JSON.parse(buffer));
}

function jdForm({ jdFile, jdText, llm }) {
  const form = new FormData();
  if (jdFile) form.append("jd_file", jdFile);
  else form.append("jd_text", jdText);
  form.append("provider", llm.provider);
  form.append("model", llm.model);
  return form;
}

async function post(path, form) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, { method: "POST", body: form });
  } catch {
    throw new Error("Cannot reach the backend. Make sure it is running on port 8000.");
  }

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
    }
    throw new Error(withRef(message, res.headers.get("X-Request-ID")));
  }
  return res;
}

function withRef(message, requestId) {
  return requestId ? `${message} (ref ${requestId})` : message;
}
