import { Link } from "react-router-dom";
import { byline, isStated, readingTime } from "../lib/format";

export function Kicker({ children, muted = false }) {
  return <div className={muted ? "kicker kicker-muted" : "kicker"}>{children}</div>;
}

/** A story teaser. size: "lead" | "standard" | "compact" */
export function Story({ paper, size = "standard", kicker, showSummary = true }) {
  const ins = paper.insight;
  const to = `/paper/${paper.id}`;
  return (
    <article className={`story story-${size}`}>
      {kicker && <Kicker>{kicker}</Kicker>}
      <h3 className="story-hed">
        <Link to={to}>{paper.title}</Link>
      </h3>
      {ins && isStated(ins.tldr) && <p className="story-dek">{ins.tldr}</p>}
      {showSummary && size === "lead" && ins && isStated(ins.problem) && (
        <p className="story-summary">{ins.problem}</p>
      )}
      <p className="story-meta">
        <span className="story-byline">By {byline(paper.authors)}</span>
        {ins && <span className="story-time">{readingTime(ins)} min read</span>}
      </p>
    </article>
  );
}

export function Briefs({ papers, title }) {
  if (!papers.length) return null;
  return (
    <section className="briefs">
      <h4 className="rail-title">{title}</h4>
      <ol className="brief-list">
        {papers.map((p) => (
          <li key={p.id}>
            <Link to={`/paper/${p.id}`}>{p.title}</Link>
            <span className="brief-by">{byline(p.authors, 2)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Elsewhere({ items }) {
  if (!items?.length) return null;
  return (
    <section className="elsewhere">
      <h4 className="rail-title">Elsewhere in the journals</h4>
      <div className="elsewhere-grid">
        {items.map((r) => (
          <a key={r.url} className="elsewhere-item" href={r.url} target="_blank" rel="noreferrer">
            <span className="elsewhere-host">{r.host}</span>
            <span className="elsewhere-title">{r.title}</span>
          </a>
        ))}
      </div>
    </section>
  );
}
