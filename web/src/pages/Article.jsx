import { Link, useLocation, useParams } from "react-router-dom";
import ChatPanel from "../components/ChatPanel";
import { ErrorNote, Loading } from "../components/Status";
import { Kicker } from "../components/Story";
import { fetchPaper, findReport } from "../lib/data";
import { arxivAbs, arxivPdf, byline, hostOf, isStated, longDate, readingTime } from "../lib/format";
import { useAsync, useTitle } from "../lib/hooks";

function Labeled({ label, children, dropcap = false }) {
  return (
    <div className="labeled">
      <h3 className="label">{label}</h3>
      <p className={dropcap ? "dropcap" : undefined}>{children}</p>
    </div>
  );
}

export default function Article() {
  const { "*": rawId } = useParams(); // ids like hep-th/9901001 contain a slash
  const id = decodeURIComponent(rawId || "");
  const { state } = useLocation();
  const { data, error, loading } = useAsync(async () => {
    const report = await findReport(id).catch(() => null);
    if (report) return report;
    if (state?.paper?.id === id) return { paper: state.paper };
    return { paper: await fetchPaper(id) };
  }, [id]);
  useTitle(data?.paper?.title);

  if (loading) return <Loading label="Fetching the report" />;
  if (error) return <ErrorNote error={error}>This paper couldn&rsquo;t be found.</ErrorNote>;

  const { paper, section, edition, brief, featured } = data;
  const ins = paper.insight;
  const cats = paper.categories || [];
  const authors = paper.authors || [];

  return (
    <div className="wrap article-wrap">
      <div className="article-grid">
        <article className="article">
          <Kicker>
            {section ? `${section.name} · ` : ""}
            {cats.slice(0, 3).join(" · ")}
            {!featured && edition ? " · In brief" : ""}
            {brief ? " · Daily brief" : ""}
          </Kicker>
          <h1 className="article-hed">{paper.title}</h1>
          {ins && isStated(ins.tldr) && <p className="article-dek">{ins.tldr}</p>}
          {!ins && paper.summary && <p className="article-dek">{paper.summary}</p>}
          <div className="article-byline">
            <span className="by">By {byline(authors, 6)}</span>
            <span className="meta">
              Submitted {longDate(paper.published || "", false)} · arXiv:{paper.id}
              {ins ? ` · ${readingTime(ins)} min read` : ""}
            </span>
          </div>
          <div className="article-actions">
            <a className="btn btn-ink" href={paper.abs_url || arxivAbs(paper.id)} target="_blank" rel="noreferrer">
              Read on arXiv
            </a>
            <a className="btn btn-outline" href={paper.pdf_url || arxivPdf(paper.id)} target="_blank" rel="noreferrer">
              Official PDF
            </a>
            <a className="btn btn-outline only-mobile" href="#ask">
              Ask about it
            </a>
          </div>

          {ins ? (
            <div className="article-body">
              {isStated(ins.problem) && (
                <Labeled label="The problem" dropcap>
                  {ins.problem}
                </Labeled>
              )}
              {isStated(ins.approach) && <Labeled label="The approach">{ins.approach}</Labeled>}
              {ins.key_findings?.some(isStated) && (
                <div className="labeled">
                  <h3 className="label">Key findings</h3>
                  <ul className="findings">
                    {ins.key_findings.filter(isStated).map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                </div>
              )}
              {isStated(ins.why_it_matters) && (
                <blockquote className="pullquote">
                  <span className="pullquote-label">Why it matters</span>
                  {ins.why_it_matters}
                </blockquote>
              )}
              {isStated(ins.limitations) && <Labeled label="Limitations">{ins.limitations}</Labeled>}
              {ins.tags?.length > 0 && <p className="filed">Filed under: {ins.tags.join(" · ")}</p>}
              {ins.source === "abstract" && (
                <p className="editors-note">Editor&rsquo;s note: this report was prepared from the abstract alone.</p>
              )}
              {paper.links?.length > 0 && (
                <div className="also-online">
                  <h3 className="label">Also online</h3>
                  <ul>
                    {paper.links.map((l) => (
                      <li key={l.url}>
                        <a href={l.url} target="_blank" rel="noreferrer">
                          {l.title}
                        </a>{" "}
                        <span className="host">{l.host || hostOf(l.url)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <details className="abstract">
                <summary>The authors&rsquo; abstract</summary>
                <p>{paper.abstract}</p>
              </details>
            </div>
          ) : (
            <div className="article-body">
              <Labeled label="Abstract" dropcap>
                {paper.abstract}
              </Labeled>
              <p className="editors-note">
                {brief
                  ? "This paper appeared in the daily brief, which summarises abstracts only. Ask the desk about the full paper."
                  : section
                  ? "This paper appeared in brief, so there is no full report. Ask the desk about it."
                  : "This paper hasn’t been covered in an edition. Ask the desk about it."}
              </p>
            </div>
          )}
          {brief && (
            <p className="appeared-in">
              Appeared in the <Link to={`/brief/${brief.date}`}>daily brief of {longDate(brief.date)}</Link>.
            </p>
          )}
          {edition && (
            <p className="appeared-in">
              Appeared in the <Link to={`/edition/${edition.date}`}>edition of {longDate(edition.date)}</Link>
              {section && (
                <>
                  , <Link to={`/section/${section.key}`}>{section.name}</Link>
                </>
              )}
              .
            </p>
          )}
        </article>
        <div id="ask" className="article-aside">
          <ChatPanel paper={paper} />
        </div>
      </div>
    </div>
  );
}
