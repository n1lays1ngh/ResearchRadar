// Static data (built from data/editions by scripts/sync-data.mjs) and API calls.
const cache = new Map();

function getJSON(url) {
  if (!cache.has(url)) {
    cache.set(
      url,
      fetch(url).then((r) => {
        if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
        return r.json();
      }).catch((err) => {
        cache.delete(url); // allow a retry
        throw err;
      }),
    );
  }
  return cache.get(url);
}

export const loadEditions = () => getJSON("/data/editions.json");
export const loadEdition = (date) => getJSON(`/editions/${date}.json`);
export const loadPaperIndex = () => getJSON("/data/papers.json");

/** Find a paper's report in the archive: { paper, section, edition } or null. */
export async function findReport(id) {
  const index = await loadPaperIndex();
  const hit = index[id];
  if (!hit) return null;
  const edition = await loadEdition(hit.date);
  const section = edition.sections.find((s) => s.key === hit.section);
  const featured = section?.featured.find((p) => p.id === id);
  const paper = featured || section?.more.find((p) => p.id === id);
  return paper ? { paper, section, edition, featured: Boolean(featured) } : null;
}

async function api(url, options) {
  const r = await fetch(url, options);
  let body = null;
  try {
    body = await r.json();
  } catch {
    /* non-JSON error page */
  }
  if (!r.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : `The server returned HTTP ${r.status}.`);
  }
  return body;
}

export const fetchPaper = (id) => api(`/api/paper/${encodeURIComponent(id)}`);
export const fetchCategories = () => {
  if (!cache.has("cats")) cache.set("cats", api("/api/categories"));
  return cache.get("cats");
};
export const fetchLatest = ({ category, days, q, limit }) =>
  api(`/api/arxiv?${new URLSearchParams({ category, days, q, limit })}`);

const post = (url, data) =>
  api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
export const requestSubscription = (data) => post("/api/subscribe", data);
export const confirmSubscription = (token) => post("/api/subscribe/confirm", { token });

/**
 * Stream a chat answer. Calls onEvent for each NDJSON event:
 * {type:"sources", sources, fulltext} | {type:"delta", text} | {type:"error", message} | {type:"done"}
 */
export async function streamChat({ paper, messages, web, signal }, onEvent) {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      paper: { id: paper.id, title: paper.title || "", authors: paper.authors || [], abstract: paper.abstract || "" },
      messages,
      web,
    }),
    signal,
  });
  if (!r.ok || !r.body) {
    let detail = `The server returned HTTP ${r.status}.`;
    try {
      const body = await r.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
}
