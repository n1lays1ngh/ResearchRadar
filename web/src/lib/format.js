const NOT_STATED = "Not stated in the provided text.";

export const isStated = (text) => Boolean(text) && text.trim() !== NOT_STATED;

export function longDate(iso, withWeekday = true) {
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    weekday: withWeekday ? "long" : undefined,
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function byline(authors = [], limit = 3) {
  if (!authors.length) return "Unknown authors";
  if (authors.length > limit) return `${authors.slice(0, limit).join(", ")} and others`;
  if (authors.length === 1) return authors[0];
  return `${authors.slice(0, -1).join(", ")} and ${authors.at(-1)}`;
}

/** Rough reading time of a report, newspaper style. */
export function readingTime(insight) {
  if (!insight) return 1;
  const words = [insight.problem, insight.approach, insight.limitations, insight.why_it_matters, ...(insight.key_findings || [])]
    .join(" ")
    .split(/\s+/).length;
  return Math.max(1, Math.round(words / 220));
}

export const hostOf = (url) => {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
};

export const arxivAbs = (id) => `https://arxiv.org/abs/${id}`;
export const arxivPdf = (id) => `https://arxiv.org/pdf/${id}`;
