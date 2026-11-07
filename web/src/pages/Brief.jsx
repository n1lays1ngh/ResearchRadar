import { Link, useParams } from "react-router-dom";
import { ErrorNote, Loading } from "../components/Status";
import SubscribeBox from "../components/SubscribeBox";
import { loadBrief, loadBriefs, loadEditions } from "../lib/data";
import { byline, longDate } from "../lib/format";
import { useAsync, useTitle } from "../lib/hooks";

export default function Brief() {
  const { date } = useParams();
  const { data, error, loading } = useAsync(async () => {
    const [briefs, editions] = await Promise.all([loadBriefs(), loadEditions()]);
    const i = date ? briefs.findIndex((b) => b.date === date) : 0;
    if (i < 0 || !briefs.length) return { briefs, brief: null };
    return { briefs, index: i, edition: editions[0], brief: await loadBrief(briefs[i].date) };
  }, [date]);
  const review = data?.brief?.kind === "review";
  const name = review ? "Week in Review" : "Daily Brief";
  const when = review ? "this week" : "today";
  useTitle(data?.brief ? `${name}, ${longDate(data.brief.date, false)}` : "Daily Brief");

  if (loading) return <Loading label="Fetching the brief" />;
  if (error) return <ErrorNote error={error}>The brief couldn&rsquo;t be loaded.</ErrorNote>;
  if (!data.brief)
    return (
      <div className="wrap narrow empty">
        <h1 className="page-title">{date ? "No brief on that date" : "No daily brief yet"}</h1>
        <p>
          The daily brief is published Monday to Friday, after arXiv&rsquo;s overnight announcement, with a Week in
          Review on Saturday.
        </p>
      </div>
    );

  const { brief, briefs, index, edition } = data;
  const newer = briefs[index - 1];
  const older = briefs[index + 1];
  const picked = brief.sections.reduce((n, s) => n + s.papers.length, 0);

  return (
    <div className="wrap brief-page">
      <header className="brief-head">
        <div className="kicker">{review ? "The Week in Review" : "The Daily Brief"}</div>
        <h1 className="brief-date">{longDate(brief.date)}</h1>
        <p className="brief-stats">
          {review
            ? `The ${picked} best papers from ${brief.covered?.length || 0} daily brief${brief.covered?.length === 1 ? "" : "s"} (${brief.total} arXiv announcements this week)`
            : `${picked} selected from ${brief.total} new announcements on arXiv`}
        </p>
        <nav className="brief-pager" aria-label="Other briefs">
          {older ? <Link to={`/brief/${older.date}`}>← {longDate(older.date, false)}</Link> : <span />}
          {newer ? <Link to={index - 1 === 0 ? "/brief" : `/brief/${newer.date}`}>{longDate(newer.date, false)} →</Link> : <span />}
        </nav>
      </header>
      <div className="brief-grid">
        <div className="brief-main">
          {brief.sections.map((s) => (
            <section key={s.key} className="brief-section">
              <div className="brief-section-head">
                <h2>{s.name}</h2>
                <span className="section-code">arXiv {s.key}</span>
              </div>
              {s.papers.length === 0 ? (
                <p className="brief-empty">No new preprints matched this section {when}.</p>
              ) : (
                <>
                  {s.lede && <p className="brief-lede">{s.lede}</p>}
                  <ol className="brief-items">
                    {s.papers.map((p) => (
                      <li key={p.id}>
                        <h3>
                          <Link to={`/paper/${p.id}`}>{p.title}</Link>
                        </h3>
                        {p.summary && <p className="brief-summary">{p.summary}</p>}
                        <p className="brief-meta">
                          {byline(p.authors, 2)} · {p.categories?.slice(0, 3).join(", ")}
                          {p.announce_type === "cross" ? " · cross-listed" : ""} ·{" "}
                          <a href={p.abs_url} target="_blank" rel="noreferrer">
                            arXiv
                          </a>{" "}
                          ·{" "}
                          <a href={p.pdf_url} target="_blank" rel="noreferrer">
                            PDF
                          </a>
                        </p>
                      </li>
                    ))}
                  </ol>
                </>
              )}
            </section>
          ))}
          <p className="brief-note">
            Summaries are written by a language model from each paper&rsquo;s abstract and may contain errors. Open a
            paper to read the abstract or ask the desk about it.
          </p>
        </div>
        <aside className="brief-rail">
          <SubscribeBox compact initialLists={["daily"]} />
          {edition && (
            <Link className="todays-paper" to="/">
              <span className="tp-label">The weekly edition</span>
              <span className="tp-desc">
                In-depth reports from {longDate(edition.date, false)} ({edition.edition})
              </span>
            </Link>
          )}
          <h4 className="rail-title rail-gap">Recent briefs</h4>
          <ul className="recent-briefs">
            {briefs.slice(0, 10).map((b, i) => (
              <li key={b.date}>
                <Link to={i === 0 ? "/brief" : `/brief/${b.date}`} className={b.date === brief.date ? "current" : ""}>
                  {b.kind === "review" ? `Week in Review, ${longDate(b.date, false)}` : longDate(b.date)}
                </Link>
                <span>{b.picked} papers</span>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}
