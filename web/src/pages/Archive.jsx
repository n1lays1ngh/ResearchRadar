import { Link } from "react-router-dom";
import { ErrorNote, Loading } from "../components/Status";
import { loadBriefs, loadEditions } from "../lib/data";
import { longDate } from "../lib/format";
import { useAsync, useTitle } from "../lib/hooks";

export default function Archive() {
  const { data, error, loading } = useAsync(
    async () => ({ editions: await loadEditions(), briefs: await loadBriefs().catch(() => []) }),
    [],
  );
  useTitle("Archive");
  if (loading) return <Loading />;
  if (error) return <ErrorNote error={error}>The archive couldn&rsquo;t be loaded.</ErrorNote>;
  return (
    <div className="wrap narrow">
      <h1 className="page-title">The archive</h1>
      <p className="page-dek">Every weekly edition and daily brief, newest first.</p>
      <h2 className="archive-heading">Weekly editions</h2>
      {data.editions.length === 0 && <p>No editions yet.</p>}
      <ol className="archive-list">
        {data.editions.map((e) => (
          <li key={e.date} className="archive-item">
            <div className="archive-date">
              <span className="archive-edition">{e.edition}</span>
              <Link to={`/edition/${e.date}`}>{longDate(e.date)}</Link>
              <span className="archive-stats">
                {e.picked} selected from {e.scanned} preprints · {e.week_range}
              </span>
            </div>
            <ul className="archive-leads">
              {e.leads.map((l) => (
                <li key={l.id}>
                  <span className="kicker">{l.section}</span> <Link to={`/paper/${l.id}`}>{l.title}</Link>
                </li>
              ))}
            </ul>
            <div className="archive-actions">
              <Link className="btn btn-ink btn-sm" to={`/edition/${e.date}`}>
                Read
              </Link>
              {e.pdf && (
                <a className="btn btn-outline btn-sm" href={`/editions/${e.date}.pdf`} download>
                  PDF
                </a>
              )}
              {e.html && (
                <a className="btn btn-outline btn-sm" href={`/editions/${e.date}.html`} target="_blank" rel="noreferrer">
                  Email version
                </a>
              )}
            </div>
          </li>
        ))}
      </ol>
      {data.briefs.length > 0 && (
        <>
          <h2 className="archive-heading">Daily briefs</h2>
          <ul className="brief-archive">
            {data.briefs.map((b) => (
              <li key={b.date}>
                <Link to={`/brief/${b.date}`}>{longDate(b.date)}</Link>
                <span>
                  {b.picked} papers · {b.leads[0]?.title}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
