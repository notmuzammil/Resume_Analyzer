const COLUMNS = [
  ["Rank", (r, i) => i + 1],
  ["Candidate", (r) => r.candidate_name],
  ["Category", (r) => (r.status === "ok" ? r.category : "Error")],
  ["Score", (r) => r.score],
  ["Missing Deal-Breakers", (r) => r.failed_deal_breakers?.join("; ")],
  ["Deal-Breakers To Check", (r) => r.unverified_deal_breakers?.join("; ")],
  ["Missing Must-Haves", (r) => r.failed_must_haves?.join("; ")],
  ["Skills (/10)", (r) => r.breakdown?.skills.rating],
  ["Experience (/10)", (r) => r.breakdown?.experience.rating],
  ["Education (/10)", (r) => r.breakdown?.education.rating],
  ["Role Fit (/10)", (r) => r.breakdown?.fit.rating],
  ["Current Title", (r) => r.current_title],
  ["Relevant Experience (yrs)", (r) => r.relevant_experience_years],
  ["Total Experience (yrs)", (r) => r.total_experience_years],
  ["Email", (r) => r.email],
  ["Phone", (r) => r.phone],
  ["Matched Skills", (r) => r.matched_skills?.join("; ")],
  ["Missing Skills", (r) => r.missing_skills?.join("; ")],
  ["Strengths", (r) => r.strengths?.join("; ")],
  ["Concerns", (r) => r.concerns?.join("; ")],
  ["Summary", (r) => r.summary || r.error],
  ["File", (r) => r.file_name],
  ["AI Model", (r) => r.ai_model],
];

function cell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function downloadCsv(results) {
  const rows = [COLUMNS.map(([header]) => header).join(",")];
  results.forEach((r, i) => rows.push(COLUMNS.map(([, get]) => cell(get(r, i))).join(",")));

  const blob = new Blob(["﻿" + rows.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `shortlist-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
