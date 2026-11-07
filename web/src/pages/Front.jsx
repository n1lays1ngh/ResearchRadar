import { Link, useParams } from "react-router-dom";
import SectionBlock from "../components/SectionBlock";
import { ErrorNote, Loading } from "../components/Status";
import { Kicker, Story } from "../components/Story";
import SubscribeBox from "../components/SubscribeBox";
import { loadBriefs, loadEdition, loadEditions } from "../lib/data";
import { byline, isStated, longDate, readingTime } from "../lib/format";
import { useAsync, useTitle } from "../lib/hooks";

export default function Front() {
  const { date } = useParams();
  const { data, error, loading } = useAsync(async () => {
    const [editions, briefs] = await Promise.all([loadEditions(), loadBriefs().catch(() => [])]);
    const meta = date ? editions.find((e) => e.date === date) : editions[0];
    if (!meta) return { editions, edition: null, meta: null };
    return { editions, meta, latestBrief: briefs[0], edition: await loadEdition(meta.date) };
  }, [date]);
  useTitle(date && data?.meta ? `Edition of ${longDate(data.meta.date, false)}` : "");

  if (loading) return <Loading label="Fetching the paper" />;
  if (error) return <ErrorNote error={error}>The edition couldn&rsquo;t be loaded.</ErrorNote>;
  if (!data.edition)
    return (
      <div className="wrap empty">
        <h1 className="page-title">{date ? "No edition on that date" : "The presses haven’t run yet"}</h1>
        <p>
          {date ? <Link to="/archive">See the archive</Link> : "The first edition appears after the next weekly run."}
        </p>
      </div>
    );

  const { edition, meta, editions, latestBrief } = data;
  const isLatest = editions[0].date === meta.date;
  const withLeads = edition.sections.filter((s) => s.featured.length);
  const [top, ...others] = withLeads;
  const topStory = top.featured[0];
  const ins = topStory.insight;

  return (
    <div className="wrap front">
      {!isLatest && (
        <div className="archive-banner">
          You are reading the edition of {longDate(meta.date)}. <Link to="/">Go to the latest edition</Link>
        </div>
      )}
      <div className="front-top">
        <div className="front-left">
          {others.map((s) => (
            <Story key={s.key} paper={s.featured[0]} size="standard" kicker={s.name} />
          ))}
        </div>
        <article className="front-main">
          <Kicker>
            {top.name} · {topStory.categories?.[0] || top.key}
          </Kicker>
          <h1 className="front-hed">
            <Link to={`/paper/${topStory.id}`}>{topStory.title}</Link>
          </h1>
          {ins && isStated(ins.tldr) && <p className="front-dek">{ins.tldr}</p>}
          <p className="story-meta">
            <span className="story-byline">By {byline(topStory.authors)}</span>
            {ins && <span className="story-time">{readingTime(ins)} min read</span>}
          </p>
          {ins && isStated(ins.problem) && <p className="front-summary">{ins.problem}</p>}
          {ins && isStated(ins.why_it_matters) && (
            <blockquote className="front-quote">{ins.why_it_matters}</blockquote>
          )}
          <Link className="read-more" to={`/paper/${topStory.id}`}>
            Read the full report →
          </Link>
          <SubscribeBox banner />
        </article>
        <aside className="front-right">
          {latestBrief && isLatest && (
            <Link className="brief-teaser" to="/brief">
              <span className="kicker">
                {latestBrief.kind === "review" ? "The Week in Review" : "The Daily Brief"} ·{" "}
                {longDate(latestBrief.date, false)}
              </span>
              <span className="brief-teaser-hed">{latestBrief.leads[0]?.title}</span>
              <span className="brief-teaser-more">
                {latestBrief.kind === "review"
                  ? `The week's ${latestBrief.picked} best papers →`
                  : `${latestBrief.picked} papers from today's arXiv announcement →`}
              </span>
            </Link>
          )}
          <h4 className="rail-title">The week in brief</h4>
          {edition.sections
            .filter((s) => s.overview)
            .map((s) => (
              <div key={s.key} className="note">
                <Kicker>{s.name}</Kicker>
                <p>{s.overview}</p>
                <Link className="note-more" to={`/section/${s.key}`}>
                  More in {s.name} →
                </Link>
              </div>
            ))}
          {meta.pdf && (
            <a className="todays-paper" href={`/editions/${meta.date}.pdf`} download>
              <span className="tp-label">Today&rsquo;s paper</span>
              <span className="tp-desc">Download this edition as a PDF ({edition.edition})</span>
            </a>
          )}
        </aside>
      </div>
      {edition.sections.map((s) => (
        <SectionBlock key={s.key} section={s} skipLead={withLeads.includes(s)} />
      ))}
    </div>
  );
}
