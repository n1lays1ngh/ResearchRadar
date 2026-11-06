import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorNote, Loading } from "../components/Status";
import { fetchCategories, fetchLatest } from "../lib/data";
import { byline, longDate } from "../lib/format";
import { useAsync, useTitle } from "../lib/hooks";

export default function Browse() {
  const [params, setParams] = useSearchParams();
  const category = params.get("category") || "cs.CL";
  const days = Number(params.get("days") || 7);
  const q = params.get("q") || "";
  const limit = Number(params.get("limit") || 25);
  const [keywords, setKeywords] = useState(q);
  useEffect(() => {
    setKeywords(q);
  }, [q]);
  useTitle("Browse arXiv");

  const cats = useAsync(fetchCategories, []);
  const results = useAsync(() => fetchLatest({ category, days, q, limit }), [category, days, q, limit]);
  const set = (patch) => setParams({ category, days, q, limit, ...patch });

  return (
    <div className="wrap browse">
      <h1 className="page-title">Browse arXiv</h1>
      <p className="page-dek">
        The newest preprints in any official arXiv category, straight from arXiv. Open one to read it or ask the desk
        about it.
      </p>
      <form
        className="browse-form"
        onSubmit={(e) => {
          e.preventDefault();
          set({ q: keywords.trim() });
        }}
      >
        <label>
          <span>Category</span>
          <select value={category} onChange={(e) => set({ category: e.target.value })}>
            {!cats.data && <option value={category}>{category}</option>}
            {cats.data?.groups.map((g) => (
              <optgroup key={g.name} label={g.name}>
                {g.categories.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.code} · {c.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label>
          <span>Keywords</span>
          <input
            value={keywords}
            placeholder="e.g. state of health, dialogue"
            onChange={(e) => setKeywords(e.target.value)}
          />
        </label>
        <label>
          <span>Last</span>
          <select value={days} onChange={(e) => set({ days: e.target.value })}>
            {[1, 3, 7, 14, 30].map((d) => (
              <option key={d} value={d}>
                {d} day{d > 1 ? "s" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Show</span>
          <select value={limit} onChange={(e) => set({ limit: e.target.value })}>
            {[10, 25, 50].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <button className="btn btn-ink" type="submit">
          Search
        </button>
      </form>
      <p className="browse-source">
        <a href={`https://arxiv.org/list/${category}/recent`} target="_blank" rel="noreferrer">
          See {category} on arxiv.org →
        </a>
      </p>

      {results.loading && <Loading label="Asking arXiv" />}
      {results.error && <ErrorNote error={results.error}>arXiv didn&rsquo;t answer.</ErrorNote>}
      {results.data && (
        <>
          <h2 className="browse-head">
            {results.data.name} <span>({results.data.papers.length})</span>
          </h2>
          {results.data.papers.length === 0 && <p>No preprints found. Try more days or fewer keywords.</p>}
          <ol className="browse-list">
            {results.data.papers.map((p) => (
              <li key={p.id} className="browse-item">
                <div className="kicker kicker-muted">
                  {p.categories?.slice(0, 3).join(" · ")} · {longDate(p.published, false)}
                </div>
                <h3>
                  <Link to={`/paper/${p.id}`} state={{ paper: p }}>
                    {p.title}
                  </Link>
                </h3>
                <p className="browse-by">By {byline(p.authors)}</p>
                <p className="browse-abstract">{p.abstract.slice(0, 320)}{p.abstract.length > 320 ? "…" : ""}</p>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
