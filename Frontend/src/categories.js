export const CATEGORIES = [
  { name: "Highly Suitable", className: "cat-high", range: "Score 78–100" },
  { name: "Suitable", className: "cat-suitable", range: "Score 51–77" },
  { name: "Moderate", className: "cat-moderate", range: "Score 41–50" },
  { name: "Not Suitable", className: "cat-not", range: "40 or under, or missing a deal-breaker" },
];

export const CRITERIA = [
  { key: "skills", label: "Skills" },
  { key: "experience", label: "Experience" },
  { key: "education", label: "Education & certifications" },
  { key: "fit", label: "Role fit" },
];

export function categoryClass(name) {
  return CATEGORIES.find((c) => c.name === name)?.className || "cat-error";
}

export function categoryRank(result) {
  if (result.status !== "ok") return CATEGORIES.length;
  return CATEGORIES.findIndex((c) => c.name === result.category);
}
